"""The downloadable PDF report. Email and IP addresses are left out, since PDFs get shared."""
import re
from collections import Counter
from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Circle, Drawing, Rect, String, Wedge
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFError, TTFont
from reportlab.platypus import (CondPageBreak, KeepTogether, NextPageTemplate, PageBreak, PageTemplate, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)
from reportlab.platypus.frames import Frame

from ..catalog import COMPUTERS, DEFENSES, NETWORK_GEAR, OPERATING_SYSTEMS, PASSWORD_TYPES
from .graph_engine import SEVERITY_ORDER, analyze, build_model
from .questions import account_rows

INK = colors.HexColor("#0f1a2b")
BODY = colors.HexColor("#27364a")
MUTED = colors.HexColor("#66768c")
LINE = colors.HexColor("#dde4ec")
PANEL = colors.HexColor("#f4f7fa")
ACCENT = colors.HexColor("#0f9d76")
ACCENT_BRIGHT = colors.HexColor("#34d399")  # The icon's own green.
COVER = colors.HexColor("#0a111d")
COVER_TEXT = colors.HexColor("#e4ebf5")
COVER_MUTED = colors.HexColor("#8e9db3")
SEVERITY = {
    "critical": colors.HexColor("#d92d20"), "high": colors.HexColor("#e8710a"),
    "medium": colors.HexColor("#d9a400"), "low": colors.HexColor("#7c8a9e"),
}
SECTIONS = [("vulnerabilities", "Vulnerabilities"), ("recommendations", "Recommendations"), ("topology", "Topology")]
PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
WIDTH = PAGE_W - 2 * MARGIN


# Regular, bold and light, in order of preference: Windows, then common Linux locations.
FONT_CANDIDATES = [
    ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/segoeuil.ttf"),
    *[
        (f"{folder}/DejaVuSans.ttf", f"{folder}/DejaVuSans-Bold.ttf", f"{folder}/DejaVuSans-ExtraLight.ttf")
        for folder in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu-sans-fonts",
                       "/usr/share/fonts/TTF", "/usr/share/fonts/dejavu")
    ],
    *[
        (f"{folder}/LiberationSans-Regular.ttf", f"{folder}/LiberationSans-Bold.ttf", f"{folder}/LiberationSans-Regular.ttf")
        for folder in ("/usr/share/fonts/truetype/liberation", "/usr/share/fonts/liberation-sans")
    ],
]


def _fonts() -> tuple[str, str, str]:
    """Prefers a system font, because the built-in PDF fonts can't show names like "Mălina"."""
    for regular, bold, light in FONT_CANDIDATES:
        try:
            pdfmetrics.registerFont(TTFont("Report", regular))
            pdfmetrics.registerFont(TTFont("Report-Bold", bold))
            pdfmetrics.registerFont(TTFont("Report-Light", light if Path(light).exists() else regular))
        except (TTFError, OSError):
            continue
        pdfmetrics.registerFontFamily("Report", normal="Report", bold="Report-Bold", italic="Report", boldItalic="Report-Bold")
        return "Report", "Report-Bold", "Report-Light"
    return "Helvetica", "Helvetica-Bold", "Helvetica"


REGULAR, BOLD, LIGHT = _fonts()
STYLES = {
    "body": ParagraphStyle("body", fontName=REGULAR, fontSize=9.5, leading=13.5, textColor=BODY),
    "muted": ParagraphStyle("muted", fontName=REGULAR, fontSize=8.5, leading=12, textColor=MUTED),
    "h1": ParagraphStyle("h1", fontName=BOLD, fontSize=17, leading=22, textColor=INK, spaceAfter=3 * mm),
    "h2": ParagraphStyle("h2", fontName=BOLD, fontSize=11.5, leading=15, textColor=INK, spaceBefore=4 * mm, spaceAfter=2 * mm),
    "card_title": ParagraphStyle("card_title", fontName=BOLD, fontSize=9.5, leading=13, textColor=INK),
    "cell": ParagraphStyle("cell", fontName=REGULAR, fontSize=8.3, leading=10.8, textColor=BODY),
    "head": ParagraphStyle("head", fontName=BOLD, fontSize=7.8, leading=10, textColor=MUTED),
    "tag": ParagraphStyle("tag", fontName=BOLD, fontSize=7, leading=9, textColor=colors.white, alignment=TA_CENTER),
    "stat": ParagraphStyle("stat", fontName=BOLD, fontSize=19, leading=23, textColor=INK, alignment=TA_CENTER),
    "stat_label": ParagraphStyle("stat_label", fontName=REGULAR, fontSize=7.8, leading=10, textColor=MUTED, alignment=TA_CENTER),
}


