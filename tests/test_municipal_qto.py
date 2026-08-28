from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
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
    def test_mcp_stdio_handshake_and_tool_flow(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            project_root = Path(folder)
            shutil.copytree(ROOT / "cad_qto", project_root / "cad_qto")
            shutil.copy(FIXTURE, project_root / "demo.dxf")
            payload = json.loads(INPUT.read_text(encoding="utf-8"))
            environment = os.environ.copy()
            environment["MUNICIPAL_QTO_PROJECT_ROOT"] = str(project_root)
            process = subprocess.Popen(
                [sys.executable, str(ROOT / "plugins" / "municipal-cad-qto" / "mcp_server.py")],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=environment,
            )

            def request(message: dict) -> dict:
                assert process.stdin is not None
                assert process.stdout is not None
                process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
                process.stdin.flush()
                line = process.stdout.readline()
                if not line:
                    stderr = process.stderr.read() if process.stderr else ""
                    self.fail(f"MCP 服务提前退出：{stderr}")
                return json.loads(line)

            try:
                initialized = request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
                self.assertEqual(initialized["result"]["serverInfo"]["name"], "municipal-cad-qto")
                listed = request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
                self.assertEqual(len(listed["result"]["tools"]), 7)
                inspected = request({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "municipal_qto_inspect_dxf", "arguments": {"source_file": "demo.dxf"}}})
                self.assertEqual(json.loads(inspected["result"]["content"][0]["text"])["status"], "PARSED")
                normalized = request({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "municipal_qto_normalize_dxf", "arguments": {"source_file": "demo.dxf", "output_file": "data/cad_jobs/test.canonical.dxf"}}})
                self.assertEqual(json.loads(normalized["result"]["content"][0]["text"])["status"], "NORMALIZED")
                calculated = request({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "municipal_qto_calculate_retaining", "arguments": {"source_file": "demo.dxf", "job_id": "MCP-TEST-001", "project_id": "TEST-PROJECT", "sections": payload["sections"]}}})
                calculated_payload = json.loads(calculated["result"]["content"][0]["text"])
                self.assertEqual(calculated_payload["status"], "REVIEW_REQUIRED")
                jobs = request({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "municipal_qto_list_jobs", "arguments": {}}})
                self.assertEqual(len(json.loads(jobs["result"]["content"][0]["text"])["jobs"]), 1)
                detail = request({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "municipal_qto_get_job", "arguments": {"job_id": "MCP-TEST-001"}}})
                self.assertEqual(json.loads(detail["result"]["content"][0]["text"])["job_id"], "MCP-TEST-001")
                reviewed = request({"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "municipal_qto_review_job", "arguments": {"job_id": "MCP-TEST-001", "reviewer_id": "demo-cost", "reviewer_role": "cost", "decision": "approve", "checked_items": ["source_drawing", "design_basis", "section_parameters", "units_and_rule", "location_scope"], "note": "演示复核", "confirm": True}}})
                reviewed_payload = json.loads(reviewed["result"]["content"][0]["text"])
                self.assertEqual(reviewed_payload["status"], "REVIEWED_PENDING_AUTHORITY")
                self.assertEqual(reviewed_payload["calculation"]["semantic_status"], "Inference")
                self.assertEqual(len(reviewed_payload["review_history"]), 1)
            finally:
                process.terminate()
                process.wait(timeout=10)
                if process.stdin:
                    process.stdin.close()
                if process.stdout:
                    process.stdout.close()
                if process.stderr:
                    process.stderr.close()

    def test_formal_dingtalk_callback_issues_session_after_roster_gate(self) -> None:
        original = {name: getattr(app_server, name) for name in ("APP_MODE", "AUTH_CONFIG", "AUTH_STATES", "AUTH_SESSIONS", "TRUSTED_IDENTITY_PROXY", "DATA", "EVIDENCE", "CAD_JOBS", "DB_FILE")}

        class FakeAuthConfig:
            configured = True
            corp_id = "corp-test"
            redirect_uri = "https://private.example.test/auth/dingtalk/callback"

            def exchange_code(self, code: str) -> str:
                self.last_code = code
                return "token-test"

            def fetch_userinfo(self, access_token: str) -> dict:
                return {
                    "user_id": "union-test",
                    "user_name": "实名测试成员",
                    "corp_id": self.corp_id,
                    "active": True,
                    "real_name_verified": True,
                }

        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder) / "data"
            app_server.APP_MODE = "dingtalk"
            app_server.AUTH_CONFIG = FakeAuthConfig()
            app_server.AUTH_STATES.clear()
            app_server.AUTH_SESSIONS.clear()
            app_server.TRUSTED_IDENTITY_PROXY = False
            app_server.DATA = data
            app_server.EVIDENCE = data / "evidence"
            app_server.CAD_JOBS = data / "cad_jobs"
            app_server.DB_FILE = data / "db.json"
            db = app_server.default_db()
            db["members"][1].update({"user_id": "union-test", "identity_source": "local_demo", "real_name_verified": False})
            app_server.save_db(db)
            app_server.AUTH_STATES["state-test"] = time.time() + 60
            httpd = app_server.ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                class NoRedirect(urllib.request.HTTPRedirectHandler):
                    def redirect_request(self, req, fp, code, msg, headers, newurl):
                        return None

                opener = urllib.request.build_opener(NoRedirect)
                callback = f"http://127.0.0.1:{httpd.server_address[1]}/auth/dingtalk/callback?state=state-test&code=code-test"
                try:
                    opener.open(callback)
                    self.fail("钉钉回调应返回重定向")
                except urllib.error.HTTPError as exc:
                    self.assertEqual(exc.code, 302)
                    session_cookie = exc.headers["Set-Cookie"]
                self.assertIn("HttpOnly", session_cookie)

                request = urllib.request.Request(
                    f"http://127.0.0.1:{httpd.server_address[1]}/api/bootstrap",
                    headers={"Cookie": session_cookie.split(";", 1)[0]},
                )
                with urllib.request.urlopen(request) as response:
                    bootstrap = json.loads(response.read().decode("utf-8"))
                self.assertEqual(response.status, 200)
                self.assertEqual(bootstrap["current_member"]["user_id"], "union-test")
                self.assertEqual(bootstrap["current_member"]["role_code"], "production_manager")
            finally:
                httpd.shutdown()
                httpd.server_close()
        for name, value in original.items():
            setattr(app_server, name, value)

    def test_dxf_inventory_reports_unsupported_entities(self) -> None:
        document = parse_ascii_dxf(FIXTURE)
        inventory = geometry_inventory(document)
        self.assertEqual(inventory["entity_count"], 3)
        self.assertEqual(inventory["unsupported_entity_count"], 1)
        by_layer = {layer["layer"]: layer for layer in inventory["layers"]}
        self.assertEqual(by_layer["挡护结构-挡墙"]["linear_length"], 68.0)
        self.assertEqual(by_layer["挡护结构-排水"]["linear_length"], 30.0)
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
        incomplete = {"job_id": job["job_id"], "reviewer_id": "demo-cost", "reviewer_role": "cost", "decision": "approve", "checked_items": ["source_drawing"], "confirm": True}
        with self.assertRaises(ReviewInputError):
            record_job_review(job, incomplete)
        unconfirmed = {"job_id": job["job_id"], "reviewer_id": "demo-cost", "reviewer_role": "cost", "decision": "return", "checked_items": [], "confirm": False}
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
        self.assertEqual(promoted["calculation"]["review_status"], "已人工审核")

    def test_server_cad_post_persists_job_in_isolated_data_root(self) -> None:
        original = {name: getattr(app_server, name) for name in ("APP_MODE", "DATA", "EVIDENCE", "CAD_JOBS", "DB_FILE")}
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder) / "data"
            app_server.APP_MODE = "local_demo"
            app_server.DATA = data
            app_server.EVIDENCE = data / "evidence"
            app_server.CAD_JOBS = data / "cad_jobs"
            app_server.DB_FILE = data / "db.json"
            httpd = app_server.ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                payload = json.loads(INPUT.read_text(encoding="utf-8"))
                payload["source_file"] = "fixtures/cq_retaining_demo.dxf"
                request = urllib.request.Request(
                    f"http://127.0.0.1:{httpd.server_address[1]}/api/cad/retaining",
                    data=json.dumps({"source_file": payload["source_file"], "sections": payload["sections"]}, ensure_ascii=False).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(request) as response:
                        result = json.loads(response.read().decode("utf-8"))
                except urllib.error.HTTPError as exc:
                    self.fail(f"CAD 接口返回 {exc.code}: {exc.read().decode('utf-8')}")
                self.assertEqual(response.status, 201)
                self.assertEqual(result["summary"]["status"], "REVIEW_REQUIRED")
                self.assertTrue((app_server.CAD_JOBS / f"{result['summary']['job_id']}.json").exists())
                job_id = result["summary"]["job_id"]
                review_request = urllib.request.Request(
                    f"http://127.0.0.1:{httpd.server_address[1]}/api/cad/jobs/{job_id}/review",
                    data=json.dumps({"reviewer_id": "demo-cost", "reviewer_role": "cost", "decision": "approve", "checked_items": ["source_drawing", "design_basis", "section_parameters", "units_and_rule", "location_scope"], "note": "页面复核", "confirm": True}, ensure_ascii=False).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(review_request) as response:
                    reviewed = json.loads(response.read().decode("utf-8"))
                self.assertEqual(response.status, 200)
                self.assertEqual(reviewed["job"]["status"], "REVIEWED_PENDING_AUTHORITY")
                self.assertEqual(reviewed["summary"]["review_status"], "已审核待身份授权")
                with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_address[1]}/api/cad/jobs") as response:
                    jobs = json.loads(response.read().decode("utf-8"))
                self.assertEqual(len(jobs["jobs"]), 1)
                self.assertEqual(jobs["jobs"][0]["status"], "REVIEWED_PENDING_AUTHORITY")
            finally:
                httpd.shutdown()
                httpd.server_close()
        for name, value in original.items():
            setattr(app_server, name, value)


if __name__ == "__main__":
    unittest.main()
