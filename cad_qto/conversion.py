from __future__ import annotations

import os
from math import ceil
from pathlib import Path
from typing import Any

from .canonical import sha256_file
from .dxf import DxfDocument, Entity, parse_ascii_dxf, write_canonical_dxf


SUPPORTED_INPUT_EXTENSIONS = {".dxf", ".pdf", ".dwg"}


class ConversionError(ValueError):
    """Raised when a local input cannot be converted without guessing."""


def _number(value: float) -> float:
    return round(float(value), 6)


def _point(value: Any) -> tuple[float, float]:
    if hasattr(value, "x") and hasattr(value, "y"):
        return _number(value.x), _number(value.y)
    return _number(value[0]), _number(value[1])


def _safe_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", "").splitlines()).strip()


def _pdf_dxf(source: Path, destination: Path) -> dict[str, Any]:
    try:
        import fitz  # type: ignore
    except ImportError as exc:
        raise ConversionError("本机未安装 PyMuPDF，无法进行 PDF 矢量转 DXF；未上传 PDF") from exc

    entities: list[Entity] = []
    warnings: list[str] = []
    page_summaries: list[dict[str, Any]] = []
    vector_path_count = 0
    text_count = 0
    try:
        document = fitz.open(source)
    except Exception as exc:
        raise ConversionError(f"PDF 无法在本机打开：{exc}") from exc
    try:
        page_count = len(document)
        if page_count == 0:
            raise ConversionError("PDF 没有页面，未生成 DXF")
        page_gap = 100.0
        x_offset = 0.0
        for page_index, page in enumerate(document, start=1):
            page_width = float(page.rect.width)
            page_height = float(page.rect.height)
            layer = f"PDF_PAGE_{page_index:03d}"
            page_paths = 0
            page_texts = 0
            try:
                drawings = page.get_drawings()
            except Exception as exc:
                drawings = []
                warnings.append(f"第 {page_index} 页矢量图元读取失败：{exc}")
            for drawing in drawings:
                for item in drawing.get("items", []):
                    kind = item[0] if item else ""
                    if kind == "l" and len(item) >= 3:
                        start = _point(item[1])
                        end = _point(item[2])
                        entities.append(Entity("LINE", layer, {
                            "x1": start[0] + x_offset,
                            "y1": page_height - start[1],
                            "x2": end[0] + x_offset,
                            "y2": page_height - end[1],
                        }))
                        page_paths += 1
                    elif kind == "re" and len(item) >= 2:
                        rect = item[1]
                        left, top = _point((rect.x0, rect.y0))
                        right, bottom = _point((rect.x1, rect.y1))
                        entities.append(Entity("LWPOLYLINE", layer, {
                            "points": [
                                (left + x_offset, page_height - top),
                                (right + x_offset, page_height - top),
                                (right + x_offset, page_height - bottom),
                                (left + x_offset, page_height - bottom),
                            ],
                            "closed": True,
                        }))
                        page_paths += 1
                    elif kind == "c" and len(item) >= 5:
                        # Cubic curves are approximated into short line segments so the
                        # existing conservative DXF parser can inspect them.
                        p0, p1, p2, p3 = (_point(item[index]) for index in range(1, 5))
                        segments = max(4, min(24, ceil(max(
                            abs(p3[0] - p0[0]), abs(p3[1] - p0[1]),
                            abs(p1[0] - p0[0]), abs(p2[1] - p0[1]),
                        ) / 12)))
                        previous = p0
                        for step in range(1, segments + 1):
                            t = step / segments
                            u = 1 - t
                            current = (
                                u ** 3 * p0[0] + 3 * u ** 2 * t * p1[0] + 3 * u * t ** 2 * p2[0] + t ** 3 * p3[0],
                                u ** 3 * p0[1] + 3 * u ** 2 * t * p1[1] + 3 * u * t ** 2 * p2[1] + t ** 3 * p3[1],
                            )
                            entities.append(Entity("LINE", layer, {
                                "x1": previous[0] + x_offset,
                                "y1": page_height - previous[1],
                                "x2": current[0] + x_offset,
                                "y2": page_height - current[1],
                            }))
                            previous = current
                        page_paths += 1
                    elif kind:
                        warnings.append(f"第 {page_index} 页存在未映射的 PDF 图元：{kind}")
            try:
                words = page.get_text("words")
            except Exception as exc:
                words = []
                warnings.append(f"第 {page_index} 页文字读取失败：{exc}")
            for word in words:
                if len(word) < 5:
                    continue
                text = _safe_text(word[4])
                if not text:
                    continue
                x0, y0, x1, y1 = map(float, word[:4])
                entities.append(Entity("TEXT", layer, {
                    "x": x0 + x_offset,
                    "y": page_height - y1,
                    "height": max(1.0, min(72.0, y1 - y0)),
                    "text": text,
                    "rotation": 0.0,
                }))
                page_texts += 1
            vector_path_count += page_paths
            text_count += page_texts
            page_summaries.append({"page": page_index, "width_pt": page_width, "height_pt": page_height, "vector_path_count": page_paths, "text_count": page_texts, "x_offset_pt": x_offset})
            x_offset += page_width + page_gap
        if not entities:
            raise ConversionError("PDF 未提取到可计算的矢量线段或文字；扫描件请先在本地完成 OCR/矢量化，不自动猜测")
        if vector_path_count == 0:
            warnings.append("PDF 仅提取到文字，没有矢量线段；专业工程量仍需人工补充几何依据")
        if page_count > 1:
            warnings.append("多页 PDF 已按页面横向排布到一个 DXF 模型空间，页面边界和比例需人工核对")
        document_out = DxfDocument(entities, [], "utf-8", "6")
        write_canonical_dxf(document_out, destination)
    finally:
        document.close()
    return {
        "status": "CONVERTED",
        "method": "local-pymupdf-vector-extraction",
        "source_format": "pdf",
        "converted_format": "dxf",
        "page_count": len(page_summaries),
        "vector_path_count": vector_path_count,
        "text_count": text_count,
        "entity_count": len(entities),
        "pages": page_summaries,
        "warnings": warnings,
    }


