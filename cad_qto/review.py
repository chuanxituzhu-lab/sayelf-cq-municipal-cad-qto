from __future__ import annotations

import copy
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


REVIEW_PROTOCOL_VERSION = "cq-municipal-review-v0.1"
REVIEWER_ID_RE = re.compile(r"^[^\\/\\\\]{2,80}$")
REVIEW_ROLES = {"production", "technical", "cost", "project_manager"}
DECISIONS = {"approve", "return", "reject"}
REQUIRED_CHECKS = (
    "source_drawing",
    "design_basis",
    "section_parameters",
    "units_and_rule",
    "location_scope",
)
CHECK_LABELS = {
    "source_drawing": "原始图纸与版本",
    "design_basis": "设计说明与依据",
    "section_parameters": "挡护断面参数",
    "units_and_rule": "单位与规则版本",
    "location_scope": "工程部位与范围",
}


class ReviewInputError(ValueError):
    """Raised when a human review cannot be recorded safely."""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _text(value: Any, field: str, *, required: bool = True, maximum: int = 2000) -> str:
    result = str(value or "").strip()
    if required and not result:
        raise ReviewInputError(f"缺少人工审核字段：{field}")
    if len(result) > maximum:
        raise ReviewInputError(f"人工审核字段过长：{field}")
    return result


def _checked_items(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ReviewInputError("checked_items 必须是数组")
    result: list[str] = []
    for item in value:
        code = _text(item, "checked_items", maximum=80)
        if code not in CHECK_LABELS:
            raise ReviewInputError(f"不支持的人工审核项：{code}")
        if code in result:
            raise ReviewInputError(f"人工审核项重复：{code}")
        result.append(code)
    return result


def _evidence_refs(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ReviewInputError("evidence_refs 必须是数组")
    result: list[str] = []
    for item in value:
        ref = _text(item, "evidence_refs", maximum=240)
        path = Path(ref)
        if path.is_absolute() or ".." in path.parts:
            raise ReviewInputError("evidence_refs 只能使用项目内相对引用")
        if ref not in result:
            result.append(ref)
    if len(result) > 50:
        raise ReviewInputError("evidence_refs 不能超过 50 条")
    return result


def record_job_review(
    job: dict[str, Any],
    review_input: dict[str, Any],
    *,
    verified_reviewer_id: str | None = None,
) -> dict[str, Any]:
    """Return a reviewed copy of a job and keep the original object unchanged."""
    if not isinstance(job, dict):
        raise ReviewInputError("算量作业必须是对象")
    if not isinstance(review_input, dict):
        raise ReviewInputError("人工审核输入必须是对象")
    if review_input.get("confirm") is not True:
        raise ReviewInputError("人工审核必须明确 confirm=true")
    requested_job_id = _text(review_input.get("job_id"), "job_id", maximum=80)
    if requested_job_id != str(job.get("job_id", "")):
        raise ReviewInputError("审核作业编号与作业内容不一致")

    reviewer_id = _text(review_input.get("reviewer_id"), "reviewer_id", maximum=80)
    if not REVIEWER_ID_RE.fullmatch(reviewer_id):
        raise ReviewInputError("reviewer_id 不能包含路径分隔符")
    reviewer_role = _text(review_input.get("reviewer_role"), "reviewer_role", maximum=40)
    if reviewer_role not in REVIEW_ROLES:
        raise ReviewInputError(f"不支持的审核岗位：{reviewer_role}")
    decision = _text(review_input.get("decision"), "decision", maximum=20)
    if decision not in DECISIONS:
        raise ReviewInputError(f"不支持的审核决定：{decision}")
    checked_items = _checked_items(review_input.get("checked_items"))
    missing = [code for code in REQUIRED_CHECKS if code not in checked_items]
    if decision == "approve" and missing:
        labels = "、".join(CHECK_LABELS[code] for code in missing)
        raise ReviewInputError(f"通过前必须完成全部审核项：{labels}")
    if verified_reviewer_id is not None:
        verified = _text(verified_reviewer_id, "verified_reviewer_id", maximum=80)
        if reviewer_id != verified:
            raise ReviewInputError("审核人标识与当前已认证身份不一致")
    else:
        verified = ""

    note = _text(review_input.get("note"), "note", required=False)
    evidence_refs = _evidence_refs(review_input.get("evidence_refs"))
    identity_status = "VERIFIED_LOCAL_IDENTITY" if verified else "UNVERIFIED_EXPLICIT_INPUT"
    if decision == "approve" and verified:
        status = "FACT_CONFIRMED"
        semantic_status = "Fact"
        fact_promotion_status = "PROMOTED"
        review_status = "已人工审核"
    elif decision == "approve":
        status = "REVIEWED_PENDING_AUTHORITY"
        semantic_status = "Inference"
        fact_promotion_status = "BLOCKED_UNVERIFIED_IDENTITY"
        review_status = "已审核待身份授权"
    elif decision == "return":
        status = "RETURNED"
        semantic_status = "Inference"
        fact_promotion_status = "NOT_APPLICABLE"
        review_status = "退回补充"
    else:
        status = "REJECTED"
        semantic_status = "Inference"
        fact_promotion_status = "NOT_APPLICABLE"
        review_status = "审核不通过"

    reviewed = copy.deepcopy(job)
    calculation = reviewed.get("calculation")
    if not isinstance(calculation, dict):
        raise ReviewInputError("算量作业缺少 calculation 结果，不能审核")
    review_id = f"REV-{uuid.uuid4().hex[:10].upper()}"
    created_at = _now()
    event = {
        "review_id": review_id,
        "protocol_version": REVIEW_PROTOCOL_VERSION,
        "reviewer_id": reviewer_id,
        "reviewer_role": reviewer_role,
        "decision": decision,
        "checked_items": checked_items,
        "missing_required_checks": missing,
        "note": note,
        "evidence_refs": evidence_refs,
        "identity_status": identity_status,
        "fact_promotion_status": fact_promotion_status,
        "created_at": created_at,
    }
    history = reviewed.get("review_history", [])
    if not isinstance(history, list):
        raise ReviewInputError("算量作业 review_history 格式损坏")
    history.append(event)
    reviewed["review_history"] = history
    reviewed["review"] = {
        "protocol_version": REVIEW_PROTOCOL_VERSION,
        "status": status,
        "semantic_status": semantic_status,
        "fact_promotion_status": fact_promotion_status,
        "last_review_id": review_id,
        "last_reviewer_id": reviewer_id,
        "last_reviewer_role": reviewer_role,
        "last_review_at": created_at,
        "missing_required_checks": missing,
    }
    reviewed["status"] = status
    calculation["review_status"] = review_status
    calculation["semantic_status"] = semantic_status
    calculation["fact_promotion_status"] = fact_promotion_status
    return reviewed


def write_job_atomic(path: str | Path, job: dict[str, Any]) -> None:
    """Persist a reviewed job without leaving a half-written JSON file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()
