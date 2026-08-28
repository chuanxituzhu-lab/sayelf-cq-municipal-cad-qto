from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import server as app_server

from cad_qto.canonical import canonicalize_dxf
from cad_qto.dxf import geometry_inventory, parse_ascii_dxf
from cad_qto.job import run_job
from cad_qto.retaining import RetainingInputError, calculate_retaining_sections
from cad_qto.review import ReviewInputError, record_job_review


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "cq_retaining_demo.dxf"
INPUT = ROOT / "fixtures" / "cq_retaining_demo.json"


class MunicipalQtoTests(unittest.TestCase):
    def test_dxf_inventory_reports_unsupported_entities(self) -> None:
        document = parse_ascii_dxf(FIXTURE)
        inventory = geometry_inventory(document)
        self.assertEqual(inventory["entity_count"], 3)
        self.assertEqual(inventory["unsupported_entity_count"], 1)
        layers = {layer["layer"]: layer for layer in inventory["layers"]}
        self.assertEqual(layers["挡护结构-挡墙"]["linear_length"], 68.0)
        self.assertEqual(layers["挡护结构-排水"]["linear_length"], 30.0)
        self.assertEqual(document.units_code, "6")

    def test_canonicalization_keeps_traceable_hashes_and_warning(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            manifest = canonicalize_dxf(FIXTURE, Path(folder) / "demo.canonical.dxf")
        self.assertEqual(manifest["status"], "NORMALIZED")
        self.assertEqual(len(manifest["source_sha256"]), 64)
        self.assertEqual(len(manifest["canonical_sha256"]), 64)
        self.assertTrue(manifest["warnings"])

    def test_retaining_quantities_are_deterministic_and_explicit(self) -> None:
        payload = json.loads(INPUT.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            job = run_job(payload, canonical_path=Path(folder) / "demo.canonical.dxf")
        totals = {item["item_code"]: item["quantity"] for item in job["calculation"]["totals"]}
        self.assertEqual(totals["CQ-RET-WALL"], 168.0)
        self.assertEqual(totals["CQ-RET-FOUND"], 36.0)
        self.assertEqual(totals["CQ-RET-DRAIN-HOLE"], 7.0)
        self.assertEqual(totals["CQ-RET-ANCHOR"], 6.0)
        self.assertEqual(totals["CQ-RET-PILE"], 15.36)
        self.assertEqual(totals["CQ-RET-SHOTCRETE"], 1.5)
        self.assertEqual(job["status"], "REVIEW_REQUIRED")
        self.assertEqual(job["calculation"]["review_status"], "待人工审核")
        self.assertTrue(all(item["status"] == "Inference" for item in job["calculation"]["quantities"]))

    def test_incomplete_section_stops_instead_of_guessing(self) -> None:
        with self.assertRaises(RetainingInputError):
            calculate_retaining_sections([{"section_id": "R-X", "length_m": 20}], {})

    def test_review_requires_all_checks_and_explicit_confirmation(self) -> None:
        payload = json.loads(INPUT.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            job = run_job(payload, canonical_path=Path(folder) / "demo.canonical.dxf")
        incomplete = {"job_id": job["job_id"], "reviewer_id": "cost-01", "reviewer_role": "cost", "decision": "approve", "checked_items": ["source_drawing"], "confirm": True}
        with self.assertRaises(ReviewInputError):
            record_job_review(job, incomplete)
        unconfirmed = {"job_id": job["job_id"], "reviewer_id": "cost-01", "reviewer_role": "cost", "decision": "return", "checked_items": [], "confirm": False}
        with self.assertRaises(ReviewInputError):
            record_job_review(job, unconfirmed)

    def test_review_promotes_only_with_verified_local_identity(self) -> None:
        payload = json.loads(INPUT.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            job = run_job(payload, canonical_path=Path(folder) / "demo.canonical.dxf")
        review_input = {"job_id": job["job_id"], "reviewer_id": "verified-cost", "reviewer_role": "cost", "decision": "approve", "checked_items": ["source_drawing", "design_basis", "section_parameters", "units_and_rule", "location_scope"], "confirm": True}
        pending = record_job_review(job, review_input)
        self.assertEqual(pending["status"], "REVIEWED_PENDING_AUTHORITY")
        promoted = record_job_review(pending, review_input, verified_reviewer_id="verified-cost")
        self.assertEqual(promoted["status"], "FACT_CONFIRMED")
        self.assertEqual(promoted["review"]["semantic_status"], "Fact")

    def test_server_exposes_only_cad_workflow_and_persists_job(self) -> None:
        original = {name: getattr(app_server, name) for name in ("DATA", "CAD_JOBS", "PROJECT_ID", "PROJECT_NAME", "REVIEWER_ID")}
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder) / "data"
            app_server.DATA = data
            app_server.CAD_JOBS = data / "cad_jobs"
            app_server.PROJECT_ID = "TEST-CAD-QTO"
            app_server.PROJECT_NAME = "测试 CAD 造价算量"
            app_server.REVIEWER_ID = None
            httpd = app_server.ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{httpd.server_address[1]}"
            try:
                with urllib.request.urlopen(f"{base}/api/bootstrap") as response:
                    bootstrap = json.loads(response.read().decode("utf-8"))
                self.assertEqual(bootstrap["project"]["project_name"], "测试 CAD 造价算量")
                self.assertEqual(bootstrap["input_formats"], ["ASCII DXF"])
                self.assertNotIn("roles", bootstrap)

                inspect_request = urllib.request.Request(f"{base}/api/cad/inspect", data=json.dumps({"source_file": "fixtures/cq_retaining_demo.dxf"}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(inspect_request) as response:
                    inspection = json.loads(response.read().decode("utf-8"))
                self.assertEqual(inspection["inspection"]["status"], "PARSED")

                payload = json.loads(INPUT.read_text(encoding="utf-8"))
                calculate_request = urllib.request.Request(f"{base}/api/cad/retaining", data=json.dumps({"source_file": "fixtures/cq_retaining_demo.dxf", "sections": payload["sections"]}, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(calculate_request) as response:
                    calculation = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(response.status, 201)
                job_id = calculation["summary"]["job_id"]
                self.assertEqual(calculation["job"]["status"], "REVIEW_REQUIRED")
                self.assertTrue((app_server.CAD_JOBS / f"{job_id}.json").exists())

                with urllib.request.urlopen(f"{base}/api/cad/jobs") as response:
                    jobs = json.loads(response.read().decode("utf-8"))
                self.assertEqual(len(jobs["jobs"]), 1)
                self.assertEqual(jobs["jobs"][0]["quantity_count"], 13)

                with urllib.request.urlopen(f"{base}/api/cad/jobs/{job_id}") as response:
                    detail = json.loads(response.read().decode("utf-8"))
                self.assertEqual(detail["job_id"], job_id)
                self.assertEqual(len(detail["source"]["source_sha256"]), 64)

                with self.assertRaises(urllib.error.HTTPError) as old_route:
                    urllib.request.urlopen(f"{base}/api/records")
                self.assertEqual(old_route.exception.code, 404)

                with self.assertRaises(urllib.error.HTTPError) as old_page:
                    urllib.request.urlopen(f"{base}/admin.html")
                self.assertEqual(old_page.exception.code, 404)

                bad_request = urllib.request.Request(f"{base}/api/cad/inspect", data=json.dumps({"source_file": "../outside.dxf"}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
                with self.assertRaises(urllib.error.HTTPError) as escaped:
                    urllib.request.urlopen(bad_request)
                self.assertEqual(escaped.exception.code, 400)
            finally:
                httpd.shutdown()
                httpd.server_close()
        for name, value in original.items():
            setattr(app_server, name, value)


if __name__ == "__main__":
    unittest.main()
