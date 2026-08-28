from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any


class RetainingInputError(ValueError):
    """Raised when a retaining section is too ambiguous to calculate safely."""


Q = Decimal("0.000001")


def _decimal(value: Any, field: str, *, required: bool = False, positive: bool = False) -> Decimal | None:
    if value is None or value == "":
        if required:
            raise RetainingInputError(f"挡护结构断面缺少必填尺寸：{field}")
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RetainingInputError(f"挡护结构尺寸不是有效数字：{field}") from exc
    if not result.is_finite() or result < 0 or (positive and result <= 0):
        raise RetainingInputError(f"挡护结构尺寸必须为{'大于 0' if positive else '非负'}：{field}")
    return result


def _rounded(value: Decimal) -> float:
    return float(value.quantize(Q, rounding=ROUND_HALF_UP))


def _ceil(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def _floor(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def _ref(section: dict[str, Any], source_manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_type": "CAD_AND_INPUT_SNAPSHOT",
        "source_file": source_manifest.get("source_file", ""),
        "source_sha256": source_manifest.get("source_sha256", ""),
        "section_id": section.get("section_id", ""),
        "input_origin": "人工确认的断面参数；需在审核时与图纸断面核对",
    }


def _line(section: dict[str, Any], source_manifest: dict[str, Any], item_code: str, item: str, unit: str, quantity: Decimal, formula: str, inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "quantity_id": f"{section.get('section_id', 'SECTION')}-{item_code}",
        "section_id": section.get("section_id", ""),
        "station_start": section.get("station_start", ""),
        "station_end": section.get("station_end", ""),
        "wall_type": section.get("wall_type", "未指定"),
        "item_code": item_code,
        "item": item,
        "unit": unit,
        "quantity": _rounded(quantity),
        "formula": formula,
        "inputs": inputs,
        "status": "Inference",
        "review_status": "待人工审核",
        "evidence_refs": [_ref(section, source_manifest)],
    }


def calculate_retaining_sections(sections: list[dict[str, Any]], source_manifest: dict[str, Any], rule_pack_version: str = "cq-municipal-retaining-v0.1") -> dict[str, Any]:
    if not isinstance(sections, list) or not sections:
        raise RetainingInputError("至少需要一个挡护结构断面")
    quantities: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            raise RetainingInputError(f"第 {index} 个挡护断面不是对象")
        section_id = str(section.get("section_id", f"SECTION-{index:03d}")).strip() or f"SECTION-{index:03d}"
        section = {**section, "section_id": section_id}
        if not str(section.get("wall_type", "")).strip():
            warnings.append({"section_id": section_id, "code": "WALL_TYPE_UNCONFIRMED", "message": "未填写挡护结构类型，数量只能作为待核对草稿"})
        length = _decimal(section.get("length_m"), f"{section_id}.length_m", required=True, positive=True)
        base = _decimal(section.get("wall_base_width_m"), f"{section_id}.wall_base_width_m", required=True, positive=True)
        top = _decimal(section.get("wall_top_width_m"), f"{section_id}.wall_top_width_m", required=True, positive=True)
        height = _decimal(section.get("wall_height_m"), f"{section_id}.wall_height_m", required=True, positive=True)
        if top > base:
            warnings.append({"section_id": section_id, "code": "WALL_TOP_WIDER_THAN_BASE", "message": "墙顶宽度大于墙底宽度，仍按输入梯形断面计算，请人工核对"})
        wall_area = (base + top) * height / Decimal("2")
        wall_material = str(section.get("wall_material", "未指定")).strip() or "未指定"
        quantities.append(_line(section, source_manifest, "CQ-RET-WALL", f"挡墙墙身（{wall_material}，梯形断面）", "m³", wall_area * length, f"({base} + {top}) / 2 × {height} × {length}", {"base_width_m": _rounded(base), "top_width_m": _rounded(top), "height_m": _rounded(height), "length_m": _rounded(length)}))

        foundation_values = [_decimal(section.get(key), f"{section_id}.{key}") for key in ("foundation_width_m", "foundation_thickness_m")]
        if any(value is not None for value in foundation_values):
            if any(value is None or value <= 0 for value in foundation_values):
                warnings.append({"section_id": section_id, "code": "FOUNDATION_INPUT_INCOMPLETE", "message": "基础参数不完整，未计算基础体积"})
            else:
                foundation_width, foundation_thickness = foundation_values
                quantities.append(_line(section, source_manifest, "CQ-RET-FOUND", "挡墙基础", "m³", foundation_width * foundation_thickness * length, f"{foundation_width} × {foundation_thickness} × {length}", {"width_m": _rounded(foundation_width), "thickness_m": _rounded(foundation_thickness), "length_m": _rounded(length)}))

        for field, code, item, unit in (("excavation_area_m2_per_m", "CQ-RET-EXC", "挡护结构基坑开挖", "m³"), ("backfill_area_m2_per_m", "CQ-RET-BACKFILL", "挡护结构墙背回填", "m³")):
            area = _decimal(section.get(field), f"{section_id}.{field}")
            if area is not None and area > 0:
                quantities.append(_line(section, source_manifest, code, item, unit, area * length, f"{area} × {length}", {"section_area_m2_per_m": _rounded(area), "length_m": _rounded(length)}))

        hole_count = _decimal(section.get("drainage_hole_count"), f"{section_id}.drainage_hole_count")
        hole_spacing = _decimal(section.get("drainage_hole_spacing_m"), f"{section_id}.drainage_hole_spacing_m", positive=True)
        if hole_count is None and hole_spacing is not None:
            hole_count = Decimal(_floor(length / hole_spacing) + 1)
        if hole_count is not None and hole_count > 0:
            if hole_count != hole_count.to_integral_value():
                warnings.append({"section_id": section_id, "code": "DRAINAGE_HOLE_COUNT_NOT_INTEGER", "message": "泄水孔数量不是整数，未生成数量明细"})
            else:
                formula = f"{hole_count}（图纸明确数量）" if section.get("drainage_hole_count") not in {None, ""} else f"floor({length} / {hole_spacing}) + 1"
                quantities.append(_line(section, source_manifest, "CQ-RET-DRAIN-HOLE", "泄水孔", "个", hole_count, formula, {"count": int(hole_count), "spacing_m": _rounded(hole_spacing) if hole_spacing else None, "length_m": _rounded(length)}))

        filter_area = _decimal(section.get("filter_area_m2_per_m"), f"{section_id}.filter_area_m2_per_m")
        if filter_area is not None and filter_area > 0:
            quantities.append(_line(section, source_manifest, "CQ-RET-FILTER", "墙背反滤层", "m²", filter_area * length, f"{filter_area} × {length}", {"area_m2_per_m": _rounded(filter_area), "length_m": _rounded(length)}))

        anchor_count = _decimal(section.get("anchor_count"), f"{section_id}.anchor_count")
        anchor_spacing = _decimal(section.get("anchor_spacing_m"), f"{section_id}.anchor_spacing_m", positive=True)
        anchor_rows = _decimal(section.get("anchor_rows"), f"{section_id}.anchor_rows")
        if anchor_count is None and anchor_spacing is not None and anchor_rows is not None and anchor_rows > 0:
            anchor_count = Decimal(_ceil(length / anchor_spacing)) * anchor_rows
        if anchor_count is not None and anchor_count > 0:
            if anchor_count != anchor_count.to_integral_value():
                warnings.append({"section_id": section_id, "code": "ANCHOR_COUNT_NOT_INTEGER", "message": "锚杆数量不是整数，未生成锚杆数量明细"})
            else:
                formula = f"{anchor_count}（图纸明确数量）" if section.get("anchor_count") not in {None, ""} else f"ceil({length} / {anchor_spacing}) × {anchor_rows}"
                quantities.append(_line(section, source_manifest, "CQ-RET-ANCHOR", "锚杆/锚索", "根", anchor_count, formula, {"count": int(anchor_count), "spacing_m": _rounded(anchor_spacing) if anchor_spacing else None, "rows": int(anchor_rows) if anchor_rows else None}))
                anchor_length = _decimal(section.get("anchor_length_m"), f"{section_id}.anchor_length_m")
                if anchor_length is None or anchor_length <= 0:
                    warnings.append({"section_id": section_id, "code": "ANCHOR_LENGTH_MISSING", "message": "已计算锚杆根数，但缺少锚杆长度，未计算钻孔/注浆长度"})
                else:
                    drilling = anchor_count * anchor_length
                    quantities.append(_line(section, source_manifest, "CQ-RET-ANCHOR-DRILL", "锚杆钻孔", "m", drilling, f"{anchor_count} × {anchor_length}", {"count": int(anchor_count), "length_m": _rounded(anchor_length)}))
                    quantities.append(_line(section, source_manifest, "CQ-RET-GROUT", "锚杆注浆长度（按孔深）", "m", drilling, f"{anchor_count} × {anchor_length}", {"count": int(anchor_count), "length_m": _rounded(anchor_length)}))

        pile_count = _decimal(section.get("pile_count"), f"{section_id}.pile_count")
        if pile_count is not None and pile_count > 0:
            pile_length = _decimal(section.get("pile_length_m"), f"{section_id}.pile_length_m")
            pile_width = _decimal(section.get("pile_width_m"), f"{section_id}.pile_width_m")
            pile_depth = _decimal(section.get("pile_depth_m"), f"{section_id}.pile_depth_m")
            if pile_count != pile_count.to_integral_value():
                warnings.append({"section_id": section_id, "code": "PILE_COUNT_NOT_INTEGER", "message": "抗滑桩数量不是整数，未生成桩数量明细"})
            else:
                quantities.append(_line(section, source_manifest, "CQ-RET-PILE-COUNT", "抗滑桩", "根", pile_count, f"{pile_count}（图纸明确数量）", {"count": int(pile_count)}))
                if all(value is not None and value > 0 for value in (pile_length, pile_width, pile_depth)):
                    quantities.append(_line(section, source_manifest, "CQ-RET-PILE", "抗滑桩混凝土", "m³", pile_count * pile_length * pile_width * pile_depth, f"{pile_count} × {pile_length} × {pile_width} × {pile_depth}", {"count": int(pile_count), "length_m": _rounded(pile_length), "width_m": _rounded(pile_width), "depth_m": _rounded(pile_depth)}))
                else:
                    warnings.append({"section_id": section_id, "code": "PILE_SECTION_INCOMPLETE", "message": "已计算抗滑桩根数，但桩长/桩截面不完整，未计算混凝土体积"})

        shotcrete_area = _decimal(section.get("shotcrete_area_m2_per_m"), f"{section_id}.shotcrete_area_m2_per_m")
        shotcrete_thickness = _decimal(section.get("shotcrete_thickness_m"), f"{section_id}.shotcrete_thickness_m")
        if shotcrete_area is not None and shotcrete_area > 0:
            area_total = shotcrete_area * length
            quantities.append(_line(section, source_manifest, "CQ-RET-MESH", "钢筋网/挂网面积", "m²", area_total, f"{shotcrete_area} × {length}", {"area_m2_per_m": _rounded(shotcrete_area), "length_m": _rounded(length)}))
            if shotcrete_thickness is not None and shotcrete_thickness > 0:
                quantities.append(_line(section, source_manifest, "CQ-RET-SHOTCRETE", "喷射混凝土", "m³", area_total * shotcrete_thickness, f"{shotcrete_area} × {length} × {shotcrete_thickness}", {"area_m2_per_m": _rounded(shotcrete_area), "length_m": _rounded(length), "thickness_m": _rounded(shotcrete_thickness)}))
            else:
                warnings.append({"section_id": section_id, "code": "SHOTCRETE_THICKNESS_MISSING", "message": "已计算挂网面积，但缺少喷射混凝土厚度，未计算体积"})

    totals: dict[str, dict[str, Any]] = {}
    for quantity in quantities:
        total = totals.setdefault(quantity["item_code"], {"item_code": quantity["item_code"], "item": quantity["item"], "unit": quantity["unit"], "quantity": 0.0})
        total["quantity"] = _rounded(Decimal(str(total["quantity"])) + Decimal(str(quantity["quantity"])))
    return {
        "discipline": "retaining",
        "rule_pack_version": rule_pack_version,
        "status": "CALCULATED",
        "review_required": True,
        "review_status": "待人工审核",
        "review_reasons": ["所有机器计算量均为 Inference，须与原图、设计说明和断面表复核"] + [warning["message"] for warning in warnings],
        "warnings": warnings,
        "quantities": quantities,
        "totals": sorted(totals.values(), key=lambda item: item["item_code"]),
    }
