from __future__ import annotations

import html
import json
import os
import zipfile
from pathlib import Path
from typing import Any, Iterable


class ExportError(ValueError):
    """Raised when a local result cannot be exported safely."""


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _pdf_text(value: Any) -> str:
    """Keep common engineering units readable in fonts without superscripts."""
    return _text(value).replace("²", "2").replace("³", "3").replace("×", " x ").replace("π", "pi")


def _xlsx_cell(ref: str, value: Any, style: int = 0) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return f'<c r="{ref}" s="{style}" t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
    escaped = html.escape(_text(value), quote=False)
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escaped}</t></is></c>'


def _column_name(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _sheet_xml(rows: Iterable[Iterable[Any]], widths: list[int]) -> str:
    row_xml: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells: list[str] = []
        for column_index, value in enumerate(row, start=1):
            style = 0
            if row_index == 1:
                style = 1
            elif row_index in {5, 6}:
                style = 2
            elif isinstance(value, (int, float)):
                style = 3
            cell = _xlsx_cell(f"{_column_name(column_index)}{row_index}", value, style)
            if cell:
                cells.append(cell)
        row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    cols = "".join(f'<col min="{i}" max="{i}" width="{width}" customWidth="1"/>' for i, width in enumerate(widths, start=1))
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane state="frozen" ySplit="5" topLeftCell="A6"/></sheetView></sheetViews><cols>{cols}</cols><sheetData>{"".join(row_xml)}</sheetData></worksheet>'


def _styles_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><numFmts count="0"/><fonts count="2"><font><sz val="10"/><name val="Microsoft YaHei"/></font><font><b/><sz val="12"/><name val="Microsoft YaHei"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="solid"><fgColor rgb="DCEAF0"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/><xf numFmtId="0" fontId="1" fillId="1" borderId="0"/><xf numFmtId="0" fontId="0" fillId="1" borderId="0"/><xf numFmtId="2" fontId="0" fillId="0" borderId="0"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''


def _workbook_xml(sheet_names: list[str]) -> str:
    sheets = "".join(f'<sheet name="{html.escape(name, quote=True)}" sheetId="{i}" r:id="rId{i}"/>' for i, name in enumerate(sheet_names, start=1))
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{sheets}</sheets></workbook>'


def export_xlsx(job: dict[str, Any], destination: str | Path) -> Path:
    if not isinstance(job, dict) or not isinstance(job.get("calculation"), dict):
        raise ExportError("作业缺少可导出的 calculation 结果")
    calculation = job["calculation"]
    source = job.get("source", {})
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    totals = calculation.get("totals", [])
    quantities = calculation.get("quantities", [])
    warnings = list(source.get("warnings", [])) + list(source.get("conversion_warnings", [])) + list(calculation.get("warnings", []))
    summary_rows = [
        ["重庆市政 CAD 工程量计算成果（Excel）"],
        ["作业编号", job.get("job_id", ""), "项目编号", job.get("project_id", "")],
        ["源图文件", source.get("source_file", ""), "源图 SHA-256", source.get("source_sha256", "")],
        ["转换状态", source.get("conversion_status", "未记录"), "审核状态", calculation.get("review_status", "待人工审核")],
        [],
        ["编码", "分项", "单位", "总数量"],
        *[[item.get("item_code", ""), item.get("item", ""), item.get("unit", ""), item.get("quantity", 0)] for item in totals],
    ]
    detail_rows = [
        ["工程量明细（可追溯草稿）"],
        ["作业编号", job.get("job_id", ""), "规则包", calculation.get("rule_pack_version", "")],
        [],
        [],
        ["专业", "断面/分段", "起点", "终点", "编码", "分项", "单位", "数量", "公式", "状态", "证据"],
        *[[item.get("discipline", ""), item.get("section_id", ""), item.get("station_start", ""), item.get("station_end", ""), item.get("item_code", ""), item.get("item", ""), item.get("unit", ""), item.get("quantity", 0), item.get("formula", ""), item.get("status", "Inference"), item.get("evidence_refs", [])] for item in quantities],
    ]
    evidence_rows = [
        ["证据、转换与审核状态"],
        ["原始文件", source.get("original_file", source.get("source_file", ""))],
        ["计算输入 DXF", source.get("source_file", "")],
        ["原始 SHA-256", source.get("original_sha256", source.get("source_sha256", ""))],
        ["计算 DXF SHA-256", source.get("source_sha256", "")],
        ["转换方式", source.get("conversion_method", "identity")],
        ["审核状态", calculation.get("review_status", "待人工审核")],
        ["语义状态", calculation.get("semantic_status", "Hypothesis")],
        [],
        ["告警", "内容"],
        *[[warning.get("code", "SOURCE"), warning.get("message", "")] if isinstance(warning, dict) else ["SOURCE", warning] for warning in warnings],
    ]
    sheets = [("算量汇总", summary_rows, [22, 34, 12, 18]), ("工程量明细", detail_rows, [12, 16, 14, 14, 22, 34, 10, 14, 48, 16, 48]), ("证据与审核", evidence_rows, [22, 70])]
    content_types = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
    for index in range(1, len(sheets) + 1):
        content_types.append(f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
    content_types.append("</Types>")
    workbook_rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>']
    for index in range(1, len(sheets) + 1):
        workbook_rels.append(f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>')
    workbook_rels.append("</Relationships>")
    with zipfile.ZipFile(destination_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "".join(content_types))
        archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rIdWorkbook" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr("xl/workbook.xml", _workbook_xml([name for name, _, _ in sheets]))
        archive.writestr("xl/_rels/workbook.xml.rels", "".join(workbook_rels))
        archive.writestr("xl/styles.xml", _styles_xml())
        for index, (_, rows, widths) in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(rows, widths))
    return destination_path


def export_pdf(job: dict[str, Any], destination: str | Path) -> Path:
    try:
        from reportlab.lib import colors  # type: ignore
        from reportlab.lib.enums import TA_LEFT  # type: ignore
        from reportlab.lib.pagesizes import A4, landscape  # type: ignore
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore
        from reportlab.lib.units import mm  # type: ignore
        from reportlab.pdfbase import pdfmetrics  # type: ignore
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont  # type: ignore
        from reportlab.pdfbase.ttfonts import TTFont  # type: ignore
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # type: ignore
    except ImportError as exc:
        raise ExportError("本机未安装 reportlab，无法生成 PDF 成果") from exc
    if not isinstance(job, dict) or not isinstance(job.get("calculation"), dict):
        raise ExportError("作业缺少可导出的 calculation 结果")
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    calculation = job["calculation"]
    source = job.get("source", {})
    font_name = "STSong-Light"
    if "MunicipalCjk" not in pdfmetrics.getRegisteredFontNames():
        font_candidates = [
            Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "simhei.ttf",
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        ]
        for font_path in font_candidates:
            if not font_path.is_file():
                continue
            try:
                pdfmetrics.registerFont(TTFont("MunicipalCjk", str(font_path)))
                font_name = "MunicipalCjk"
                break
            except Exception:
                continue
    if font_name == "STSong-Light":
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    styles = getSampleStyleSheet()
    title = ParagraphStyle("CadTitle", parent=styles["Title"], fontName=font_name, fontSize=16, leading=21, alignment=TA_LEFT, textColor=colors.HexColor("#163B4A"))
    body = ParagraphStyle("CadBody", parent=styles["BodyText"], fontName=font_name, fontSize=8.5, leading=12)
    small = ParagraphStyle("CadSmall", parent=body, fontSize=7, leading=9)
    document = SimpleDocTemplate(str(destination_path), pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm, title="重庆市政 CAD 工程量计算成果")
    story: list[Any] = [Paragraph("重庆市政 CAD 工程量计算成果（待人工审核）", title), Spacer(1, 5 * mm)]
    story.append(Paragraph(f"作业：{_pdf_text(job.get('job_id'))}　项目：{_pdf_text(job.get('project_id'))}　规则包：{_pdf_text(calculation.get('rule_pack_version'))}", body))
    story.append(Paragraph(f"计算 DXF：{_pdf_text(source.get('source_file'))}　SHA-256：{_pdf_text(source.get('source_sha256'))}", small))
    story.append(Spacer(1, 4 * mm))
    totals = [["编码", "分项", "单位", "总数量"]] + [[_pdf_text(item.get("item_code")), _pdf_text(item.get("item")), _pdf_text(item.get("unit")), _pdf_text(item.get("quantity"))] for item in calculation.get("totals", [])]
    total_table = Table(totals, colWidths=[42 * mm, 92 * mm, 22 * mm, 28 * mm], repeatRows=1)
    total_table.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), font_name), ("FONTSIZE", (0, 0), (-1, -1), 8), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCEAF0")), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#9CB2BA")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (-1, 1), (-1, -1), "RIGHT")]))
    story.extend([Paragraph("一、工程量汇总", body), total_table, Spacer(1, 4 * mm)])
    detail_data = [["专业", "断面/分段", "编码", "分项", "单位", "数量", "公式", "状态"]]
    for item in calculation.get("quantities", [])[:200]:
        detail_data.append([_pdf_text(item.get("discipline")), _pdf_text(item.get("section_id")), _pdf_text(item.get("item_code")), _pdf_text(item.get("item")), _pdf_text(item.get("unit")), _pdf_text(item.get("quantity")), _pdf_text(item.get("formula")), _pdf_text(item.get("status", "Inference"))])
    detail_table = Table(detail_data, colWidths=[18 * mm, 25 * mm, 38 * mm, 55 * mm, 16 * mm, 22 * mm, 80 * mm, 24 * mm], repeatRows=1)
    detail_table.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), font_name), ("FONTSIZE", (0, 0), (-1, -1), 6.5), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCEAF0")), ("GRID", (0, 0), (-1, -1), 0.2, colors.HexColor("#B4C4C8")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.extend([Paragraph("二、工程量明细（最多展示 200 条，完整数据以 Excel 为准）", body), detail_table, Spacer(1, 4 * mm)])
    warnings = list(source.get("warnings", [])) + list(source.get("conversion_warnings", [])) + list(calculation.get("warnings", []))
    evidence = [["项目", "内容"], ["原始文件", _pdf_text(source.get("original_file", source.get("source_file")))], ["转换方式", _pdf_text(source.get("conversion_method", "identity"))], ["审核状态", _pdf_text(calculation.get("review_status", "待人工审核"))], ["语义/计算状态", f"{_pdf_text(calculation.get('semantic_status', 'Hypothesis'))} / Inference"]]
    evidence.extend([["告警", _pdf_text(item.get("message", item) if isinstance(item, dict) else item)] for item in warnings])
    evidence_table = Table(evidence, colWidths=[35 * mm, 243 * mm], repeatRows=1)
    evidence_table.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), font_name), ("FONTSIZE", (0, 0), (-1, -1), 7), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCEAF0")), ("GRID", (0, 0), (-1, -1), 0.2, colors.HexColor("#B4C4C8")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.extend([Paragraph("三、证据与人工审核", body), evidence_table, Spacer(1, 3 * mm), Paragraph("本成果为 Inference 草稿，不替代原图、设计说明、断面表和人工复核；未经审核不得作为结算事实。", small)])
    document.build(story)
    return destination_path
