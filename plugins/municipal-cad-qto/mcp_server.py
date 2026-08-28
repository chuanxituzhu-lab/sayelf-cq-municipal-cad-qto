from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _resolve_root(raw: str) -> Path:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = Path(__file__).resolve().parent / candidate
    return candidate.resolve()


_configured_root = os.environ.get("MUNICIPAL_QTO_PROJECT_ROOT", "").strip()
_default_root = _resolve_root(_configured_root) if _configured_root else Path(__file__).resolve().parents[2]
if str(_default_root) not in sys.path:
    sys.path.insert(0, str(_default_root))

from cad_qto.canonical import canonicalize_dxf, sha256_file  # noqa: E402
from cad_qto.dxf import geometry_inventory, parse_ascii_dxf  # noqa: E402
from cad_qto.job import QtoJobError, run_job  # noqa: E402
from cad_qto.review import ReviewInputError, record_job_review, write_job_atomic  # noqa: E402


SERVER_NAME = "municipal-cad-qto"
SERVER_VERSION = "0.2.0"
PROTOCOL_VERSION = "2024-11-05"
SERVER_INSTRUCTIONS = (
    "这是本地优先的重庆市政 CAD 工程量辅助工具。只接受项目私有目录内的 ASCII DXF；"
    "图层识别是 Hypothesis，公式计算是 Inference，必须人工审核后才能成为 Fact。"
    "不得覆盖原图、不得越权读取项目目录外文件、不得上传真实工程资料。"
    "复核工具必须明确 confirm=true；未配置本地审核身份时只能记录待授权状态。"
)


def project_root() -> Path:
    configured = os.environ.get("MUNICIPAL_QTO_PROJECT_ROOT", "").strip()
    return _resolve_root(configured) if configured else _default_root


def _path(value: Any) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("缺少项目内相对路径")
    candidate = Path(raw)
    root = project_root()
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PermissionError("路径必须位于项目私有根目录内") from exc
    return resolved


def _label(path: str | Path) -> str:
    try:
        return Path(path).resolve().relative_to(project_root()).as_posix()
    except ValueError:
        return "PROJECT_PRIVATE_STORAGE"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _success(value: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": _json(value)}], "structuredContent": value}


def _failure(message: str) -> dict[str, Any]:
    return {"isError": True, "content": [{"type": "text", "text": message}]}


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str], *, read_only: bool, idempotent: bool) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": properties, "required": required, "additionalProperties": False},
        "annotations": {"readOnlyHint": read_only, "destructiveHint": False, "idempotentHint": idempotent, "openWorldHint": False},
    }


TOOLS = [
    _tool("municipal_qto_capabilities", "读取本地算量核心的支持范围、规则版本和数据边界。", {}, [], read_only=True, idempotent=True),
    _tool("municipal_qto_inspect_dxf", "只读检查项目内 ASCII DXF 的支持实体、图层、文字、单位和未支持实体。", {"source_file": {"type": "string", "description": "项目根目录内的 DXF 相对路径"}}, ["source_file"], read_only=True, idempotent=True),
    _tool("municipal_qto_normalize_dxf", "在项目私有目录内生成标准化 DXF 副本，不覆盖原图。", {"source_file": {"type": "string", "description": "项目根目录内的 DXF 相对路径"}, "output_file": {"type": "string", "description": "可选，项目根目录内的输出相对路径"}}, ["source_file"], read_only=False, idempotent=True),
    _tool("municipal_qto_calculate_retaining", "按人工确认的挡护结构断面参数计算工程量草稿，并保存带证据的本地作业。", {"source_file": {"type": "string", "description": "项目根目录内的 DXF 相对路径"}, "sections": {"type": "array", "description": "人工确认的挡护结构断面参数数组", "items": {"type": "object"}}, "job_id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{4,80}$", "description": "可选、稳定的本地作业编号"}, "project_id": {"type": "string", "description": "可选的单项目编号"}, "rule_pack_version": {"type": "string", "description": "可选规则包版本"}}, ["source_file", "sections"], read_only=False, idempotent=False),
    _tool("municipal_qto_list_jobs", "列出项目私有目录内的算量作业摘要。", {}, [], read_only=True, idempotent=True),
    _tool("municipal_qto_get_job", "读取指定算量作业的完整公式、输入、哈希、告警和审核状态。", {"job_id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{4,80}$"}}, ["job_id"], read_only=True, idempotent=True),
    _tool("municipal_qto_review_job", "按人工确认清单记录算量作业复核；只有本地已认证审核人才能把 Inference 提升为 Fact。", {"job_id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{4,80}$"}, "reviewer_id": {"type": "string", "description": "审核人标识；正式模式必须与本地已认证身份一致"}, "reviewer_role": {"type": "string", "enum": ["production", "technical", "cost"]}, "decision": {"type": "string", "enum": ["approve", "return", "reject"]}, "checked_items": {"type": "array", "items": {"type": "string", "enum": ["source_drawing", "design_basis", "section_parameters", "units_and_rule", "location_scope"]}}, "note": {"type": "string", "description": "审核备注"}, "evidence_refs": {"type": "array", "items": {"type": "string"}, "description": "项目内证据相对引用"}, "confirm": {"type": "boolean", "description": "必须明确为 true"}}, ["job_id", "reviewer_id", "reviewer_role", "decision", "checked_items", "confirm"], read_only=False, idempotent=False),
]


