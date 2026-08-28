from __future__ import annotations

import json
import uuid
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from .canonical import canonicalize_dxf
from .dxf import parse_ascii_dxf
from .network import calculate_network_sections
from .recognition import recognize_candidates
from .road import calculate_road_sections
from .retaining import calculate_retaining_sections


class QtoJobError(ValueError):
    """Raised when a QTO job cannot be completed without unsafe assumptions."""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _rounded_total(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def _combined_calculation(calculations: list[dict[str, Any]]) -> dict[str, Any]:
    quantities: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    rule_pack_versions: list[str] = []
    totals: dict[str, dict[str, Any]] = {}
    for calculation in calculations:
        quantities.extend(calculation.get("quantities", []))
        warnings.extend(calculation.get("warnings", []))
        version = str(calculation.get("rule_pack_version", "")).strip()
        if version and version not in rule_pack_versions:
            rule_pack_versions.append(version)
        for item in calculation.get("totals", []):
            total = totals.setdefault(item["item_code"], {
                "item_code": item["item_code"],
                "item": item["item"],
                "unit": item["unit"],
                "quantity": 0.0,
            })
            total["quantity"] = _rounded_total(Decimal(str(total["quantity"])) + Decimal(str(item["quantity"])))
    discipline_labels = {"road": "道路", "network": "管网", "retaining": "挡护"}
    labels = [discipline_labels.get(calculation["discipline"], calculation["discipline"]) for calculation in calculations]
    return {
        "disciplines": [calculation["discipline"] for calculation in calculations],
        "rule_pack_version": "+".join(rule_pack_versions),
        "rule_pack_versions": rule_pack_versions,
        "status": "CALCULATED",
        "review_required": True,
        "review_status": "待人工审核",
        "review_reasons": [f"{'、'.join(labels)}工程量均为 Inference，须与原图、设计说明、断面和构筑物表复核"] + [warning["message"] for warning in warnings],
        "warnings": warnings,
        "quantities": quantities,
        "totals": sorted(totals.values(), key=lambda item: item["item_code"]),
    }


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
    retaining_sections = job_input.get("retaining_sections")
    if retaining_sections is None:
        retaining_sections = job_input.get("sections", [])
    calculations: list[dict[str, Any]] = []
    if job_input.get("road_sections"):
        calculations.append(calculate_road_sections(job_input["road_sections"], canonical, str(job_input.get("road_rule_pack_version", "cq-municipal-road-v0.1"))))
    if job_input.get("network_sections"):
        calculations.append(calculate_network_sections(job_input["network_sections"], canonical, str(job_input.get("network_rule_pack_version", "cq-municipal-network-v0.1"))))
    if retaining_sections:
        calculations.append(calculate_retaining_sections(retaining_sections, canonical, str(job_input.get("retaining_rule_pack_version", job_input.get("rule_pack_version", "cq-municipal-retaining-v0.1")))))
    if not calculations:
        raise QtoJobError("至少需要一类工程量输入：road_sections、network_sections 或 retaining_sections")
    combined = _combined_calculation(calculations)
    job_id = str(job_input.get("job_id", "")).strip() or f"CAD-{uuid.uuid4().hex[:10].upper()}"
    return {
        "job_id": job_id,
        "project_id": str(job_input.get("project_id", "")).strip(),
        "created_at": _now(),
        "status": "REVIEW_REQUIRED",
        "source": canonical,
        "recognition": recognition,
        "calculation": combined,
        "input_snapshot": {
            "road_sections": job_input.get("road_sections", []),
            "network_sections": job_input.get("network_sections", []),
            "retaining_sections": retaining_sections or [],
            "rule_pack_versions": combined["rule_pack_versions"],
        },
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
