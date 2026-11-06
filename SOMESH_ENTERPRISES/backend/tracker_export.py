"""Read-only PDF rendering of the existing Tracker response."""
import io
import os
from xml.sax.saxutils import escape


def tracker_pdf(tracker):
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, LongTable, Paragraph, Spacer, TableStyle

    # Use the fonts shipped with ReportLab, including on machines without system fonts.
    for name, filename in (("Tracker", "Vera.ttf"), ("TrackerBold", "VeraBd.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, os.path.join(os.path.dirname(reportlab.__file__), "fonts", filename)))
    normal = ParagraphStyle("cell", fontName="Tracker", fontSize=8, leading=11, splitLongWords=True)
    center = ParagraphStyle("time", parent=normal, alignment=TA_CENTER)
    header = ParagraphStyle("header", parent=normal, fontName="TrackerBold", textColor=colors.white)
    title = ParagraphStyle("title", parent=normal, fontName="TrackerBold", fontSize=18, leading=24)

    def cell(value, style=normal):
        return Paragraph(escape(str(value if value is not None else "–")).replace("\n", "<br/>"), style)

    def time(value):
        return str(value)[11:16] if value else "–"

    def duration(seconds):
        seconds = max(0, int(seconds or 0))
        return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"

    headings = ["Person", "Task", "Started", "Done", "Approved", "Ended", "Worked", "Status", "Docs"]
    data = [[cell(label, header) for label in headings]]
    for row in tracker["rows"]:
        docs = "\n".join(str(doc.get("name") or doc.get("path") or "Document") for doc in row.get("docs", [])) or "–"
        task = f"{row['code']} {row['task']}\n{row.get('type', '')}"
        if row.get("bill"):
            task += f" · {row['bill']}"
        data.append([cell(f"{row['person']}\n{row['dept']}"), cell(task),
                     *[cell(time(row.get(key)), center) for key in ("started_at", "done_at", "approved_at", "ended_at")],
                     cell(duration(row["day_seconds"]), center), cell(row["status"]), cell(docs)])
    empty = len(data) == 1
    if empty:
        data.append([cell("No tracked tasks for this day.")] + [""] * 8)
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), rightMargin=24, leftMargin=24,
                            topMargin=26, bottomMargin=30, title="Employee Task Tracker")
    widths = [78, 169, 49, 43, 58, 43, 56, 100, doc.width - 696]
    table = LongTable(data, colWidths=widths, repeatRows=1, splitByRow=1, splitInRow=1, hAlign="LEFT")
    style = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d1d1f")),
             ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bfc3c9")),
             ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
             ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f7")])]
    if empty:
        style.append(("SPAN", (0, 1), (-1, 1)))
    table.setStyle(TableStyle(style))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Tracker", 8)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(24, 16, f"Tracker · {tracker['date']}")
        canvas.drawRightString(document.pagesize[0] - 24, 16, f"Page {document.page}")
        canvas.restoreState()

    doc.build([cell("Employee Task Tracker", title), Spacer(1, 5),
               cell(f"Date: {tracker['date']} · {len(tracker['rows'])} task records"), Spacer(1, 14), table],
              onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()
