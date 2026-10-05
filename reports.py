"""PDF health report generation (fpdf2)."""
from datetime import date

from fpdf import FPDF

BRAND_RGB = (153, 53, 86)
TEXT_RGB = (60, 60, 60)
DISCLAIMER = (
    "CycleWise is for awareness only and does not replace professional medical advice. "
    "Always consult a qualified doctor."
)


def _heading(pdf, text):
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*BRAND_RGB)
    pdf.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*TEXT_RGB)


def build_health_report(user_name, start, end, stats, notes, symptoms):
    """Return the PDF as bytes.

    ``notes`` and ``symptoms`` are lists of ORM objects; only the first ten of
    each are printed so the report stays short.
    """
    pdf = FPDF()
    pdf.add_page()

    pdf.set_fill_color(*BRAND_RGB)
    pdf.rect(0, 0, 210, 28, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_xy(10, 8)
    pdf.cell(0, 12, "CycleWise Health Report", new_x="LMARGIN", new_y="NEXT")

    pdf.set_text_color(80, 80, 80)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(10, 32)
    period = f"{start} to {end}" if start else f"All time to {end}"
    pdf.cell(0, 6, f"Name: {user_name}  |  Period: {period}  |  Generated: {date.today()}",
             new_x="LMARGIN", new_y="NEXT")

    pdf.set_xy(10, 44)
    _heading(pdf, "Cycle Summary")
    pdf.set_font("Helvetica", "", 11)
    lines = [
        f"Average cycle length : {stats['avg_cycle']} days",
        f"Average period length: {stats['avg_period']} days",
        f"Total cycles tracked : {stats['total']}",
        f"Cycle pattern        : {'Irregular' if stats['irregular'] else 'Regular'}",
    ]
    if stats["next_period"]:
        lines.append(f"Next period predicted: {stats['next_period']}")
    for line in lines:
        pdf.cell(0, 7, line, new_x="LMARGIN", new_y="NEXT")

    if notes:
        pdf.ln(4)
        _heading(pdf, "Journal Notes")
        for n in notes[:10]:
            mood = f" [{n.mood_tag}]" if n.mood_tag else ""
            text = n.content[:100] + ("..." if len(n.content) > 100 else "")
            pdf.multi_cell(0, 6, f"{n.date}{mood}: {text}")
            pdf.ln(1)

    if symptoms:
        pdf.ln(4)
        _heading(pdf, "Symptoms Discussed")
        for s in symptoms[:10]:
            sev = f" ({s.severity})" if s.severity else ""
            cond = f" -> {s.condition}" if s.condition else ""
            pdf.multi_cell(0, 6, f"{s.date}{sev}: {s.text[:80]}{cond}")
            pdf.ln(1)

    pdf.ln(6)
    pdf.set_fill_color(245, 240, 255)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(100, 80, 150)
    pdf.multi_cell(0, 6, DISCLAIMER, fill=True)

    return bytes(pdf.output())