def _text(value) -> str:
    return escape(str(value))


def _paragraph(value, style: str = "body") -> Paragraph:
    return Paragraph(_text(value), STYLES[style])


def _rich(text: str) -> list:
    """Turns the model's plain text into paragraphs. It's untrusted, so it's escaped first."""
    flowables = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", _text(line))
        bullet = re.match(r"^(?:[-*•]|\d+[.)])\s+(.*)", safe)
        if bullet:
            style = ParagraphStyle("item", parent=STYLES["body"], leftIndent=4 * mm, bulletIndent=1 * mm, spaceAfter=1.2 * mm)
            flowables.append(Paragraph(bullet.group(1), style, bulletText="•"))
        else:
            heading = re.match(r"^#+\s*(.*)", safe)
            flowables.append(Paragraph(heading.group(1), STYLES["card_title"]) if heading
                             else Paragraph(safe, ParagraphStyle("p", parent=STYLES["body"], spaceAfter=1.8 * mm)))
    return flowables


def _table(rows: list[list], widths: list[float], repeat_header: bool = True) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1 if repeat_header else 0)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 2.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _header_row(*titles: str) -> list:
    return [_paragraph(title, "head") for title in titles]


def _severity_tag(severity: str) -> Table:
    tag = Table([[Paragraph(severity.upper(), STYLES["tag"])]], colWidths=[16 * mm])
    tag.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SEVERITY.get(severity, MUTED)),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("ROUNDEDCORNERS", [2, 2, 2, 2]),
    ]))
    return tag


