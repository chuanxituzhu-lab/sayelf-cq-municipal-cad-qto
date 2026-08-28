from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot
from pathlib import Path
from typing import Any


class DxfParseError(ValueError):
    """Raised when the conservative ASCII DXF parser cannot safely continue."""


@dataclass
class Entity:
    kind: str
    layer: str = "0"
    values: dict[str, Any] = field(default_factory=dict)
    source_line: int = 0


@dataclass
class DxfDocument:
    entities: list[Entity]
    unsupported_entities: list[dict[str, Any]]
    source_encoding: str
    units_code: str | None = None


SUPPORTED_ENTITY_TYPES = {"LINE", "LWPOLYLINE", "TEXT", "MTEXT"}


def _decode_ascii_dxf(raw: bytes) -> tuple[str, str]:
    if raw.startswith(b"AutoCAD Binary DXF") or b"\x00" in raw[:512]:
        raise DxfParseError("当前最小核心只接受 ASCII DXF；二进制 DXF 请先在本地转换后再导入")
    for encoding in ("utf-8-sig", "gb18030", "cp1252"):
        try:
            text = raw.decode(encoding)
            if "SECTION" in text and "ENTITIES" in text:
                return text, encoding
        except UnicodeDecodeError:
            continue
    raise DxfParseError("DXF 文本编码无法安全识别，未生成任何工程量")


def _pairs(text: str) -> list[tuple[int, str]]:
    lines = text.splitlines()
    if len(lines) % 2:
        raise DxfParseError("DXF 代码和值未成对出现，文件可能损坏")
    result: list[tuple[int, str]] = []
    for index in range(0, len(lines), 2):
        try:
            code = int(lines[index].strip())
        except ValueError as exc:
            raise DxfParseError(f"DXF 第 {index + 1} 行组码无效") from exc
        result.append((code, lines[index + 1].rstrip("\r")))
    return result


