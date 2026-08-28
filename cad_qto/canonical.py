from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .dxf import DxfParseError, geometry_inventory, parse_ascii_dxf, write_canonical_dxf


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonicalize_dxf(source_path: str | Path, canonical_path: str | Path) -> dict[str, Any]:
    source = Path(source_path)
    target = Path(canonical_path)
    if source.resolve() == target.resolve():
        raise DxfParseError("标准化输出不能覆盖原始 DXF")
    document = parse_ascii_dxf(source)
    write_canonical_dxf(document, target)
    inventory = geometry_inventory(document)
    warnings = []
    if document.unsupported_entities:
        warnings.append("存在未支持的实体；这些实体已保留在告警中，没有参与工程量")
    if document.units_code not in {None, "6"}:
        warnings.append(f"图纸 $INSUNITS={document.units_code}，当前只记录单位代码，不自动换算模型单位")
    return {
        "source_file": str(source),
        "canonical_file": str(target),
        "source_sha256": sha256_file(source),
        "canonical_sha256": sha256_file(target),
        "source_encoding": document.source_encoding,
        "status": "NORMALIZED",
        "parser_version": "ascii-dxf-v0.1",
        "kept_entity_count": len(document.entities),
        "unsupported_entities": document.unsupported_entities,
        "warnings": warnings,
        "geometry_inventory": inventory,
    }
