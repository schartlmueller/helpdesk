"""Leistungsnachweis als PDF. Ohne Django, einzeln testbar."""

from io import BytesIO


def _hours(seconds):
    minutes = round(seconds / 60)
    return f"{minutes // 60}:{minutes % 60:02d} h"


def build_service_report(title, organization, period, groups, total_seconds, footer=""):
    """Erzeugt das PDF und gibt es als Bytes zurück.

    ``groups``: Liste von dicts mit ``label``, ``seconds`` und ``lines``;
    jede Zeile hat ``date``, ``person``, ``time``, ``seconds``, ``note``.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape

    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8.5, leading=11)
    bold = ParagraphStyle("bold", parent=small, fontName="Helvetica-Bold")
    head = ParagraphStyle("head", parent=styles["Title"], fontSize=16, alignment=0, spaceAfter=4)

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"{title} {organization}",
    )

    def cell(text, style=small):
        return Paragraph(escape(str(text)), style)

    story = [
        Paragraph(escape(title), head),
        Paragraph(f"<b>{escape(organization)}</b>", styles["Normal"]),
        Paragraph(escape(f"Zeitraum: {period}"), styles["Normal"]),
        Spacer(1, 6 * mm),
    ]

    rows = [[cell(t, bold) for t in ("Datum", "Bearbeiter", "Uhrzeit", "Tätigkeit", "Dauer")]]
    group_rows = []
    for group in groups:
        group_rows.append(len(rows))
        rows.append([cell(group["label"], bold), "", "", "", cell(_hours(group["seconds"]), bold)])
        for line in group["lines"]:
            rows.append(
                [
                    cell(line["date"]),
                    cell(line["person"]),
                    cell(line["time"]),
                    cell(line["note"]),
                    cell(_hours(line["seconds"])),
                ]
            )
    total_row = len(rows)
    rows.append([cell("Summe", bold), "", "", "", cell(_hours(total_seconds), bold)])

    table = Table(
        rows, colWidths=[22 * mm, 38 * mm, 26 * mm, 68 * mm, 20 * mm], repeatRows=1
    )
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
        ("LINEBELOW", (0, 1), (-1, -2), 0.25, colors.lightgrey),
        ("LINEABOVE", (0, total_row), (-1, total_row), 0.8, colors.black),
        ("ALIGN", (4, 0), (4, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for index in group_rows:
        style.append(("SPAN", (0, index), (3, index)))
        style.append(("BACKGROUND", (0, index), (-1, index), colors.HexColor("#eef1f4")))
    table.setStyle(TableStyle(style))
    story.append(table)
    if footer:
        story += [Spacer(1, 8 * mm), Paragraph(escape(footer), small)]

    def page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Seite {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=page_number, onLaterPages=page_number)
    return buffer.getvalue()
