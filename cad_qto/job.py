from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .canonical import canonicalize_dxf
from .dxf import parse_ascii_dxf
from .recognition import recognize_candidates
from .retaining import calculate_retaining_sections


class QtoJobError(ValueError):
    """Raised when a QTO job cannot be completed without unsafe assumptions."""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def run_job(job_input: dict[str, Any], *, canonical_path: str | Path | None = None) -> dict[str, Any]:
    if not isinstance(job_input, dict):
        raise QtoJobError("算量输入必须是 JSON 对象")
    source_value = str(job_input.get("source_file", "")).strip()
    if not source_value:
        raise QtoJobError("缺少 source_file；当前核心只接受项目私有路径下的 DXF")
    source = Path(source_value)
    if source.suffix.lower() != ".dxf":
        raise QtoJobError("当前 MVP 只接受 .dxf；DWG/PDF/IFC/LandXML 请走各自适配器，不强行转成 DXF")
    if not source.exists() or not source.is_file():
        raise QtoJobError(f"图纸文件不存在：{source}")
    if canonical_path is None:
        canonical_path = source.with_name(source.stem + ".canonical.dxf")
    canonical = canonicalize_dxf(source, canonical_path)
    document = parse_ascii_dxf(source)
    recognition = recognize_candidates(document, canonical)
    retaining = calculate_retaining_sections(job_input.get("sections", []), canonical, str(job_input.get("rule_pack_version", "cq-municipal-retaining-v0.1")))
    job_id = str(job_input.get("job_id", "")).strip() or f"CAD-{uuid.uuid4().hex[:10].upper()}"
    return {
        "job_id": job_id,
        "project_id": str(job_input.get("project_id", "")).strip(),
        "created_at": _now(),
        "status": "REVIEW_REQUIRED",
        "source": canonical,
        "recognition": recognition,
        "calculation": retaining,
        "input_snapshot": {"sections": job_input.get("sections", []), "rule_pack_version": retaining["rule_pack_version"]},
        "data_classification": "PRIVATE_PROJECT_DATA",
    }


def run_job_file(input_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    source = Path(input_path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    result = run_job(payload)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
