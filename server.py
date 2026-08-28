from __future__ import annotations

import json
import mimetypes
import os
import re
import threading
import uuid
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from cad_qto.canonical import canonicalize_dxf, sha256_file
from cad_qto.dxf import geometry_inventory, parse_ascii_dxf
from cad_qto.job import QtoJobError, run_job
from cad_qto.review import REVIEW_PROTOCOL_VERSION, ReviewInputError, record_job_review, write_job_atomic

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
DATA = ROOT / "data"
CAD_JOBS = DATA / "cad_jobs"
HOST = os.environ.get("MUNICIPAL_QTO_HOST", "127.0.0.1").strip() or "127.0.0.1"
PORT = int(os.environ.get("MUNICIPAL_QTO_PORT", "8765"))
PROJECT_ID = os.environ.get("MUNICIPAL_QTO_PROJECT_ID", "CQ-MUNICIPAL-CAD-QTO").strip() or "CQ-MUNICIPAL-CAD-QTO"
PROJECT_NAME = os.environ.get("MUNICIPAL_QTO_PROJECT_NAME", "重庆市政 CAD 工程量计算（造价算量）").strip() or "重庆市政 CAD 工程量计算（造价算量）"
REVIEWER_ID = os.environ.get("MUNICIPAL_QTO_REVIEWER_ID", "").strip() or None
JOB_LOCK = threading.RLock()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


def project_info() -> dict[str, str]:
    return {"project_id": PROJECT_ID, "project_name": PROJECT_NAME, "scope": "PROJECT_PRIVATE"}


def capabilities() -> dict:
    return {
        "server": "municipal-cad-qto",
        "version": "0.2.0",
        "input_formats": ["ASCII DXF"],
        "canonical_output": "ASCII DXF（保守实体子集）",
        "supported_entities": ["LINE", "LWPOLYLINE", "TEXT", "MTEXT"],
        "rule_pack_versions": ["cq-municipal-retaining-v0.1"],
        "review_protocol_version": REVIEW_PROTOCOL_VERSION,
        "review_states": ["REVIEW_REQUIRED", "REVIEWED_PENDING_AUTHORITY", "FACT_CONFIRMED", "RETURNED", "REJECTED"],
        "retaining_scope": ["墙身", "基础", "开挖", "回填", "泄水孔", "反滤层", "锚杆/锚索", "抗滑桩", "喷射混凝土", "钢筋网"],
        "semantic_status": "Hypothesis",
        "calculation_status": "Inference",
        "review_required": True,
        "external_upload": False,
    }


def safe_job_id(value: str) -> str:
    job_id = str(value or "").strip()
    if not job_id:
        return new_id("CAD")
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,80}", job_id):
        raise ValueError("算量作业编号不合法")
    return job_id


def project_path(value: str, *, must_exist: bool = True) -> Path:
    raw = str(value or "").strip()
    candidate = Path(raw)
    if not raw or candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("图纸路径必须是项目根目录内的相对路径")
    resolved = (ROOT / candidate).resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError("图纸路径必须位于项目私有根目录内") from exc
    if must_exist and (not resolved.exists() or not resolved.is_file()):
        raise ValueError(f"图纸文件不存在：{raw}")
    return resolved


def path_label(value: str | Path) -> str:
    path = Path(value).resolve()
    try:
        return str(path.relative_to(ROOT.resolve()))
    except ValueError:
        return "PROJECT_PRIVATE_STORAGE"


def inspect_dxf(source: Path) -> dict:
    if source.suffix.lower() != ".dxf":
        raise ValueError("当前工具只接受 .dxf；不要把 PDF/IFC/LandXML 当作 DXF")
    document = parse_ascii_dxf(source)
    return {
        "status": "PARSED",
        "source_file": path_label(source),
        "source_sha256": sha256_file(source),
        "geometry_inventory": geometry_inventory(document),
        "review_required": bool(document.unsupported_entities),
    }


def job_summary(job: dict, result_file: str = "") -> dict:
    source = job.get("source", {})
    calculation = job.get("calculation", {})
    return {
        "job_id": job.get("job_id", ""),
        "project_id": job.get("project_id", PROJECT_ID),
        "source_file": source.get("source_file", "PROJECT_PRIVATE_STORAGE"),
        "canonical_file": source.get("canonical_file", "PROJECT_PRIVATE_STORAGE"),
        "result_file": result_file,
        "source_sha256": source.get("source_sha256", ""),
        "canonical_sha256": source.get("canonical_sha256", ""),
        "rule_pack_version": calculation.get("rule_pack_version", ""),
        "status": job.get("status", ""),
        "review_status": calculation.get("review_status", ""),
        "warning_count": len(source.get("warnings", [])) + len(calculation.get("warnings", [])),
        "quantity_count": len(calculation.get("quantities", [])),
        "created_at": job.get("created_at", ""),
    }


