from __future__ import annotations

import json
import mimetypes
import os
import re
import threading
import uuid
from datetime import datetime
from email.parser import BytesParser
from email.policy import default as default_email_policy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from cad_qto.canonical import canonicalize_dxf, sha256_file
from cad_qto.conversion import ConversionError, SUPPORTED_INPUT_EXTENSIONS, convert_to_dxf
from cad_qto.dxf import geometry_inventory, parse_ascii_dxf
from cad_qto.export import ExportError, export_pdf, export_xlsx
from cad_qto.job import QtoJobError, run_job
from cad_qto.review import REVIEW_PROTOCOL_VERSION, ReviewInputError, record_job_review, write_job_atomic

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
DATA = ROOT / "data"
CAD_JOBS = DATA / "cad_jobs"
CAD_INPUTS = DATA / "cad_inputs"
CAD_EXPORTS = DATA / "cad_exports"
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
        "version": "0.4.0",
        "input_formats": ["ASCII DXF（默认）", "PDF（本地矢量转 DXF）", "DWG（本地转换器转 DXF）"],
        "file_entry": {"single": True, "multiple": True, "accepted_extensions": [".dxf", ".pdf", ".dwg"], "default_extension": ".dxf"},
        "conversion": {"local_only": True, "target_format": ".dxf", "pdf_method": "PyMuPDF 矢量图元提取", "dwg_method": "本机 ODA File Converter / ezdxf odafc", "scan_pdf_auto_ocr": False},
        "exports": [{"format": "xlsx", "label": "Excel 工程量成果"}, {"format": "pdf", "label": "PDF 工程量成果"}],
        "canonical_output": "ASCII DXF（保守实体子集）",
        "supported_entities": ["LINE", "LWPOLYLINE", "TEXT", "MTEXT"],
        "disciplines": ["road", "network", "retaining"],
        "rule_pack_versions": ["cq-municipal-road-v0.1", "cq-municipal-network-v0.1", "cq-municipal-retaining-v0.1"],
        "review_protocol_version": REVIEW_PROTOCOL_VERSION,
        "review_states": ["REVIEW_REQUIRED", "REVIEWED_PENDING_AUTHORITY", "FACT_CONFIRMED", "RETURNED", "REJECTED"],
        "road_scope": ["路面面积/体积", "基层", "底基层", "路基挖方", "路基填方", "路缘石", "人行道铺装"],
        "network_scope": ["管道长度", "管沟开挖", "垫层", "管道占用体积", "管沟回填", "检查井", "雨水口", "路面恢复"],
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


def project_paths(values: object) -> list[Path]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list) or not values:
        raise ValueError("至少需要一个项目内 DXF 文件；PDF/DWG 请先在文件入口本地转换")
    if len(values) > 50:
        raise ValueError("单次最多使用 50 个 DXF 文件")
    paths = [project_path(value) for value in values]
    if any(path.suffix.lower() != ".dxf" for path in paths):
        raise ValueError("算量核心只接收 DXF；PDF/DWG 必须先通过本地转换入口生成 DXF")
    return paths


def path_label(value: str | Path) -> str:
    path = Path(value).resolve()
    try:
        return str(path.relative_to(ROOT.resolve()))
    except ValueError:
        return "PROJECT_PRIVATE_STORAGE"


def inspect_dxf(source: Path) -> dict:
    if source.suffix.lower() != ".dxf":
        raise ValueError("图纸检查需要 DXF；PDF/DWG 请先在本地转换为 DXF")
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
        "warning_count": len(source.get("warnings", [])) + len(source.get("conversion_warnings", [])) + len(calculation.get("warnings", [])),
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