def _card(severity: str, title: str, detail: str) -> Table:
    card = Table(
        [[_severity_tag(severity), [_paragraph(title, "card_title"), Spacer(1, 1), _paragraph(detail, "cell")]]],
        colWidths=[20 * mm, WIDTH - 20 * mm],
    )
    card.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBEFORE", (0, 0), (0, -1), 2.2, SEVERITY.get(severity, MUTED)),
        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (0, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return card


def _score_color(score: int):
    if score >= 70:
        return ACCENT
    return SEVERITY["medium"] if score >= 40 else SEVERITY["critical"]


def _gauge(score: int, size: float = 150, on_dark: bool = True) -> Drawing:
    drawing = Drawing(size, size)
    middle = size / 2
    track = colors.HexColor("#22304a") if on_dark else LINE
    drawing.add(Circle(middle, middle, middle - 2, fillColor=track, strokeColor=None))
    if score > 0:
        sweep = 360 * min(score, 99.9) / 100
        drawing.add(Wedge(middle, middle, middle - 2, 90 - sweep, 90, fillColor=_score_color(score), strokeColor=None))
    drawing.add(Circle(middle, middle, middle - 15, fillColor=COVER if on_dark else colors.white, strokeColor=None))
    drawing.add(String(middle, middle - 6, str(score), fontName=BOLD, fontSize=size * 0.26,
                       fillColor=COVER_TEXT if on_dark else INK, textAnchor="middle"))
    drawing.add(String(middle, middle - size * 0.2, "out of 100", fontName=REGULAR, fontSize=size * 0.06,
                       fillColor=COVER_MUTED if on_dark else MUTED, textAnchor="middle"))
    return drawing


def _bars(values: list[tuple[str, int, object]], width: float = WIDTH) -> Drawing:
    """Horizontal bars with direct labels, so no axis or legend is needed."""
    row, label_w, value_w = 17, 92, 26
    drawing = Drawing(width, row * len(values))
    biggest = max([value for _, value, _ in values] + [1])
    for index, (label, value, color) in enumerate(values):
        y = row * (len(values) - index - 1) + 3
        drawing.add(String(0, y + 2, label, fontName=REGULAR, fontSize=8.3, fillColor=BODY))
        track = width - label_w - value_w
        drawing.add(Rect(label_w, y, track, 9, fillColor=PANEL, strokeColor=None, rx=2, ry=2))
        if value:
            drawing.add(Rect(label_w, y, max(3, track * value / biggest), 9, fillColor=color, strokeColor=None, rx=2, ry=2))
        drawing.add(String(width, y + 1.5, str(value), fontName=BOLD, fontSize=8.5, fillColor=INK, textAnchor="end"))
    return drawing


def _stats(items: list[tuple[object, str]]) -> Table:
    cell = WIDTH / len(items)
    table = Table([[[_paragraph(value, "stat"), _paragraph(label, "stat_label")] for value, label in items]], colWidths=[cell] * len(items))
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PANEL), ("INNERGRID", (0, 0), (-1, -1), 3, colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _posture(accounts: list[dict]) -> int:
    """Average account score, counting important accounts more, and ignoring unrecorded ones."""
    weights = {"critical": 8, "high": 4, "medium": 2, "low": 1}
    known = [a for a in accounts if a["recorded"]]
    total = sum(weights.get(a["level"], 1) for a in known)
    return round(sum(a["score"] * weights.get(a["level"], 1) for a in known) / total) if total else 0


def _strength_buckets(accounts: list[dict]) -> list[tuple[str, int, object]]:
    def bucket(account: dict) -> str:
        if not account["recorded"]:
            return "Not recorded"
        if account["passkey"] or "hardware_key" in account["factors"]:
            return "Passkey / hardware"
        if {"totp", "push_2fa"} & set(account["factors"]):
            return "TOTP / push"
        return "SMS / email" if account["factors"] else "No 2FA"

    counts = Counter(bucket(account) for account in accounts)
    return [
        ("Passkey / hardware", counts["Passkey / hardware"], ACCENT),
        ("TOTP / push", counts["TOTP / push"], colors.HexColor("#3a9fd6")),
        ("SMS / email", counts["SMS / email"], SEVERITY["medium"]),
        ("No 2FA", counts["No 2FA"], SEVERITY["critical"]),
        ("Not recorded", counts["Not recorded"], SEVERITY["low"]),
    ]


def _when(value) -> str:
    return value.strftime("%d %b %Y") if value else ""


def _logo(canvas, x: float, y: float, size: float) -> None:
    """The app's shield-and-check, drawn as vectors from the same shape as its icon (24-unit box)."""
    unit = size / 24
    point = lambda px, py: (x + px * unit, y + (24 - py) * unit)  # noqa: E731  Icon coordinates run downward.
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#0b111c"))
    canvas.roundRect(x, y, size, size, 5 * unit, stroke=0, fill=1)
    shield = canvas.beginPath()
    shield.moveTo(*point(12, 2.2))
    shield.curveTo(*point(14, 4), *point(16.8, 5.1), *point(19.2, 5.1))
    shield.lineTo(*point(20, 5.9))
    shield.lineTo(*point(20, 13))
    shield.curveTo(*point(20, 17.6), *point(16.8, 20.4), *point(12, 22))
    shield.curveTo(*point(7.2, 20.4), *point(4, 17.6), *point(4, 13))
    shield.lineTo(*point(4, 5.9))
    shield.lineTo(*point(4.8, 5.1))
    shield.curveTo(*point(7.2, 5.1), *point(10, 4), *point(12, 2.2))
    shield.close()
    canvas.setFillColor(ACCENT_BRIGHT)
    canvas.drawPath(shield, stroke=0, fill=1)
    check = canvas.beginPath()
    check.moveTo(*point(8.6, 12.4))
    check.lineTo(*point(11, 14.8))
    check.lineTo(*point(15.6, 10.2))
    canvas.setStrokeColor(colors.HexColor("#0b111c"))
    canvas.setLineWidth(2.1 * unit)
    canvas.setLineCap(1)
    canvas.setLineJoin(1)
    canvas.drawPath(check, stroke=1, fill=0)
    canvas.restoreState()


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, 14 * mm, PAGE_W - MARGIN, 14 * mm)
    _logo(canvas, MARGIN, 8.6 * mm, 3.6 * mm)
    canvas.setFont(BOLD, 7.5)
    canvas.setFillColor(INK)
    canvas.drawString(MARGIN + 5 * mm, 9.6 * mm, "Security Modeler")
    canvas.setFont(REGULAR, 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN + 27 * mm, 9.6 * mm, "made by Akulav  ·  Confidential: this maps how your accounts can be attacked.")
    canvas.drawRightString(PAGE_W - MARGIN, 9.6 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _cover_page(summary: dict, posture: int, generated: datetime):
    def draw(canvas, _doc) -> None:
        canvas.saveState()
        canvas.setFillColor(COVER)
        canvas.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
        _logo(canvas, MARGIN, PAGE_H - 34 * mm, 12 * mm)
        canvas.setFillColor(COVER_TEXT)
        canvas.setFont(BOLD, 13)
        canvas.drawString(MARGIN + 16 * mm, PAGE_H - 26.5 * mm, "Security Modeler")
        canvas.setFillColor(COVER_MUTED)
        canvas.setFont(REGULAR, 9)
        canvas.drawString(MARGIN + 16 * mm, PAGE_H - 32 * mm, "made by Akulav")
        canvas.setFillColor(ACCENT)
        canvas.rect(MARGIN, PAGE_H - 45 * mm, 14 * mm, 1.2 * mm, stroke=0, fill=1)
        canvas.setFillColor(COVER_TEXT)
        canvas.setFont(BOLD, 31)
        canvas.drawString(MARGIN, PAGE_H - 62 * mm, "Personal Security")
        canvas.drawString(MARGIN, PAGE_H - 75 * mm, "Report")
        canvas.setFillColor(COVER_MUTED)
        canvas.setFont(REGULAR, 11)
        canvas.drawString(MARGIN, PAGE_H - 86 * mm, generated.strftime("%d %B %Y"))

        gauge = _gauge(posture, 180)
        gauge.drawOn(canvas, (PAGE_W - 180) / 2, PAGE_H - 180 * mm)
        canvas.setFillColor(COVER_TEXT)
        canvas.setFont(BOLD, 12)
        canvas.drawCentredString(PAGE_W / 2, PAGE_H - 190 * mm, "Account protection score")
        canvas.setFillColor(COVER_MUTED)
        canvas.setFont(REGULAR, 9)
        canvas.drawCentredString(PAGE_W / 2, PAGE_H - 197 * mm, "Based on what's recorded in your map, with important accounts counting more")

        cells = [(summary["nodes"], "Nodes mapped"), (summary["edges"], "Relationships"),
                 (summary["critical"], "Critical findings"), (summary["high"], "High findings")]
        step = (PAGE_W - 2 * MARGIN) / len(cells)
        for index, (value, label) in enumerate(cells):
            x = MARGIN + step * (index + 0.5)
            canvas.setFillColor(COVER_TEXT)
            canvas.setFont(BOLD, 21)
            canvas.drawCentredString(x, 52 * mm, str(value))
            canvas.setFillColor(COVER_MUTED)
            canvas.setFont(REGULAR, 8.5)
            canvas.drawCentredString(x, 46 * mm, label)
        canvas.setFont(REGULAR, 8)
        canvas.drawCentredString(PAGE_W / 2, 20 * mm, "Confidential. Contains a map of your accounts and how they could be attacked. Store it safely.")
        canvas.setFillColor(ACCENT)
        canvas.drawCentredString(PAGE_W / 2, 14 * mm, "Security Modeler  ·  made by Akulav  ·  github.com/Akulav/ai-security-modeler")
        canvas.restoreState()

    return draw


def build_report(
    nodes: list[dict], edges: list[dict], narrative: dict | None = None, narrative_date=None,
    narrative_model: str | None = None, answers: list[dict] | None = None, generated: datetime | None = None,
) -> bytes:
    generated = generated or datetime.now()
    analysis = analyze(nodes, edges)
    findings = analysis["findings"]
    model = build_model(nodes, edges)
    accounts = account_rows(model)
    posture = _posture(accounts)
    answers = answers or []

    story: list = [NextPageTemplate("content"), PageBreak()]

    story.append(_paragraph("Summary", "h1"))
    if narrative and narrative.get("summary"):
        story += _rich(narrative["summary"])
        story.append(_paragraph(
            f"AI summary from {_when(narrative_date)}" + (f", written by {narrative_model}" if narrative_model else "")
            + ". It may predate recent changes to your map, and AI text can contain mistakes.", "muted",
        ))
    else:
        story.append(_paragraph(
            "No AI analysis has been run yet, so this report contains calculated results only. "
            "Run the analysis in the app to add AI commentary."))
    story.append(Spacer(1, 4 * mm))
    story.append(_stats([
        (posture, "Protection score"), (len(accounts), "Accounts"),
        (sum(1 for a in accounts if a["recorded"] and not a["factors"] and not a["passkey"]), "Known without 2FA"),
        (sum(1 for a in accounts if a["breaches"]), "With recorded breaches"),
    ]))

    severity_counts = Counter(f["severity"] for f in findings)
    charts = Table(
        [[_paragraph("Findings by severity", "h2"), _paragraph("How accounts are protected", "h2")],
         [_bars([(level.capitalize(), severity_counts[level], SEVERITY[level]) for level in SEVERITY_ORDER], WIDTH / 2 - 8),
          _bars(_strength_buckets(accounts), WIDTH / 2 - 8)]],
        colWidths=[WIDTH / 2, WIDTH / 2],
    )
    charts.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [Spacer(1, 2 * mm), charts]

    story.append(_paragraph("Fix these first", "h2"))
    for finding in findings[:5]:
        story += [_card(finding["severity"], finding["title"], finding["detail"]), Spacer(1, 1.5 * mm)]

    story.append(PageBreak())
    story.append(_paragraph("Calculated findings", "h1"))
    story.append(_paragraph("These come directly from your map, so they're exact for what you've entered.", "muted"))
    for key, title in SECTIONS:
        items = [f for f in findings if f["section"] == key]
        if not items:
            continue
        story += [CondPageBreak(35 * mm), _paragraph(f"{title} ({len(items)})", "h2")]
        for item in items:
            story.append(KeepTogether([_card(item["severity"], item["title"], item["detail"]), Spacer(1, 1.5 * mm)]))

    if narrative and any(narrative.get(key) for key, _ in SECTIONS):
        story.append(PageBreak())
        story.append(_paragraph("AI assessment", "h1"))
        story.append(_paragraph(
            f"Written by the local AI model on {_when(narrative_date)}. Check these before acting on them, "
            "because AI text can contain mistakes.", "muted"))
        for key, title in SECTIONS:
            items = narrative.get(key) or []
            if not items:
                continue
            story += [CondPageBreak(35 * mm), _paragraph(title, "h2")]
            for item in items:
                story.append(KeepTogether([_card(item.get("severity", "medium"), item.get("title", ""), item.get("detail", "")), Spacer(1, 1.5 * mm)]))

    if answers:
        story.append(PageBreak())
        story.append(_paragraph("Questions answered by the AI", "h1"))
        story.append(_paragraph("The latest answer to each question you asked. Check these before acting on them.", "muted"))
        for answer in answers:
            story.append(CondPageBreak(40 * mm))
            story.append(_paragraph(answer["question"], "h2"))
            story.append(_paragraph(f"Answered {_when(answer.get('created_at'))}", "muted"))
            story.append(Spacer(1, 1.5 * mm))
            story += _rich(answer["answer"])

    if accounts:
        story.append(PageBreak())
        story.append(_paragraph("Every account", "h1"))
        story.append(_paragraph(
            "Weakest first. The score reflects what's recorded: the password type and the strongest second factor, "
            "with penalties for breaches and legacy status. “Not recorded” means unknown, not unprotected.", "muted"))
        story.append(Spacer(1, 2 * mm))
        rows = [_header_row("Account", "Score", "Importance", "Password", "Second factors")]
        styles = []
        for index, account in enumerate(accounts, start=1):
            score = account["score"] if account["recorded"] else "–"
            factors = "Passkey, " * account["passkey"] + account["factor_labels"]
            if not account["recorded"]:
                factors = "Not recorded"
            elif account["passkey"] and not account["factors"]:
                factors = "Passkey"
            name = account["name"] + (" (legacy)" if account["status"] == "legacy" else "")
            rows.append([
                _paragraph(name, "cell"), _paragraph(score, "cell"), _paragraph(account["level"], "cell"),
                _paragraph(PASSWORD_TYPES.get(account["password_type"], account["password_type"]), "cell"), _paragraph(factors, "cell"),
            ])
            if account["recorded"]:
                styles.append(("LINEBEFORE", (1, index), (1, index), 2.2, _score_color(account["score"])))
        table = _table(rows, [50 * mm, 13 * mm, 19 * mm, 37 * mm, WIDTH - 119 * mm])
        table.setStyle(TableStyle(styles))
        story.append(table)

    devices = [n for n in model.nodes.values() if n["type"] in COMPUTERS]
    gear = [n for n in model.nodes.values() if n["type"] in NETWORK_GEAR]
    if devices or gear:
        story.append(PageBreak())
        story.append(_paragraph("Devices and network", "h1"))
    if devices:
        rows = [_header_row("Device", "OS", "Encryption", "Lock", "Defenses")]
        for node in devices:
            os_name = f"{OPERATING_SYSTEMS.get(node.get('os'), 'Not set')} {node.get('os_version') or ''}".strip()
            rows.append([
                _paragraph(node["name"], "cell"), _paragraph(os_name, "cell"), _paragraph(node.get("encryption", "unknown"), "cell"),
                _paragraph(PASSWORD_TYPES.get(node["password_type"], node["password_type"]), "cell"),
                _paragraph(", ".join(DEFENSES.get(d, d) for d in node.get("defenses") or []) or "None recorded", "cell"),
            ])
        story.append(_table(rows, [36 * mm, 30 * mm, 21 * mm, 28 * mm, WIDTH - 115 * mm]))
    if gear:
        story.append(_paragraph("Network gear", "h2"))
        rows = [_header_row("Gear", "Admin password", "Defenses")]
        for node in gear:
            rows.append([
                _paragraph(node["name"], "cell"), _paragraph(PASSWORD_TYPES.get(node["password_type"], node["password_type"]), "cell"),
                _paragraph(", ".join(DEFENSES.get(d, d) for d in node.get("defenses") or []) or "None recorded", "cell"),
            ])
        story.append(_table(rows, [45 * mm, 38 * mm, WIDTH - 83 * mm]))

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title="Personal Security Report", author="Security Modeler", creator="Security Modeler, made by Akulav",
                            leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=18 * mm)
    content = Frame(MARGIN, 18 * mm, WIDTH, PAGE_H - MARGIN - 18 * mm, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[content], onPage=_cover_page(analysis["summary"], posture, generated)),
        PageTemplate(id="content", frames=[content], onPage=_footer),
    ])
    doc.build(story)
    return buffer.getvalue()
