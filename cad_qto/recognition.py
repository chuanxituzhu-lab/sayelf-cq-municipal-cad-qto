from __future__ import annotations

from typing import Any

from .dxf import DxfDocument, geometry_inventory


LAYER_RULES = (
    ("retaining", ("挡护", "挡墙", "挡土", "护坡", "护岸", "重力墙", "悬臂墙", "桩板墙", "抗滑桩", "锚杆", "锚索", "格构")),
    ("road", ("道路", "路面", "路基", "路床", "边坡")),
    ("drainage", ("雨水", "污水", "排水", "管沟", "边沟", "截水", "盲沟")),
    ("earthwork", ("土方", "挖方", "填方", "回填", "弃方")),
)


def classify_layer(layer: str) -> list[str]:
    normalized = layer.casefold()
    return [group for group, keywords in LAYER_RULES if any(keyword.casefold() in normalized for keyword in keywords)]


def recognize_candidates(document: DxfDocument, source_manifest: dict[str, Any]) -> dict[str, Any]:
    inventory = geometry_inventory(document)
    candidates: list[dict[str, Any]] = []
    for layer in inventory["layers"]:
        groups = classify_layer(layer["layer"])
        if not groups:
            continue
        candidates.append({
            "candidate_id": f"LAYER-{len(candidates) + 1:03d}",
            "layer": layer["layer"],
            "candidate_groups": groups,
            "status": "Hypothesis",
            "review_required": True,
            "reason": "根据图层名称匹配候选专业，必须由人员确认构件语义和断面参数",
            "geometry": layer,
            "evidence_refs": [{
                "evidence_type": "CAD_ENTITY_INVENTORY",
                "source_file": source_manifest.get("source_file", ""),
                "source_sha256": source_manifest.get("source_sha256", ""),
                "layer": layer["layer"],
                "source_lines": layer["source_lines"],
            }],
        })
    return {
        "recognizer_version": "layer-semantic-v0.1",
        "status": "Hypothesis",
        "review_required": True,
        "candidates": candidates,
        "unmatched_layers": [layer["layer"] for layer in inventory["layers"] if not classify_layer(layer["layer"])],
    }
