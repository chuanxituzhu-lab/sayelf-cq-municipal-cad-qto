from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import server as app_server

from cad_qto.canonical import canonicalize_dxf
from cad_qto.conversion import ConversionError, convert_to_dxf
from cad_qto.dxf import geometry_inventory, parse_ascii_dxf
from cad_qto.job import run_job
from cad_qto.network import calculate_network_sections
from cad_qto.retaining import RetainingInputError, calculate_retaining_sections
from cad_qto.review import ReviewInputError, record_job_review
from cad_qto.road import calculate_road_sections


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

    def test_road_and_network_quantities_are_deterministic_and_explicit(self) -> None:
        source_manifest = {"source_file": "fixtures/cq_retaining_demo.dxf", "source_sha256": "demo-sha"}
        road = calculate_road_sections([{
            "section_id": "RD-001", "length_m": 30, "road_type": "城市支路",
            "carriageway_width_m": 7, "surface_thickness_m": 0.18,
            "base_thickness_m": 0.20, "subbase_thickness_m": 0.20,
            "roadbed_width_m": 9, "cut_depth_m": 0.30, "curb_length_m": 60,
            "sidewalk_area_m2": 90,
        }], source_manifest)
        network = calculate_network_sections([{
            "segment_id": "PS-001", "length_m": 30, "network_type": "雨水管",
            "pipe_outer_diameter_mm": 600, "trench_width_m": 1.2,
            "trench_depth_m": 1.8, "bedding_thickness_m": 0.15,
            "manhole_count": 2, "inlet_count": 3, "road_restoration_area_m2": 36,
        }], source_manifest)
        road_totals = {item["item_code"]: item["quantity"] for item in road["totals"]}
        network_totals = {item["item_code"]: item["quantity"] for item in network["totals"]}
        self.assertEqual(road["discipline"], "road")
        self.assertEqual(road_totals["CQ-ROAD-SURFACE-AREA"], 210.0)
        self.assertEqual(road_totals["CQ-ROAD-SURFACE"], 37.8)
        self.assertEqual(road_totals["CQ-ROAD-CUT"], 81.0)
        self.assertEqual(network["discipline"], "network")
        self.assertEqual(network_totals["CQ-NET-PIPE"], 30.0)
        self.assertEqual(network_totals["CQ-NET-EXC"], 64.8)
        self.assertEqual(network_totals["CQ-NET-BEDDING"], 5.4)
        self.assertEqual(network_totals["CQ-NET-MANHOLE"], 2.0)

    def test_incomplete_section_stops_instead_of_guessing(self) -> None:
        with self.assertRaises(RetainingInputError):
            calculate_retaining_sections([{"section_id": "R-X", "length_m": 20}], {})

    def test_conversion_rejects_scan_like_pdf_and_missing_dwg_converter(self) -> None:
        from reportlab.pdfgen import canvas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            blank_pdf = root / "scan-like.pdf"
            pdf = canvas.Canvas(str(blank_pdf), pagesize=(200, 100))
            pdf.showPage()
            pdf.save()
            with self.assertRaises(ConversionError) as pdf_error:
                convert_to_dxf(blank_pdf, root / "scan-like.dxf")
            self.assertIn("矢量线段或文字", str(pdf_error.exception))

            fake_dwg = root / "drawing.dwg"
            fake_dwg.write_bytes(b"not-a-dwg")
            with self.assertRaises(ConversionError) as dwg_error:
                convert_to_dxf(fake_dwg, root / "drawing.dxf")
            self.assertTrue("DWG" in str(dwg_error.exception) or "dwg" in str(dwg_error.exception))

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
        original = {name: getattr(app_server, name) for name in ("DATA", "CAD_JOBS", "CAD_INPUTS", "CAD_EXPORTS", "PROJECT_ID", "PROJECT_NAME", "REVIEWER_ID")}
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder) / "data"
            app_server.DATA = data
            app_server.CAD_JOBS = data / "cad_jobs"
            app_server.CAD_INPUTS = data / "cad_inputs"
            app_server.CAD_EXPORTS = data / "cad_exports"
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
                self.assertEqual(bootstrap["input_formats"], ["ASCII DXF（默认）", "PDF（本地矢量转 DXF）", "DWG（本地转换器转 DXF）"])
                self.assertEqual(bootstrap["disciplines"], ["road", "network", "retaining"])
                self.assertTrue(bootstrap["file_entry"]["multiple"])
                self.assertEqual(bootstrap["file_entry"]["default_extension"], ".dxf")
                self.assertEqual({".dxf", ".pdf", ".dwg"}, set(bootstrap["file_entry"]["accepted_extensions"]))
                self.assertNotIn("roles", bootstrap)

                boundary = "----sayelf-cad-qto-test"
                uploaded_body = (
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"demo.dxf\"\r\nContent-Type: application/dxf\r\n\r\n".encode("utf-8")
                    + FIXTURE.read_bytes()
                    + f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"demo-2.dxf\"\r\nContent-Type: application/dxf\r\n\r\n".encode("utf-8")
                    + FIXTURE.read_bytes()
                    + f"\r\n--{boundary}--\r\n".encode("utf-8")
                )
                upload_request = urllib.request.Request(f"{base}/api/cad/files", data=uploaded_body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
                with urllib.request.urlopen(upload_request) as response:
                    uploaded = json.loads(response.read().decode("utf-8"))
                self.assertEqual(response.status, 201)
                self.assertEqual(len(uploaded["files"]), 2)
                uploaded_source = uploaded["files"][0]["source_file"]
                self.assertNotEqual(uploaded_source, "")
                self.assertEqual(len(list(app_server.CAD_INPUTS.glob("*.dxf"))), 2)
                with urllib.request.urlopen(f"{base}/api/cad/files") as response:
                    listed_files = json.loads(response.read().decode("utf-8"))
                self.assertEqual(len(listed_files["files"]), 2)

                inspect_batch_request = urllib.request.Request(f"{base}/api/cad/inspect-batch", data=json.dumps({"source_files": ["fixtures/cq_retaining_demo.dxf", "fixtures/cq_retaining_demo.dxf"]}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(inspect_batch_request) as response:
                    batch = json.loads(response.read().decode("utf-8"))
                self.assertEqual(len(batch["inspections"]), 2)
                self.assertTrue(all(item["status"] == "PARSED" for item in batch["inspections"]))

                inspect_request = urllib.request.Request(f"{base}/api/cad/inspect", data=json.dumps({"source_file": "fixtures/cq_retaining_demo.dxf"}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(inspect_request) as response:
                    inspection = json.loads(response.read().decode("utf-8"))
                self.assertEqual(inspection["inspection"]["status"], "PARSED")

                payload = json.loads(INPUT.read_text(encoding="utf-8"))
                calculate_request = urllib.request.Request(f"{base}/api/cad/calculate", data=json.dumps({"source_file": "fixtures/cq_retaining_demo.dxf", "road_sections": [{"section_id": "RD-001", "length_m": 30, "carriageway_width_m": 7, "surface_thickness_m": 0.18, "base_thickness_m": 0.2, "subbase_thickness_m": 0.2}], "network_sections": [{"segment_id": "PS-001", "length_m": 30, "pipe_outer_diameter_mm": 600, "trench_width_m": 1.2, "trench_depth_m": 1.8, "bedding_thickness_m": 0.15}], "retaining_sections": payload["sections"]}, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(calculate_request) as response:
                    calculation = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(response.status, 201)
                job_id = calculation["summary"]["job_id"]
                self.assertEqual(calculation["job"]["status"], "REVIEW_REQUIRED")
                self.assertEqual(calculation["job"]["calculation"]["disciplines"], ["road", "network", "retaining"])
                self.assertGreater(calculation["summary"]["quantity_count"], 13)
                self.assertTrue((app_server.CAD_JOBS / f"{job_id}.json").exists())

                with urllib.request.urlopen(f"{base}/api/cad/jobs") as response:
                    jobs = json.loads(response.read().decode("utf-8"))
                self.assertEqual(len(jobs["jobs"]), 1)
                self.assertGreater(jobs["jobs"][0]["quantity_count"], 13)

                with urllib.request.urlopen(f"{base}/api/cad/jobs/{job_id}") as response:
                    detail = json.loads(response.read().decode("utf-8"))
                self.assertEqual(detail["job_id"], job_id)
                self.assertEqual(len(detail["source"]["source_sha256"]), 64)

                with urllib.request.urlopen(f"{base}/api/cad/jobs/{job_id}/export?format=xlsx") as response:
                    workbook = response.read()
                    self.assertEqual(response.status, 200)
                    self.assertIn("attachment", response.headers.get("Content-Disposition", ""))
                self.assertTrue(zipfile.is_zipfile(__import__("io").BytesIO(workbook)))
                with urllib.request.urlopen(f"{base}/api/cad/jobs/{job_id}/export?format=pdf") as response:
                    report = response.read()
                    self.assertEqual(response.status, 200)
                self.assertTrue(report.startswith(b"%PDF-"))

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

    def test_server_converts_vector_pdf_and_preserves_two_hashes(self) -> None:
        from reportlab.pdfgen import canvas

        original = {name: getattr(app_server, name) for name in ("DATA", "CAD_JOBS", "CAD_INPUTS", "CAD_EXPORTS", "PROJECT_ID", "PROJECT_NAME", "REVIEWER_ID")}
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder) / "data"
            app_server.DATA = data
            app_server.CAD_JOBS = data / "cad_jobs"
            app_server.CAD_INPUTS = data / "cad_inputs"
            app_server.CAD_EXPORTS = data / "cad_exports"
            app_server.PROJECT_ID = "TEST-PDF-QTO"
            app_server.PROJECT_NAME = "测试 PDF 转 DXF"
            app_server.REVIEWER_ID = None
            httpd = app_server.ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{httpd.server_address[1]}"
            try:
                pdf_path = Path(folder) / "vector.pdf"
                pdf = canvas.Canvas(str(pdf_path), pagesize=(200, 100))
                pdf.line(10, 10, 100, 10)
                pdf.rect(20, 20, 50, 30)
                pdf.drawString(30, 70, "K0+000")
                pdf.save()
                boundary = "----sayelf-cad-qto-pdf"
                uploaded_body = (
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"vector.pdf\"\r\nContent-Type: application/pdf\r\n\r\n".encode("utf-8")
                    + pdf_path.read_bytes()
                    + f"\r\n--{boundary}--\r\n".encode("utf-8")
                )
                request = urllib.request.Request(f"{base}/api/cad/files", data=uploaded_body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
                with urllib.request.urlopen(request) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                item = payload["files"][0]
                self.assertEqual(item["input_format"], "pdf")
                self.assertEqual(item["conversion_status"], "CONVERTED")
                self.assertEqual(len(item["original_sha256"]), 64)
                self.assertEqual(len(item["source_sha256"]), 64)
                self.assertNotEqual(item["original_sha256"], item["source_sha256"])
                converted = list((data / "cad_inputs").glob("*.converted.dxf"))
                self.assertEqual(len(converted), 1)
                self.assertEqual(__import__("server").inspect_dxf(converted[0])["geometry_inventory"]["entity_count"], 3)
            finally:
                httpd.shutdown()
                httpd.server_close()
        for name, value in original.items():
            setattr(app_server, name, value)


if __name__ == "__main__":
    unittest.main()