def list_input_files() -> list[dict]:
    files: list[dict] = []
    if not CAD_INPUTS.exists():
        return files
    candidates = [item for item in CAD_INPUTS.iterdir() if item.is_file() and item.suffix.lower() in SUPPORTED_INPUT_EXTENSIONS and not item.name.endswith(".converted.dxf")]
    for source in sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            converted = source if source.suffix.lower() == ".dxf" else source.with_name(f"{source.stem}.converted.dxf")
            converted_exists = converted.exists() and converted.is_file()
            source_for_calculation = converted if converted_exists else source
            files.append({
                "source_file": path_label(source_for_calculation),
                "original_file": path_label(source),
                "converted_file": path_label(converted) if converted_exists else "",
                "original_name": source.name.split("-", 1)[-1],
                "input_format": source.suffix.lower().lstrip("."),
                "size_bytes": source.stat().st_size,
                "original_sha256": sha256_file(source),
                "source_sha256": sha256_file(source_for_calculation) if converted_exists else sha256_file(source),
                "conversion_status": "NOT_NEEDED" if source.suffix.lower() == ".dxf" else ("CONVERTED" if converted_exists else "FAILED"),
                "conversion_method": "identity" if source.suffix.lower() == ".dxf" else (("local-pymupdf-vector-extraction" if source.suffix.lower() == ".pdf" else "local-ezdxf-odafc") if converted_exists else "unavailable"),
                "created_at": datetime.fromtimestamp(source.stat().st_mtime).isoformat(timespec="seconds"),
            })
        except OSError:
            continue
    return files