def _dwg_dxf(source: Path, destination: Path) -> dict[str, Any]:
    try:
        from ezdxf import options  # type: ignore
        from ezdxf.addons import odafc  # type: ignore
    except ImportError as exc:
        raise ConversionError("本机未安装 ezdxf/ODA 适配组件，无法进行 DWG→DXF；未上传 DWG") from exc
    configured = os.environ.get("MUNICIPAL_QTO_DWG_CONVERTER", "").strip()
    if configured:
        configured_path = Path(configured).expanduser()
        if not configured_path.is_file():
            raise ConversionError(f"MUNICIPAL_QTO_DWG_CONVERTER 不存在：{configured}")
        options.set("odafc-addon", "win_exec_path", str(configured_path))
    if not odafc.is_installed():
        raise ConversionError("未发现本机 DWG→DXF 转换器；请安装 ODA File Converter，并可用 MUNICIPAL_QTO_DWG_CONVERTER 指定 exe。系统未上传 DWG")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        odafc.convert(source, destination, version="R2018", audit=True, replace=True)
        if not destination.exists() or destination.stat().st_size == 0:
            raise ConversionError("本机 DWG 转换器未生成有效 DXF")
        parse_ascii_dxf(destination)
    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionError(f"本机 DWG→DXF 转换失败：{exc}") from exc
    return {
        "status": "CONVERTED",
        "method": "local-ezdxf-odafc",
        "source_format": "dwg",
        "converted_format": "dxf",
        "warnings": ["DWG 转 DXF 依赖部署机已安装的 ODA File Converter；转换后的实体、文字、单位仍需人工核对"],
    }


def convert_to_dxf(source: str | Path, destination: str | Path | None = None) -> dict[str, Any]:
    source_path = Path(source).expanduser().resolve()
    if not source_path.exists() or not source_path.is_file():
        raise ConversionError(f"输入文件不存在：{source}")
    extension = source_path.suffix.lower()
    if extension not in SUPPORTED_INPUT_EXTENSIONS:
        raise ConversionError(f"不支持的输入格式：{extension or '无扩展名'}；仅支持 DXF、PDF、DWG")
    if destination is None:
        destination_path = source_path.with_suffix(".dxf") if extension != ".dxf" else source_path
    else:
        destination_path = Path(destination).expanduser().resolve()
    if extension == ".dxf":
        return {
            "status": "NOT_NEEDED",
            "method": "identity",
            "source_format": "dxf",
            "converted_format": "dxf",
            "source_file": str(source_path),
            "converted_file": str(source_path),
            "source_sha256": sha256_file(source_path),
            "converted_sha256": sha256_file(source_path),
            "warnings": [],
        }
    if source_path.resolve() == destination_path.resolve():
        raise ConversionError("转换输出不能覆盖原始文件")
    if extension == ".pdf":
        details = _pdf_dxf(source_path, destination_path)
    else:
        details = _dwg_dxf(source_path, destination_path)
    details.update({
        "source_file": str(source_path),
        "converted_file": str(destination_path),
        "source_sha256": sha256_file(source_path),
        "converted_sha256": sha256_file(destination_path),
    })
    return details
