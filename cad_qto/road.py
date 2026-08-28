from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


class RoadInputError(ValueError):
    """Raised when a road section cannot be calculated without guessing."""


Q = Decimal("0.000001")


def _decimal(value: Any, field: str, *, required: bool = False, positive: bool = False) -> Decimal | None:
    if value is None or value == "":
        if required:
            raise RoadInputError(f"道路断面缺少必填参数：{field}")
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RoadInputError(f"道路参数不是有效数字：{field}") from exc
    if not result.is_finite() or result < 0 or (positive and result <= 0):
        raise RoadInputError(f"道路参数必须为{'大于 0' if positive else '非负'}：{field}")
    return result


def _rounded(value: Decimal) -> float:
    return float(value.quantize(Q, rounding=ROUND_HALF_UP))


def _ref(section: dict[str, Any], source_manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_type": "CAD_AND_INPUT_SNAPSHOT",
        "source_file": source_manifest.get("source_file", ""),
        "source_sha256": source_manifest.get("source_sha256", ""),
        "section_id": section.get("section_id", ""),
        "discipline": "road",
        "input_origin": "人工确认的道路断面参数；需在审核时与图纸和断面表核对",
    }


def _line(section: dict[str, Any], source_manifest: dict[str, Any], item_code: str, item: str, unit: str, quantity: Decimal, formula: str, inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "quantity_id": f"{section.get('section_id', 'SECTION')}-{item_code}",
        "discipline": "road",
        "section_id": section.get("section_id", ""),
        "station_start": section.get("station_start", ""),
        "station_end": section.get("station_end", ""),
        "road_type": section.get("road_type", "未指定"),
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


def calculate_road_sections(sections: list[dict[str, Any]], source_manifest: dict[str, Any], rule_pack_version: str = "cq-municipal-road-v0.1") -> dict[str, Any]:
    if not isinstance(sections, list) or not sections:
        raise RoadInputError("至少需要一个道路断面")
    quantities: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for index, raw_section in enumerate(sections, start=1):
        if not isinstance(raw_section, dict):
            raise RoadInputError(f"第 {index} 个道路断面不是对象")
        section_id = str(raw_section.get("section_id", f"ROAD-{index:03d}")).strip() or f"ROAD-{index:03d}"
        section = {**raw_section, "section_id": section_id}
        length = _decimal(section.get("length_m"), f"{section_id}.length_m", required=True, positive=True)
        width = _decimal(section.get("carriageway_width_m"), f"{section_id}.carriageway_width_m", required=True, positive=True)
        surface_thickness = _decimal(section.get("surface_thickness_m"), f"{section_id}.surface_thickness_m", required=True, positive=True)
        area = length * width
        quantities.append(_line(section, source_manifest, "CQ-ROAD-SURFACE-AREA", "车行道路面面积", "m²", area, f"{length} × {width}", {"length_m": _rounded(length), "width_m": _rounded(width)}))
        quantities.append(_line(section, source_manifest, "CQ-ROAD-SURFACE", "车行道路面结构层", "m³", area * surface_thickness, f"{length} × {width} × {surface_thickness}", {"length_m": _rounded(length), "width_m": _rounded(width), "thickness_m": _rounded(surface_thickness)}))

        for field, code, item in (("base_thickness_m", "CQ-ROAD-BASE", "道路基层"), ("subbase_thickness_m", "CQ-ROAD-SUBBASE", "道路底基层")):
            thickness = _decimal(section.get(field), f"{section_id}.{field}")
            if thickness is None:
                warnings.append({"section_id": section_id, "code": f"{code}-INPUT-MISSING", "message": f"缺少 {field}，未计算{item}"})
            elif thickness > 0:
                quantities.append(_line(section, source_manifest, code, item, "m³", area * thickness, f"{length} × {width} × {thickness}", {"length_m": _rounded(length), "width_m": _rounded(width), "thickness_m": _rounded(thickness)}))

        cut_depth = _decimal(section.get("cut_depth_m"), f"{section_id}.cut_depth_m")
        fill_depth = _decimal(section.get("fill_depth_m"), f"{section_id}.fill_depth_m")
        roadbed_width = _decimal(section.get("roadbed_width_m"), f"{section_id}.roadbed_width_m", positive=True)
        if cut_depth is not None and cut_depth > 0:
            if roadbed_width is None:
                warnings.append({"section_id": section_id, "code": "ROAD-CUT-INPUT-INCOMPLETE", "message": "路基挖方需要 roadbed_width_m 和 cut_depth_m，未计算挖方"})
            else:
                quantities.append(_line(section, source_manifest, "CQ-ROAD-CUT", "路基挖方", "m³", length * roadbed_width * cut_depth, f"{length} × {roadbed_width} × {cut_depth}", {"length_m": _rounded(length), "roadbed_width_m": _rounded(roadbed_width), "depth_m": _rounded(cut_depth)}))
        if fill_depth is not None and fill_depth > 0:
            if roadbed_width is None:
                warnings.append({"section_id": section_id, "code": "ROAD-FILL-INPUT-INCOMPLETE", "message": "路基填方需要 roadbed_width_m 和 fill_depth_m，未计算填方"})
            else:
                quantities.append(_line(section, source_manifest, "CQ-ROAD-FILL", "路基填方", "m³", length * roadbed_width * fill_depth, f"{length} × {roadbed_width} × {fill_depth}", {"length_m": _rounded(length), "roadbed_width_m": _rounded(roadbed_width), "depth_m": _rounded(fill_depth)}))

        curb_length = _decimal(section.get("curb_length_m"), f"{section_id}.curb_length_m")
        if curb_length is not None and curb_length > 0:
            quantities.append(_line(section, source_manifest, "CQ-ROAD-CURB", "路缘石", "m", curb_length, f"{curb_length}（人工确认长度）", {"length_m": _rounded(curb_length)}))
        sidewalk_area = _decimal(section.get("sidewalk_area_m2"), f"{section_id}.sidewalk_area_m2")
        if sidewalk_area is not None and sidewalk_area > 0:
            quantities.append(_line(section, source_manifest, "CQ-ROAD-SIDEWALK", "人行道铺装面积", "m²", sidewalk_area, f"{sidewalk_area}（人工确认面积）", {"area_m2": _rounded(sidewalk_area)}))

    return {
        "discipline": "road",
        "rule_pack_version": rule_pack_version,
        "status": "CALCULATED",
        "review_required": True,
        "review_status": "待人工审核",
        "review_reasons": ["道路工程量均为 Inference，须与原图、断面表和设计说明复核"] + [warning["message"] for warning in warnings],
        "warnings": warnings,
        "quantities": quantities,
        "totals": _totals(quantities),
    }
