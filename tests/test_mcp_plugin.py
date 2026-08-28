from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "municipal-cad-qto"
MCP_SERVER = PLUGIN / "mcp_server.py"
FIXTURE = "fixtures/cq_retaining_demo.dxf"


def _load_http_module():
    if str(PLUGIN) not in sys.path:
        sys.path.insert(0, str(PLUGIN))
    module_name = "municipal_cad_qto_mcp_http_test"
    spec = importlib.util.spec_from_file_location(module_name, PLUGIN / "mcp_http_server.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 MCP HTTP 模块")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class McpPluginTests(unittest.TestCase):
    def test_plugin_manifests_and_mcp_schema_are_installable(self) -> None:
        codex_manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        mcp_manifest = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))
        marketplace = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(codex_manifest["name"], "municipal-cad-qto")
        self.assertIsInstance(codex_manifest["interface"]["defaultPrompt"], list)
        server = mcp_manifest["mcpServers"]["municipal-cad-qto"]
        self.assertEqual(server["type"], "stdio")
        self.assertEqual(server["cwd"], "${PLUGIN_ROOT}")
        self.assertEqual(server["command"], "python")
        self.assertEqual(marketplace["name"], "municipal-project")
        self.assertEqual(marketplace["plugins"][0]["source"]["path"], "./plugins/municipal-cad-qto")

    def test_stdio_negotiates_and_exposes_dxf_tools(self) -> None:
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "0.1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "municipal_qto_capabilities", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "municipal_qto_inspect_dxf", "arguments": {"source_file": FIXTURE}}},
        ]
        env = os.environ.copy()
        env["MUNICIPAL_QTO_PROJECT_ROOT"] = str(ROOT)
        completed = subprocess.run(
            [sys.executable, str(MCP_SERVER)],
            cwd=ROOT,
            env=env,
            input="\n".join(json.dumps(item, ensure_ascii=False) for item in requests) + "\n",
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
        self.assertEqual(len(responses), 4, completed.stdout)
        self.assertEqual(responses[0]["result"]["protocolVersion"], "2024-11-05")
        names = {tool["name"] for tool in responses[1]["result"]["tools"]}
        self.assertEqual(len(names), 11)
        self.assertIn("municipal_qto_convert_to_dxf", names)
        self.assertIn("municipal_qto_calculate", names)
        self.assertIn("municipal_qto_inspect_dxf_batch", names)
        self.assertIn("municipal_qto_calculate_retaining", names)
        self.assertIn("municipal_qto_review_job", names)
        self.assertIn("municipal_qto_export_job", names)
        capabilities = json.loads(responses[2]["result"]["content"][0]["text"])
        self.assertFalse(capabilities["external_upload"])
        inspection = json.loads(responses[3]["result"]["content"][0]["text"])
        self.assertEqual(inspection["status"], "PARSED")
        self.assertEqual(inspection["geometry_inventory"]["unsupported_entity_count"], 1)

    def test_stdio_calculation_writes_traceable_local_job(self) -> None:
        payload = json.loads((ROOT / "fixtures" / "cq_retaining_demo.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            (project / "fixtures").mkdir()
            shutil.copy2(ROOT / FIXTURE, project / FIXTURE)
            shutil.copytree(ROOT / "cad_qto", project / "cad_qto")
            request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "municipal_qto_calculate_retaining", "arguments": {"source_file": FIXTURE, "sections": payload["sections"]}}}
            env = os.environ.copy()
            env["MUNICIPAL_QTO_PROJECT_ROOT"] = str(project)
            completed = subprocess.run(
                [sys.executable, str(MCP_SERVER)],
                cwd=ROOT,
                env=env,
                input=json.dumps(request, ensure_ascii=False) + "\n",
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            response = json.loads(completed.stdout)
            self.assertFalse(response["result"].get("isError"))
            result = json.loads(response["result"]["content"][0]["text"])
            self.assertEqual(result["status"], "REVIEW_REQUIRED")
            result_path = project / result["result_file"]
            self.assertTrue(result_path.exists())
            stored = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(stored["result_file"], result["result_file"])
            self.assertEqual(stored["source"]["source_file"], FIXTURE)

            export_request = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "municipal_qto_export_job", "arguments": {"job_id": result["job_id"], "format": "xlsx"}}}
            exported = subprocess.run(
                [sys.executable, str(MCP_SERVER)],
                cwd=ROOT,
                env=env,
                input=json.dumps(export_request, ensure_ascii=False) + "\n",
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(exported.returncode, 0, exported.stderr)
            export_response = json.loads(exported.stdout)
            self.assertFalse(export_response["result"].get("isError"))
            export_result = json.loads(export_response["result"]["content"][0]["text"])
            self.assertEqual(export_result["format"], "xlsx")
            self.assertTrue((project / export_result["output_file"]).exists())

    def test_stdio_verified_review_promotes_fact(self) -> None:
        payload = json.loads((ROOT / "fixtures" / "cq_retaining_demo.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            (project / "fixtures").mkdir()
            shutil.copy2(ROOT / FIXTURE, project / FIXTURE)
            shutil.copytree(ROOT / "cad_qto", project / "cad_qto")
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "municipal_qto_calculate_retaining", "arguments": {"source_file": FIXTURE, "job_id": "MCP-REVIEW-001", "sections": payload["sections"]}}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "municipal_qto_review_job", "arguments": {"job_id": "MCP-REVIEW-001", "reviewer_id": "verified-cost", "reviewer_role": "cost", "decision": "approve", "checked_items": ["source_drawing", "design_basis", "section_parameters", "units_and_rule", "location_scope"], "confirm": True}}},
            ]
            env = os.environ.copy()
            env["MUNICIPAL_QTO_PROJECT_ROOT"] = str(project)
            env["MUNICIPAL_QTO_REVIEWER_ID"] = "verified-cost"
            completed = subprocess.run(
                [sys.executable, str(MCP_SERVER)],
                cwd=ROOT,
                env=env,
                input="\n".join(json.dumps(item, ensure_ascii=False) for item in requests) + "\n",
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
            reviewed = json.loads(responses[1]["result"]["content"][0]["text"])
            self.assertEqual(reviewed["status"], "FACT_CONFIRMED")
            self.assertEqual(reviewed["calculation"]["semantic_status"], "Fact")

    def test_stdio_rejects_project_escape(self) -> None:
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "municipal_qto_inspect_dxf", "arguments": {"source_file": "../outside.dxf"}},
        }
        env = os.environ.copy()
        env["MUNICIPAL_QTO_PROJECT_ROOT"] = str(ROOT)
        completed = subprocess.run(
            [sys.executable, str(MCP_SERVER)],
            cwd=ROOT,
            env=env,
            input=json.dumps(request) + "\n",
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        response = json.loads(completed.stdout)
        self.assertTrue(response["result"]["isError"])
        self.assertIn("项目私有根目录", response["result"]["content"][0]["text"])

    def test_http_requires_token_and_tracks_session(self) -> None:
        module = _load_http_module()
        original = {name: os.environ.get(name) for name in ("MUNICIPAL_QTO_PROJECT_ROOT", "MUNICIPAL_QTO_HTTP_TOKEN", "MUNICIPAL_QTO_HTTP_PORT")}
        os.environ["MUNICIPAL_QTO_PROJECT_ROOT"] = str(ROOT)
        os.environ["MUNICIPAL_QTO_HTTP_TOKEN"] = "test-token"
        os.environ["MUNICIPAL_QTO_HTTP_PORT"] = "0"
        httpd = module.create_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            with urllib.request.urlopen(f"{base}/healthz") as response:
                self.assertEqual(response.status, 200)

            initialize = urllib.request.Request(
                f"{base}/mcp",
                data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "0.1"}}}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with self.assertRaises(urllib.error.HTTPError) as unauthorized:
                urllib.request.urlopen(initialize)
            self.assertEqual(unauthorized.exception.code, 401)

            initialize.add_header("Authorization", "Bearer test-token")
            with urllib.request.urlopen(initialize) as response:
                payload = json.loads(response.read().decode("utf-8"))
                session_id = response.headers["Mcp-Session-Id"]
            self.assertEqual(payload["result"]["serverInfo"]["name"], "municipal-cad-qto")

            call = urllib.request.Request(
                f"{base}/mcp",
                data=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "municipal_qto_capabilities", "arguments": {}}}).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": "Bearer test-token", "Mcp-Session-Id": session_id},
            )
            with urllib.request.urlopen(call) as response:
                result = json.loads(response.read().decode("utf-8"))
            self.assertFalse(result.get("error"))

            invalid = urllib.request.Request(
                f"{base}/mcp",
                data=json.dumps({"jsonrpc": "2.0", "id": 3, "method": "ping", "params": {}}).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": "Bearer test-token", "Mcp-Session-Id": "invalid"},
            )
            with self.assertRaises(urllib.error.HTTPError) as invalid_session:
                urllib.request.urlopen(invalid)
            self.assertEqual(invalid_session.exception.code, 404)
        finally:
            httpd.shutdown()
            httpd.server_close()
            for name, value in original.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