def _capabilities() -> dict[str, Any]:
    return {
        "server": SERVER_NAME,
        "version": SERVER_VERSION,
        "transport": ["stdio", "streamable-http"],
        "project_root": "PROJECT_PRIVATE_STORAGE",
        "input_formats": ["ASCII DXF"],
        "supported_entities": ["LINE", "LWPOLYLINE", "TEXT", "MTEXT"],
        "rule_pack_versions": ["cq-municipal-retaining-v0.1"],
        "review_protocol_version": "cq-municipal-review-v0.1",
        "review_states": ["REVIEW_REQUIRED", "REVIEWED_PENDING_AUTHORITY", "FACT_CONFIRMED", "RETURNED", "REJECTED"],
        "retaining_scope": ["墙身", "基础", "开挖", "回填", "泄水孔", "反滤层", "锚杆/锚索", "抗滑桩", "喷射混凝土", "钢筋网"],
        "semantic_status": "Hypothesis",
        "calculation_status": "Inference",
        "review_required": True,
        "external_upload": False,
    }


def _inspect(args: dict[str, Any]) -> dict[str, Any]:
    source = _path(args.get("source_file"))
    if source.suffix.lower() != ".dxf":
        raise ValueError("当前工具只接受 .dxf；不要强行把 PDF/IFC/LandXML 当作 DXF")
    document = parse_ascii_dxf(source)
    return {
        "status": "PARSED",
        "source_file": _label(source),
        "source_sha256": sha256_file(source),
        "geometry_inventory": geometry_inventory(document),
        "review_required": bool(document.unsupported_entities),
    }


def _normalize(args: dict[str, Any]) -> dict[str, Any]:
    source = _path(args.get("source_file"))
    if source.suffix.lower() != ".dxf":
        raise ValueError("当前工具只接受 .dxf")
    output_value = str(args.get("output_file", "")).strip() or f"data/cad_jobs/{source.stem}.canonical.dxf"
    output = _path(output_value)
    manifest = canonicalize_dxf(source, output)
    manifest["source_file"] = _label(source)
    manifest["canonical_file"] = _label(output)
    return manifest