class Handler(BaseHTTPRequestHandler):
    server_version = "MunicipalCadQto/0.4"

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

    def read_uploads(self) -> list[tuple[str, bytes]]:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            raise ValueError("文件录入必须使用 multipart/form-data")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Content-Length 不合法") from exc
        if length <= 0 or length > 50 * 1024 * 1024:
            raise ValueError("文件录入总大小必须在 1B 到 50MB 之间")
        raw = self.rfile.read(length)
        envelope = (
            f"Content-Type: {content_type}\r\n"
            "MIME-Version: 1.0\r\n"
            "\r\n"
        ).encode("utf-8") + raw
        message = BytesParser(policy=default_email_policy).parsebytes(envelope)
        uploads: list[tuple[str, bytes]] = []
        for part in message.iter_parts():
            filename = part.get_filename()
            field_name = part.get_param("name", header="content-disposition")
            if field_name != "files" or not filename:
                continue
            payload = part.get_payload(decode=True) or b""
            uploads.append((filename, payload))
        if not uploads:
            raise ValueError("没有读取到文件字段 files")
        return uploads

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            try:
                self.api_get(parsed.path, parse_qs(parsed.query))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        if not self.path.startswith("/api/"):
            self.send_json({"error": "不支持的请求"}, HTTPStatus.NOT_FOUND)
            return
        try:
            with JOB_LOCK:
                path = urlparse(self.path).path
                if path == "/api/cad/files":
                    self.upload_cad_files()
                else:
                    self.api_post(path, self.read_json())
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

    def send_download(self, path: Path, content_type: str, download_name: str) -> None:
        raw = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def api_get(self, path: str, query: dict[str, list[str]] | None = None) -> None:
        if path in {"/api/bootstrap", "/api/cad/status"}:
            payload = {"project": project_info(), **capabilities()} if path == "/api/bootstrap" else {"project_id": PROJECT_ID, **capabilities()}
            self.send_json(payload)
            return
        if path == "/api/cad/jobs":
            self.send_json({"jobs": list_jobs(), "data_classification": "PRIVATE_PROJECT_DATA"})
            return
        if path == "/api/cad/files":
            self.send_json({"files": list_input_files(), "data_classification": "PRIVATE_PROJECT_DATA"})
            return
        if path.startswith("/api/cad/jobs/") and path.endswith("/export"):
            job_id = path.split("/")[4]
            safe_job_id(job_id)
            result_path = CAD_JOBS / f"{job_id}.json"
            if not result_path.exists():
                self.send_json({"error": "算量作业不存在"}, HTTPStatus.NOT_FOUND)
                return
            export_format = ((query or {}).get("format") or ["xlsx"])[0].lower()
            if export_format not in {"xlsx", "pdf"}:
                self.send_json({"error": "成果格式只支持 xlsx 或 pdf"}, HTTPStatus.BAD_REQUEST)
                return
            job = json.loads(result_path.read_text(encoding="utf-8"))
            CAD_EXPORTS.mkdir(parents=True, exist_ok=True)
            export_path = CAD_EXPORTS / f"{job_id}.{export_format}"
            if export_format == "xlsx":
                export_xlsx(job, export_path)
                content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            else:
                export_pdf(job, export_path)
                content_type = "application/pdf"
            self.send_download(export_path, content_type, f"{job_id}-cad-qto.{export_format}")
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
            self.send_json({"ok": True, "service": "municipal-cad-qto", "version": "0.4.0"})
            return
        self.send_json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)

    def api_post(self, path: str, body: dict) -> None:
        if path == "/api/cad/inspect-batch":
            inspections = []
            for source in project_paths(body.get("source_files")):
                try:
                    inspections.append(inspect_dxf(source))
                except (OSError, ValueError) as exc:
                    inspections.append({"status": "ERROR", "source_file": path_label(source), "error": str(exc), "review_required": True})
            self.send_json({"ok": True, "inspections": inspections})
            return
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
        if path == "/api/cad/convert":
            source = project_path(body.get("source_file"))
            if source.suffix.lower() not in {".pdf", ".dwg", ".dxf"}:
                raise ConversionError("本地转换只支持 DXF、PDF、DWG")
            output_value = str(body.get("output_file", "")).strip() or f"data/cad_inputs/{source.stem}.converted.dxf"
            output = project_path(output_value, must_exist=False)
            manifest = convert_to_dxf(source, output)
            inspection = inspect_dxf(output if source.suffix.lower() != ".dxf" else source)
            manifest["source_file"] = path_label(source)
            manifest["converted_file"] = path_label(output if source.suffix.lower() != ".dxf" else source)
            manifest["inspection"] = inspection
            self.send_json({"ok": True, "manifest": manifest})
            return
        if path in {"/api/cad/calculate", "/api/cad/retaining"}:
            self.create_cad_jobs(body)
            return
        if path.startswith("/api/cad/jobs/") and path.endswith("/review"):
            self.review_cad_job(path.rsplit("/", 2)[-2], body)
            return
        self.send_json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)

    def upload_cad_files(self) -> None:
        CAD_INPUTS.mkdir(parents=True, exist_ok=True)
        stored: list[dict[str, Any]] = []
        created_paths: list[Path] = []
        try:
            for original_name, payload in self.read_uploads():
                filename = Path(original_name).name
                extension = Path(filename).suffix.lower()
                if extension not in SUPPORTED_INPUT_EXTENSIONS:
                    raise ValueError(f"不支持的文件类型：{filename}；仅支持 DXF、PDF、DWG")
                if not payload:
                    raise ValueError(f"文件为空：{filename}")
                safe_name = re.sub(r"[^A-Za-z0-9_.\-\u4e00-\u9fff]+", "_", Path(filename).stem).strip("._") or "drawing"
                token = uuid.uuid4().hex[:10]
                original_target = CAD_INPUTS / f"{token}-{safe_name}{extension}"
                original_target.write_bytes(payload)
                created_paths.append(original_target)
                converted_target = original_target if extension == ".dxf" else CAD_INPUTS / f"{token}-{safe_name}.converted.dxf"
                if extension != ".dxf":
                    created_paths.append(converted_target)
                conversion = convert_to_dxf(original_target, converted_target if extension != ".dxf" else None)
                calculation_source = converted_target if extension != ".dxf" else original_target
                inspection = inspect_dxf(calculation_source)
                stored.append({
                    "source_file": path_label(calculation_source),
                    "original_file": path_label(original_target),
                    "converted_file": path_label(calculation_source),
                    "original_name": filename,
                    "input_format": extension.lstrip("."),
                    "size_bytes": len(payload),
                    "original_sha256": sha256_file(original_target),
                    "source_sha256": inspection["source_sha256"],
                    "conversion_status": conversion["status"],
                    "conversion_method": conversion["method"],
                    "conversion_warnings": conversion.get("warnings", []),
                    "status": inspection["status"],
                })
        except Exception:
            for path in created_paths:
                path.unlink(missing_ok=True)
            raise
        self.send_json({"ok": True, "files": stored, "data_classification": "PRIVATE_PROJECT_DATA"}, HTTPStatus.CREATED)

    def conversion_metadata(self, source: Path) -> dict[str, Any]:
        if not source.name.endswith(".converted.dxf"):
            return {"original_file": path_label(source), "original_sha256": sha256_file(source), "converted_file": path_label(source), "conversion_status": "NOT_NEEDED", "conversion_method": "identity", "conversion_warnings": []}
        stem = source.name[: -len(".converted.dxf")]
        original = next((source.with_name(f"{stem}{extension}") for extension in (".pdf", ".dwg") if source.with_name(f"{stem}{extension}").exists()), None)
        if original is None:
            return {"converted_file": path_label(source), "conversion_status": "CONVERTED", "conversion_method": "local", "conversion_warnings": ["未找到转换前原文件，建议人工检查本地文件留存"]}
        method = "local-pymupdf-vector-extraction" if original.suffix.lower() == ".pdf" else "local-ezdxf-odafc"
        return {"original_file": path_label(original), "original_sha256": sha256_file(original), "converted_file": path_label(source), "conversion_status": "CONVERTED", "conversion_method": method, "conversion_warnings": []}

    def create_cad_jobs(self, body: dict) -> None:
        source_values = body.get("source_files")
        if source_values is None:
            source_values = [body.get("source_file")]
        sources = project_paths(source_values)
        if len(sources) > 1 and body.get("job_id"):
            base_job_id = safe_job_id(body.get("job_id"))
        else:
            base_job_id = ""
        results: list[dict[str, Any]] = []
        for index, source in enumerate(sources, start=1):
            job_id = safe_job_id(base_job_id) if len(sources) == 1 else safe_job_id(f"{base_job_id or 'CAD'}-{index:03d}-{uuid.uuid4().hex[:6].upper()}")
            CAD_JOBS.mkdir(parents=True, exist_ok=True)
            canonical_path = CAD_JOBS / f"{job_id}.canonical.dxf"
            result = run_job({
                "job_id": job_id,
                "project_id": PROJECT_ID,
                "source_file": str(source),
                "rule_pack_version": body.get("rule_pack_version", ""),
                "road_rule_pack_version": body.get("road_rule_pack_version", "cq-municipal-road-v0.1"),
                "network_rule_pack_version": body.get("network_rule_pack_version", "cq-municipal-network-v0.1"),
                "retaining_rule_pack_version": body.get("retaining_rule_pack_version", "cq-municipal-retaining-v0.1"),
                "road_sections": body.get("road_sections", []),
                "network_sections": body.get("network_sections", []),
                "retaining_sections": body.get("retaining_sections", body.get("sections", [])),
            }, canonical_path=canonical_path)
            result["source"]["source_file"] = path_label(source)
            result["source"]["canonical_file"] = path_label(canonical_path)
            result["source"].update(self.conversion_metadata(source))
            result["input_snapshot"]["source_conversion"] = {key: value for key, value in result["source"].items() if key.startswith("original_") or key.startswith("converted_") or key.startswith("conversion_")}
            result_file = CAD_JOBS / f"{job_id}.json"
            write_job_atomic(result_file, result)
            results.append({"job": result, "summary": job_summary(result, path_label(result_file))})
        if len(results) == 1:
            self.send_json({"ok": True, **results[0]}, HTTPStatus.CREATED)
        else:
            self.send_json({"ok": True, "jobs": [item["job"] for item in results], "summaries": [item["summary"] for item in results], "count": len(results)}, HTTPStatus.CREATED)

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
    CAD_INPUTS.mkdir(exist_ok=True)
    CAD_EXPORTS.mkdir(exist_ok=True)
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