def _float(value: str, label: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise DxfParseError(f"DXF {label} 数值无效：{value!r}") from exc


def _entity_from_pairs(kind: str, pairs: list[tuple[int, str]], source_line: int) -> Entity | None:
    layer = next((value for code, value in pairs if code == 8), "0") or "0"
    if kind == "LINE":
        values = {"x1": None, "y1": None, "x2": None, "y2": None}
        for code, value in pairs:
            if code == 10:
                values["x1"] = _float(value, "LINE.x1")
            elif code == 20:
                values["y1"] = _float(value, "LINE.y1")
            elif code == 11:
                values["x2"] = _float(value, "LINE.x2")
            elif code == 21:
                values["y2"] = _float(value, "LINE.y2")
        if any(values[key] is None for key in values):
            raise DxfParseError("LINE 缺少二维端点，已停止该作业")
        return Entity(kind, layer, values, source_line)
    if kind == "LWPOLYLINE":
        points: list[list[float | None]] = []
        for code, value in pairs:
            if code == 10:
                points.append([_float(value, "LWPOLYLINE.x"), None])
            elif code == 20 and points:
                points[-1][1] = _float(value, "LWPOLYLINE.y")
        if not points or any(point[1] is None for point in points):
            raise DxfParseError("LWPOLYLINE 缺少完整顶点，已停止该作业")
        flags = int(next((value for code, value in pairs if code == 70), "0"))
        return Entity(kind, layer, {"points": [(float(x), float(y)) for x, y in points], "closed": bool(flags & 1)}, source_line)
    if kind == "TEXT":
        return Entity(kind, layer, {
            "x": _float(next((value for code, value in pairs if code == 10), "0"), "TEXT.x"),
            "y": _float(next((value for code, value in pairs if code == 20), "0"), "TEXT.y"),
            "height": _float(next((value for code, value in pairs if code == 40), "1"), "TEXT.height"),
            "text": next((value for code, value in pairs if code == 1), ""),
            "rotation": _float(next((value for code, value in pairs if code == 50), "0"), "TEXT.rotation"),
        }, source_line)
    if kind == "MTEXT":
        chunks = [value for code, value in pairs if code in {1, 3}]
        return Entity(kind, layer, {
            "x": _float(next((value for code, value in pairs if code == 10), "0"), "MTEXT.x"),
            "y": _float(next((value for code, value in pairs if code == 20), "0"), "MTEXT.y"),
            "height": _float(next((value for code, value in pairs if code == 40), "1"), "MTEXT.height"),
            "text": "".join(chunks),
            "rotation": _float(next((value for code, value in pairs if code == 50), "0"), "MTEXT.rotation"),
        }, source_line)
    return None


def parse_ascii_dxf(path: str | Path) -> DxfDocument:
    source = Path(path)
    raw = source.read_bytes()
    text, encoding = _decode_ascii_dxf(raw)
    pairs = _pairs(text)
    entities: list[Entity] = []
    unsupported: list[dict[str, Any]] = []
    units_code: str | None = None
    in_entities = False
    index = 0
    while index < len(pairs):
        code, value = pairs[index]
        if code == 0 and value == "SECTION":
            section_name = pairs[index + 1][1] if index + 1 < len(pairs) and pairs[index + 1][0] == 2 else ""
            in_entities = section_name == "ENTITIES"
            index += 2
            continue
        if code == 0 and value == "ENDSEC":
            in_entities = False
            index += 1
            continue
        if code == 9 and value == "$INSUNITS" and index + 1 < len(pairs) and pairs[index + 1][0] == 70:
            units_code = pairs[index + 1][1]
        if in_entities and code == 0:
            kind = value.upper().strip()
            end = index + 1
            while end < len(pairs) and pairs[end][0] != 0:
                end += 1
            entity_pairs = pairs[index + 1:end]
            if kind == "SEQEND":
                index = end
                continue
            if kind in SUPPORTED_ENTITY_TYPES:
                entity = _entity_from_pairs(kind, entity_pairs, index * 2 + 1)
                if entity:
                    entities.append(entity)
            else:
                unsupported.append({
                    "entity_type": kind,
                    "layer": next((v for c, v in entity_pairs if c == 8), "0"),
                    "source_line": index * 2 + 1,
                    "reason": "当前核心未实现该实体的几何提取",
                })
            index = end
            continue
        index += 1
    if not entities and not unsupported:
        raise DxfParseError("DXF 未检测到 ENTITIES，未生成任何工程量")
    return DxfDocument(entities, unsupported, encoding, units_code)


def polyline_length(points: list[tuple[float, float]], closed: bool = False) -> float:
    if len(points) < 2:
        return 0.0
    length = sum(hypot(points[index][0] - points[index - 1][0], points[index][1] - points[index - 1][1]) for index in range(1, len(points)))
    if closed:
        length += hypot(points[0][0] - points[-1][0], points[0][1] - points[-1][1])
    return length


def geometry_inventory(document: DxfDocument) -> dict[str, Any]:
    layers: dict[str, dict[str, Any]] = {}
    for entity in document.entities:
        layer = layers.setdefault(layer_name := entity.layer, {
            "layer": layer_name,
            "entity_count": 0,
            "entity_types": {},
            "linear_length": 0.0,
            "closed_polyline_count": 0,
            "texts": [],
            "source_lines": [],
        })
        layer["entity_count"] += 1
        layer["entity_types"][entity.kind] = layer["entity_types"].get(entity.kind, 0) + 1
        layer["source_lines"].append(entity.source_line)
        if entity.kind == "LINE":
            layer["linear_length"] += hypot(entity.values["x2"] - entity.values["x1"], entity.values["y2"] - entity.values["y1"])
        elif entity.kind == "LWPOLYLINE":
            layer["linear_length"] += polyline_length(entity.values["points"], entity.values["closed"])
            if entity.values["closed"]:
                layer["closed_polyline_count"] += 1
        elif entity.kind in {"TEXT", "MTEXT"}:
            layer["texts"].append(entity.values["text"])
    for layer in layers.values():
        layer["linear_length"] = round(layer["linear_length"], 6)
        layer["source_lines"].sort()
    return {
        "units_code": document.units_code,
        "entity_count": len(document.entities),
        "unsupported_entity_count": len(document.unsupported_entities),
        "layers": sorted(layers.values(), key=lambda item: item["layer"]),
        "unsupported_entities": document.unsupported_entities,
    }


def _number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def _layer_table(layers: list[str]) -> list[str]:
    lines = ["0", "TABLE", "2", "LAYER", "70", str(len(layers))]
    for layer in layers:
        lines.extend(["0", "LAYER", "2", layer[:255], "70", "0", "62", "7", "6", "CONTINUOUS"])
    lines.extend(["0", "ENDTAB"])
    return lines


def write_canonical_dxf(document: DxfDocument, destination: str | Path) -> None:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    layers = sorted({entity.layer or "0" for entity in document.entities}) or ["0"]
    lines = [
        "0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1009",
        "9", "$INSUNITS", "70", document.units_code or "6", "0", "ENDSEC",
        "0", "SECTION", "2", "TABLES",
        *_layer_table(layers),
        "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES",
    ]
    for entity in document.entities:
        values = entity.values
        lines.extend(["0", entity.kind, "8", entity.layer or "0"])
        if entity.kind == "LINE":
            lines.extend(["10", _number(values["x1"]), "20", _number(values["y1"]), "11", _number(values["x2"]), "21", _number(values["y2"])])
        elif entity.kind == "LWPOLYLINE":
            points = values["points"]
            lines.extend(["90", str(len(points)), "70", "1" if values["closed"] else "0"])
            for x, y in points:
                lines.extend(["10", _number(x), "20", _number(y)])
        elif entity.kind in {"TEXT", "MTEXT"}:
            lines.extend(["10", _number(values["x"]), "20", _number(values["y"]), "40", _number(values["height"])])
            if entity.kind == "MTEXT":
                lines.extend(["1", values["text"]])
            else:
                lines.extend(["1", values["text"]])
            if values.get("rotation", 0):
                lines.extend(["50", _number(values["rotation"])])
    lines.extend(["0", "ENDSEC", "0", "EOF", ""])
    target.write_text("\n".join(lines), encoding="utf-8", newline="\n")