def _calculate(args: dict[str, Any]) -> dict[str, Any]:
    source = _path(args.get("source_file"))
    if source.suffix.lower() != ".dxf":
        raise ValueError("当前工具只接受 .dxf")
    job_id = str(args.get("job_id", "")).strip() or f"MCP-CAD-{sha256_file(source)[:10].upper()}"
    jobs_dir = project_root() / "data" / "cad_jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    canonical = jobs_dir / f"{job_id}.canonical.dxf"
    result = run_job({
        "job_id": job_id,
        "project_id": str(args.get("project_id", "")).strip(),
        "source_file": str(source),
        "rule_pack_version": args.get("rule_pack_version", "cq-municipal-retaining-v0.1"),
        "sections": args.get("sections", []),
    }, canonical_path=canonical)
    result["source"]["source_file"] = _label(source)
    result["source"]["canonical_file"] = _label(canonical)
    result_path = jobs_dir / f"{job_id}.json"
    result["result_file"] = _label(result_path)
    write_job_atomic(result_path, result)
    return result


def _list_jobs() -> dict[str, Any]:
    jobs_dir = project_root() / "data" / "cad_jobs"
    jobs: list[dict[str, Any]] = []
    if jobs_dir.exists():
        for result_path in sorted(jobs_dir.glob("*.json")):
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            calculation = result.get("calculation", {})
            source = result.get("source", {})
            jobs.append({
                "job_id": result.get("job_id", result_path.stem),
                "status": result.get("status", ""),
                "review_status": calculation.get("review_status", ""),
                "source_file": source.get("source_file", "PROJECT_PRIVATE_STORAGE"),
                "rule_pack_version": calculation.get("rule_pack_version", ""),
                "warning_count": len(source.get("warnings", [])) + len(calculation.get("warnings", [])),
                "quantity_count": len(calculation.get("quantities", [])),
                "created_at": result.get("created_at", ""),
            })
    return {"jobs": jobs, "data_classification": "PRIVATE_PROJECT_DATA"}


def _get_job(args: dict[str, Any]) -> dict[str, Any]:
    job_id = str(args.get("job_id", "")).strip()
    if not job_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in job_id) or not 4 <= len(job_id) <= 80:
        raise ValueError("算量作业编号不合法")
    result_path = project_root() / "data" / "cad_jobs" / f"{job_id}.json"
    if not result_path.exists():
        raise FileNotFoundError("算量作业不存在")
    return json.loads(result_path.read_text(encoding="utf-8"))


def _review(args: dict[str, Any]) -> dict[str, Any]:
    job_id = str(args.get("job_id", "")).strip()
    job = _get_job({"job_id": job_id})
    reviewer_identity = os.environ.get("MUNICIPAL_QTO_REVIEWER_ID", "").strip() or None
    reviewed = record_job_review(job, args, verified_reviewer_id=reviewer_identity)
    result_path = project_root() / "data" / "cad_jobs" / f"{job_id}.json"
    write_job_atomic(result_path, reviewed)
    return reviewed


def call_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    try:
        if name == "municipal_qto_capabilities":
            return _success(_capabilities())
        if name == "municipal_qto_inspect_dxf":
            return _success(_inspect(args))
        if name == "municipal_qto_normalize_dxf":
            return _success(_normalize(args))
        if name == "municipal_qto_calculate_retaining":
            return _success(_calculate(args))
        if name == "municipal_qto_list_jobs":
            return _success(_list_jobs())
        if name == "municipal_qto_get_job":
            return _success(_get_job(args))
        if name == "municipal_qto_review_job":
            return _success(_review(args))
        return _failure(f"未知工具：{name}")
    except (OSError, PermissionError, QtoJobError, ReviewInputError, ValueError, json.JSONDecodeError) as exc:
        return _failure(str(exc))


def _error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    if isinstance(method, str) and method.startswith("notifications/"):
        return None
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": request_id, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": SERVER_INSTRUCTIONS,
        }}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = request.get("params") or {}
        name = str(params.get("name", ""))
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            return _error_response(request_id, -32602, "工具 arguments 必须是对象")
        return {"jsonrpc": "2.0", "id": request_id, "result": call_tool(name, args)}
    return _error_response(request_id, -32601, f"不支持的 MCP 方法：{method}")


def main() -> int:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("MCP 请求必须是 JSON 对象")
            response = handle_request(request)
        except (json.JSONDecodeError, ValueError) as exc:
            response = _error_response(None, -32700, str(exc))
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
