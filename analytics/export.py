from __future__ import annotations

import csv
import io
import json
import zipfile
from typing import Any
from xml.sax.saxutils import escape


def export_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def export_csv(payload: dict[str, Any]) -> bytes:
    """Flatten key dashboard metrics + ranking tables into CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["section", "key", "value"])

    def emit(section: str, key: str, value: Any) -> None:
        if isinstance(value, (dict, list)):
            writer.writerow([section, key, json.dumps(value, ensure_ascii=False)])
        else:
            writer.writerow([section, key, value])

    meta_keys = [
        "company_name",
        "branch_name",
        "overall_score",
        "branch_score",
        "total_reviews",
        "review_count",
        "total_branches",
        "average_rating",
        "google_rating",
        "ai_rating",
        "customer_satisfaction_index",
        "confidence_score",
        "ai_executive_summary",
        "ai_branch_summary",
    ]
    for key in meta_keys:
        if key in payload:
            emit("summary", key, payload[key])

    for section in (
        "sentiment_distribution",
        "complaint_categories",
        "positive_categories",
        "complaint_breakdown",
        "positive_breakdown",
        "province_distribution",
        "city_distribution",
        "branch_ranking",
        "review_trend",
        "rating_trend",
        "score_trend",
        "staff_mentions",
        "monthly_review_volume",
    ):
        if section in payload:
            emit(section, "data", payload[section])

    return buf.getvalue().encode("utf-8")


def export_excel(payload: dict[str, Any]) -> bytes:
    """Minimal XLSX (Office Open XML) without third-party deps."""
    rows = [["section", "key", "value"]]
    for line in export_csv(payload).decode("utf-8").splitlines()[1:]:
        rows.append(next(csv.reader([line])))

    sheet_rows = []
    for r_idx, row in enumerate(rows, start=1):
        cells = []
        for c_idx, value in enumerate(row, start=1):
            col = _col_name(c_idx)
            text = escape(str(value))
            cells.append(
                f'<c r="{col}{r_idx}" t="inlineStr"><is><t>{text}</t></is></c>'
            )
        sheet_rows.append(f"<row r=\"{r_idx}\">{''.join(cells)}</row>")

    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(sheet_rows)}</sheetData></worksheet>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Analytics" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


def export_pdf(payload: dict[str, Any]) -> bytes:
    """Simple single-page text PDF (no external deps)."""
    title = (
        payload.get("company_name")
        or payload.get("branch_name")
        or "BrandMonitor Analytics"
    )
    lines = [
        "BrandMonitor Executive Analytics",
        str(title),
        "",
        f"Score: {payload.get('overall_score', payload.get('branch_score'))}",
        f"Reviews: {payload.get('total_reviews', payload.get('review_count'))}",
        f"CSI: {payload.get('customer_satisfaction_index')}",
        f"Confidence: {payload.get('confidence_score')}",
        "",
        str(payload.get("ai_executive_summary") or payload.get("ai_branch_summary") or ""),
        "",
        "Strengths: " + ", ".join(payload.get("biggest_strengths") or payload.get("positive_breakdown") and [x.get('name','') for x in payload.get('positive_breakdown',[])[:5]] or []),
        "Improvements: " + ", ".join(payload.get("biggest_improvements_needed") or payload.get("improvement_suggestions") or []),
    ]
    # Escape PDF string specials
    content_lines = []
    y = 800
    for line in lines:
        safe = str(line).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_lines.append(f"BT /F1 11 Tf 50 {y} Td ({safe[:110]}) Tj ET")
        y -= 16
        if y < 50:
            break
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")
    objects = []
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    objects.append(
        f"4 0 obj<< /Length {len(stream)} >>stream\n".encode("ascii")
        + stream
        + b"\nendstream\nendobj\n"
    )
    objects.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(out.tell())
        out.write(obj)
    xref_pos = out.tell()
    out.write(f"xref\n0 {len(objects)+1}\n".encode("ascii"))
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode("ascii"))
    out.write(
        f"trailer<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return out.getvalue()


def export_chart_png_svg(chart: dict[str, Any]) -> bytes:
    """Export a simple SVG bar/line stand-in (PNG requested → SVG downloadable)."""
    labels = chart.get("labels") or []
    values = [float(v) for v in (chart.get("values") or [])]
    width = 640
    height = 360
    max_v = max(values) if values else 1.0
    bars = []
    n = max(len(values), 1)
    bar_w = (width - 80) / n
    for i, (label, value) in enumerate(zip(labels, values)):
        h = 0 if max_v == 0 else (value / max_v) * (height - 80)
        x = 40 + i * bar_w
        y = height - 40 - h
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w*0.7:.1f}" height="{h:.1f}" fill="#1f6feb"/>'
            f'<text x="{x:.1f}" y="{height-20}" font-size="10">{escape(str(label)[:12])}</text>'
        )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        f'<rect width="100%" height="100%" fill="#fff"/>'
        f'<text x="20" y="24" font-size="14">BrandMonitor chart ({escape(str(chart.get("type")))})</text>'
        f'{"".join(bars)}</svg>'
    )
    return svg.encode("utf-8")


def _col_name(idx: int) -> str:
    name = ""
    while idx:
        idx, rem = divmod(idx - 1, 26)
        name = chr(65 + rem) + name
    return name
