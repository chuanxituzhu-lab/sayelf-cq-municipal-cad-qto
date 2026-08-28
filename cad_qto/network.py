from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


class NetworkInputError(ValueError):
    """Raised when a utility-network segment cannot be calculated safely."""


Q = Decimal("0.000001")
PI = Decimal("3.141592653589793")


def _decimal(value: Any, field: str, *, required: bool = False, positive: bool = False) -> Decimal | None:
    if value is None or value == "":
        if required:
            raise NetworkInputError(f"管网断面缺少必填参数：{field}")
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise NetworkInputError(f"管网参数不是有效数字：{field}") from exc
    if not result.is_finite() or result < 0 or (positive and result <= 0):
        raise NetworkInputError(f"管网参数必须为{'大于 0' if positive else '非负'}：{field}")
    return result


def _rounded(value: Decimal) -> float:
    return float(value.quantize(Q, rounding=ROUND_HALF_UP))


def _display(value: Decimal) -> str:
    text = format(value.quantize(Q, rounding=ROUND_HALF_UP), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _ref(segment: dict[str, Any], source_manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_type": "CAD_AND_INPUT_SNAPSHOT",
        "source_file": source_manifest.get("source_file", ""),
        "source_sha256": source_manifest.get("source_sha256", ""),
        "section_id": segment.get("segment_id", ""),
        "discipline": "network",
        "input_origin": "人工确认的管网断面和构筑物参数；需在审核时与图纸和纵断面核对",
    }


def _line(segment: dict[str, Any], source_manifest: dict[str, Any], item_code: str, item: str, unit: str, quantity: Decimal, formula: str, inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "quantity_id": f"{segment.get('segment_id', 'SEGMENT')}-{item_code}",
        "discipline": "network",
        "section_id": segment.get("segment_id", ""),
        "station_start": segment.get("station_start", ""),
        "station_end": segment.get("station_end", ""),
        "network_type": segment.get("network_type", "未指定"),
        "item_code": item_code,
        "item": item,
        "unit": unit,
        "quantity": _rounded(quantity),
        "formula": formula,
        "inputs": inputs,
        "status": "Inference",
        "review_status": "待人工审核",
        "evidence_refs": [_ref(segment, source_manifest)],
    }


def _totals(quantities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    for quantity in quantities:
        total = totals.setdefault(quantity["item_code"], {
            "item_code": quantity["item_code"],
            "item": quantity["item"],
            "unit": quantity["unit"],
            "quantity": 0.0,
        })
        total["quantity"] = _rounded(Decimal(str(total["quantity"])) + Decimal(str(quantity["quantity"])))
    return sorted(totals.values(), key=lambda item: item["item_code"])


def calculate_network_sections(segments: list[dict[str, Any]], source_manifest: dict[str, Any], rule_pack_version: str = "cq-municipal-network-v0.1") -> dict[str, Any]:
    if not isinstance(segments, list) or not segments:
        raise NetworkInputError("至少需要一个管网分段")
    quantities: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for index, raw_segment in enumerate(segments, start=1):
        if not isinstance(raw_segment, dict):
            raise NetworkInputError(f"第 {index} 个管网分段不是对象")
        segment_id = str(raw_segment.get("segment_id", f"NET-{index:03d}")).strip() or f"NET-{index:03d}"
        segment = {**raw_segment, "segment_id": segment_id}
        length = _decimal(segment.get("length_m"), f"{segment_id}.length_m", required=True, positive=True)
        trench_width = _decimal(segment.get("trench_width_m"), f"{segment_id}.trench_width_m", required=True, positive=True)
        trench_depth = _decimal(segment.get("trench_depth_m"), f"{segment_id}.trench_depth_m", required=True, positive=True)
        diameter = _decimal(segment.get("pipe_outer_diameter_m"), f"{segment_id}.pipe_outer_diameter_m", positive=True)
        if diameter is None:
            diameter_mm = _decimal(segment.get("pipe_outer_diameter_mm"), f"{segment_id}.pipe_outer_diameter_mm", positive=True)
            if diameter_mm is not None:
                diameter = diameter_mm / Decimal("1000")
        if diameter is None or diameter <= 0:
            raise NetworkInputError(f"管网分段缺少必填参数：{segment_id}.pipe_outer_diameter_m 或 pipe_outer_diameter_mm")

        excavation = trench_width * trench_depth * length
        pipe_volume = PI * diameter * diameter / Decimal("4") * length
        quantities.append(_line(segment, source_manifest, "CQ-NET-PIPE", "管道敷设长度", "m", length, f"{_display(length)}（人工确认长度）", {"length_m": _rounded(length), "diameter_m": _rounded(diameter)}))
        quantities.append(_line(segment, source_manifest, "CQ-NET-EXC", "管沟土方开挖", "m³", excavation, f"{_display(trench_width)} × {_display(trench_depth)} × {_display(length)}", {"trench_width_m": _rounded(trench_width), "trench_depth_m": _rounded(trench_depth), "length_m": _rounded(length)}))
        quantities.append(_line(segment, source_manifest, "CQ-NET-PIPE-VOLUME", "管道外径占用体积", "m³", pipe_volume, f"π × {_display(diameter)}² / 4 × {_display(length)}", {"diameter_m": _rounded(diameter), "length_m": _rounded(length)}))

        bedding_thickness = _decimal(segment.get("bedding_thickness_m"), f"{segment_id}.bedding_thickness_m")
        bedding_volume = Decimal("0")
        if bedding_thickness is None:
            warnings.append({"segment_id": segment_id, "code": "NETWORK-BEDDING-MISSING", "message": "未提供垫层厚度，未计算垫层，回填暂未扣除垫层"})
        elif bedding_thickness > 0:
            bedding_volume = trench_width * bedding_thickness * length
            quantities.append(_line(segment, source_manifest, "CQ-NET-BEDDING", "管道基础垫层", "m³", bedding_volume, f"{_display(trench_width)} × {_display(bedding_thickness)} × {_display(length)}", {"width_m": _rounded(trench_width), "thickness_m": _rounded(bedding_thickness), "length_m": _rounded(length)}))

        backfill = excavation - pipe_volume - bedding_volume
        if backfill < 0:
            warnings.append({"segment_id": segment_id, "code": "NETWORK-BACKFILL-NEGATIVE", "message": "管沟开挖体积小于管道和垫层占用体积，未生成回填量"})
        else:
            quantities.append(_line(segment, source_manifest, "CQ-NET-BACKFILL", "管沟回填", "m³", backfill, f"{_display(excavation)} - {_display(pipe_volume)} - {_display(bedding_volume)}", {"excavation_m3": _rounded(excavation), "pipe_volume_m3": _rounded(pipe_volume), "bedding_m3": _rounded(bedding_volume)}))

        for field, code, item in (("manhole_count", "CQ-NET-MANHOLE", "检查井"), ("inlet_count", "CQ-NET-INLET", "雨水口")):
            count = _decimal(segment.get(field), f"{segment_id}.{field}")
            if count is not None and count > 0:
                if count != count.to_integral_value():
                    warnings.append({"segment_id": segment_id, "code": f"{code}-NOT-INTEGER", "message": f"{item}数量不是整数，未生成数量明细"})
                else:
                    quantities.append(_line(segment, source_manifest, code, item, "座", count, f"{_display(count)}（图纸明确数量）", {"count": int(count)}))

        restoration_area = _decimal(segment.get("road_restoration_area_m2"), f"{segment_id}.road_restoration_area_m2")
        if restoration_area is not None and restoration_area > 0:
            quantities.append(_line(segment, source_manifest, "CQ-NET-ROAD-RESTORE", "路面恢复面积", "m²", restoration_area, f"{restoration_area}（人工确认面积）", {"area_m2": _rounded(restoration_area)}))

    return {
        "discipline": "network",
        "rule_pack_version": rule_pack_version,
        "status": "CALCULATED",
        "review_required": True,
        "review_status": "待人工审核",
        "review_reasons": ["管网工程量均为 Inference，须与原图、纵断面和构筑物表复核"] + [warning["message"] for warning in warnings],
        "warnings": warnings,
        "quantities": quantities,
        "totals": _totals(quantities),
    }
