from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from math import ceil
from pathlib import Path
from typing import Any

from .canonical import sha256_file
from .dxf import DxfDocument, Entity, parse_ascii_dxf, write_canonical_dxf


SUPPORTED_INPUT_EXTENSIONS = {".dxf", ".pdf", ".dwg"}
DWG_CONVERTER_ENV = "MUNICIPAL_QTO_DWG_CONVERTER"
ODA_DEFAULT_PATHS = (
    Path(r"C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe"),
    Path(r"C:\Program Files (x86)\ODA\ODAFileConverter\ODAFileConverter.exe"),
)


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


def _find_oda_converter() -> Path | None:
    configured = os.environ.get(DWG_CONVERTER_ENV, "").strip().strip('"')
    if configured:
        configured_path = Path(configured).expanduser()
        if not configured_path.is_file():
            raise ConversionError(f"{DWG_CONVERTER_ENV} 指向的程序不存在：{configured}")
        return configured_path.resolve()
    for candidate in ODA_DEFAULT_PATHS:
        if candidate.is_file():
            return candidate.resolve()
    for command in ("ODAFileConverter.exe", "ODAFileConverter"):
        found = shutil.which(command)
        if found:
            return Path(found).resolve()
    return None


def dwg_converter_status() -> dict[str, Any]:
    """Return a safe local readiness status without exposing executable paths."""
    try:
        converter = _find_oda_converter()
    except ConversionError as exc:
        return {"available": False, "status": "CONFIG_ERROR", "message": str(exc)}
    if converter is None:
        return {
            "available": False,
            "status": "MISSING",
            "message": "未发现本机 ODA File Converter；DWG 需先转成 DXF",
        }
    return {"available": True, "status": "READY", "message": "本机 ODA File Converter 可用"}


def _oda_startupinfo() -> Any:
    if os.name != "nt":
        return None
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return startupinfo


def _tool_output(stdout: str, stderr: str) -> str:
    combined = "；".join(part.strip() for part in (stdout, stderr) if part and part.strip())
    return combined[:1200]


def _dwg_dxf(source: Path, destination: Path) -> dict[str, Any]:
    converter = _find_oda_converter()
    if converter is None:
        try:
            signature = source.read_bytes()[:6].decode("ascii", errors="replace")
        except OSError:
            signature = "未知"
        raise ConversionError(
            f"DWG 文件已收到，版本标记 {signature or '未知'}；但本机未发现 ODA File Converter，"
            f"无法完成 DWG→DXF。请安装 ODA File Converter，或设置 {DWG_CONVERTER_ENV} 指向 ODAFileConverter.exe。"
        )

    try:
        with tempfile.TemporaryDirectory(prefix="municipal_qto_oda_") as output_folder:
            output_dir = Path(output_folder)
            command = [
                str(converter),
                str(source.parent),
                str(output_dir),
                "ACAD2018",
                "DXF",
                "0",
                "1",
                source.name,
            ]
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=180,
                    startupinfo=_oda_startupinfo(),
                )
            except FileNotFoundError as exc:
                raise ConversionError(f"已找到 ODA 转换器，但无法启动：{converter.name}") from exc
            except PermissionError as exc:
                raise ConversionError(f"ODA 转换器没有执行权限：{converter.name}") from exc
            except subprocess.TimeoutExpired as exc:
                raise ConversionError("本机 DWG→DXF 转换超过 180 秒，已停止，未采用不完整输出") from exc
            if completed.returncode != 0:
                detail = _tool_output(completed.stdout, completed.stderr)
                suffix = f"；程序输出：{detail}" if detail else ""
                raise ConversionError(f"本机 ODA DWG→DXF 转换失败，返回码 {completed.returncode}{suffix}")

            candidates = [
                item for item in output_dir.iterdir()
                if item.is_file() and item.suffix.lower() == ".dxf" and item.stem.casefold() == source.stem.casefold()
            ]
            if len(candidates) != 1:
                raise ConversionError(f"ODA 转换未生成唯一的 {source.stem}.dxf，未采用不确定输出")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidates[0], destination)
    except ConversionError:
        raise
    except OSError as exc:
        raise ConversionError(f"本机 DWG→DXF 文件处理失败：{exc}") from exc

    if not destination.exists() or destination.stat().st_size == 0:
        raise ConversionError("本机 DWG 转换器未生成有效 DXF")
    try:
        parse_ascii_dxf(destination)
    except Exception as exc:
        raise ConversionError(f"ODA 已生成 DXF，但项目解析器无法读取该输出：{exc}") from exc
    return {
        "status": "CONVERTED",
        "method": "local-oda-cli",
        "source_format": "dwg",
        "converted_format": "dxf",
        "warnings": ["DWG 转 DXF 由本机 ODA File Converter 完成；转换后的实体、文字、单位仍需人工核对"],
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
