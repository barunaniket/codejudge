"""Generate a downloadable PDF audit report with fpdf2."""
from fpdf import FPDF
from fpdf.enums import XPos, YPos

SEV_COLORS = {"critical": (190, 30, 45), "high": (230, 90, 30),
              "medium": (210, 160, 0), "low": (90, 120, 160)}
AGENT_NAMES = {"security": "Security", "performance": "Performance", "quality": "Code Quality"}


def _t(text) -> str:
    """Core PDF fonts are latin-1 only; replace anything else."""
    return str(text).encode("latin-1", "replace").decode("latin-1")


def build_pdf(a: dict) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()

    def line(text, size=10, style="", color=(30, 30, 30), h=5.5, font="Helvetica"):
        pdf.set_font(font, style, size)
        pdf.set_text_color(*color)
        pdf.multi_cell(0, h, _t(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Header
    pdf.set_fill_color(17, 24, 39)
    pdf.rect(0, 0, 210, 32, "F")
    pdf.set_xy(12, 9)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 8, "CodeJudge Audit Report")
    pdf.set_xy(12, 19)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, _t(f"{a['filename']}  |  model {a['model']}  |  {a['created_at']}  |  {a['duration_s']}s"))
    pdf.set_y(40)

    # Grade + scores
    line(f"Overall grade: {a['grade']}   ({a['overall']}/10)", 16, "B")
    if a.get("critical_cap"):
        line("Grade capped at D because a critical security issue was found.", 9, "I", (190, 30, 45))
    pdf.ln(1)
    for k, v in a["scores"].items():
        line(f"{AGENT_NAMES.get(k, k)}: {v}/10", 11)
    pdf.ln(3)

    line("Executive verdict", 13, "B")
    line(a.get("verdict") or "-", 10)
    if a.get("top_risks"):
        pdf.ln(1)
        for r in a["top_risks"]:
            line(f"  -  {r}", 10)
    pdf.ln(4)

    # Agent findings
    for key, agent in a["agents"].items():
        line(f"{AGENT_NAMES.get(key, key)} Agent  -  {agent['score']}/10", 13, "B")
        if agent.get("summary"):
            line(agent["summary"], 9, "I", (80, 80, 80))
        if not agent["issues"]:
            line("No issues found.", 10, color=(40, 140, 70))
        for i in agent["issues"]:
            cwe = f"  [{i['cwe']}]" if i.get("cwe") else ""
            line(f"[{i['severity'].upper()}] line {i['line']}: {i['title']}{cwe}", 10, "B",
                 SEV_COLORS.get(i["severity"], (0, 0, 0)))
            line(i["description"], 9, color=(60, 60, 60))
            pdf.ln(1)
        pdf.ln(3)

    # Static verification
    if a.get("static"):
        line("Static analysis verification (Bandit / Pylint + LLM judge)", 13, "B")
        for f in a["static"]:
            v = {"true_positive": "CONFIRMED", "false_positive": "FALSE ALARM"}.get(f.get("verdict"), "UNVERIFIED")
            col = (190, 30, 45) if v == "CONFIRMED" else (40, 140, 70) if v == "FALSE ALARM" else (120, 120, 120)
            line(f"{v}  |  {f['tool']} {f['rule']} line {f['line']}: {f['message']}", 9, "B", col)
            line(f"Judge: {f.get('reason', '')}", 9, color=(60, 60, 60))
            pdf.ln(1)

    # Fixed code
    if a.get("fixed_code"):
        pdf.add_page()
        line("Suggested fixed code", 13, "B")
        pdf.ln(2)
        line(a["fixed_code"], 8, font="Courier", h=4)

    return bytes(pdf.output())