def list_jobs() -> list[dict]:
    jobs: list[dict] = []
    if not CAD_JOBS.exists():
        return jobs
    for result_path in sorted(CAD_JOBS.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            job = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        jobs.append(job_summary(job, path_label(result_path)))
    return jobs


class Handler(BaseHTTPRequestHandler):
    server_version = "MunicipalCadQto/0.2"

    def log_message(self, fmt: str, *args) -> None:
        print(fmt % args)

    def send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Content-Length 不合法") from exc
        if length < 0 or length > 12 * 1024 * 1024:
            raise ValueError("请求数据过大")
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if not isinstance(payload, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return payload

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            try:
                self.api_get(parsed.path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        if not self.path.startswith("/api/"):
            self.send_json({"error": "不支持的请求"}, HTTPStatus.NOT_FOUND)
            return
        try:
            body = self.read_json()
            with JOB_LOCK:
                self.api_post(urlparse(self.path).path, body)
        except (OSError, QtoJobError, ReviewInputError, ValueError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.send_json({"error": f"服务处理失败：{exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def serve_static(self, path: str) -> None:
        relative = path.lstrip("/") or "index.html"
        if ".." in Path(relative).parts:
            self.send_json({"error": "非法路径"}, HTTPStatus.BAD_REQUEST)
            return
        target = (WEB / relative).resolve()
        if WEB.resolve() not in target.parents and target != WEB.resolve():
            self.send_json({"error": "非法路径"}, HTTPStatus.BAD_REQUEST)
            return
        if not target.exists() or not target.is_file():
            self.send_json({"error": "页面不存在"}, HTTPStatus.NOT_FOUND)
            return
        content = target.read_bytes()
        mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{mime}; charset=utf-8" if mime.startswith("text/") else mime)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def api_get(self, path: str) -> None:
        if path in {"/api/bootstrap", "/api/cad/status"}:
            payload = {"project": project_info(), **capabilities()} if path == "/api/bootstrap" else {"project_id": PROJECT_ID, **capabilities()}
            self.send_json(payload)
            return
        if path == "/api/cad/jobs":
            self.send_json({"jobs": list_jobs(), "data_classification": "PRIVATE_PROJECT_DATA"})
            return
        if path.startswith("/api/cad/jobs/"):
            job_id = path.rsplit("/", 1)[-1]
            if not re.fullmatch(r"[A-Za-z0-9_-]{4,80}", job_id):
                self.send_json({"error": "算量作业编号不合法"}, HTTPStatus.BAD_REQUEST)
                return
            result_path = CAD_JOBS / f"{job_id}.json"
            if not result_path.exists():
                self.send_json({"error": "算量作业不存在"}, HTTPStatus.NOT_FOUND)
                return
            self.send_json(json.loads(result_path.read_text(encoding="utf-8")))
            return
        if path == "/api/healthz":
            self.send_json({"ok": True, "service": "municipal-cad-qto", "version": "0.2.0"})
            return
        self.send_json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)

    def api_post(self, path: str, body: dict) -> None:
        if path == "/api/cad/inspect":
            source = project_path(body.get("source_file"))
            self.send_json({"ok": True, "inspection": inspect_dxf(source)})
            return
        if path == "/api/cad/normalize":
            source = project_path(body.get("source_file"))
            output_value = str(body.get("output_file", "")).strip() or f"data/cad_jobs/{source.stem}.canonical.dxf"
            output = project_path(output_value, must_exist=False)
            manifest = canonicalize_dxf(source, output)
            manifest["source_file"] = path_label(source)
            manifest["canonical_file"] = path_label(output)
            self.send_json({"ok": True, "manifest": manifest})
            return
        if path == "/api/cad/retaining":
            self.create_cad_job(body)
            return
        if path.startswith("/api/cad/jobs/") and path.endswith("/review"):
            self.review_cad_job(path.rsplit("/", 2)[-2], body)
            return
        self.send_json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)

    def create_cad_job(self, body: dict) -> None:
        source = project_path(body.get("source_file"))
        if source.suffix.lower() != ".dxf":
            raise ValueError("当前工具只接受 .dxf")
        job_id = safe_job_id(body.get("job_id"))
        CAD_JOBS.mkdir(parents=True, exist_ok=True)
        canonical_path = CAD_JOBS / f"{job_id}.canonical.dxf"
        result = run_job({
            "job_id": job_id,
            "project_id": PROJECT_ID,
            "source_file": str(source),
            "rule_pack_version": body.get("rule_pack_version", "cq-municipal-retaining-v0.1"),
            "sections": body.get("sections", []),
        }, canonical_path=canonical_path)
        result["source"]["source_file"] = path_label(source)
        result["source"]["canonical_file"] = path_label(canonical_path)
        result_file = CAD_JOBS / f"{job_id}.json"
        write_job_atomic(result_file, result)
        summary = job_summary(result, path_label(result_file))
        self.send_json({"ok": True, "job": result, "summary": summary}, HTTPStatus.CREATED)

    def review_cad_job(self, job_id: str, body: dict) -> None:
        safe_job_id(job_id)
        result_path = CAD_JOBS / f"{job_id}.json"
        if not result_path.exists():
            self.send_json({"error": "算量作业不存在"}, HTTPStatus.NOT_FOUND)
            return
        job = json.loads(result_path.read_text(encoding="utf-8"))
        review_input = dict(body)
        review_input.setdefault("job_id", job_id)
        reviewed = record_job_review(job, review_input, verified_reviewer_id=REVIEWER_ID)
        write_job_atomic(result_path, reviewed)
        self.send_json({"ok": True, "job": reviewed, "summary": job_summary(reviewed, path_label(result_path))})


def main() -> None:
    DATA.mkdir(exist_ok=True)
    CAD_JOBS.mkdir(exist_ok=True)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"重庆市政 CAD 工程量计算服务运行中：http://{HOST}:{PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
