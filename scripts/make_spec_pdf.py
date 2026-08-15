"""화면기획서 Markdown -> PDF 변환.

S1의 입력이 되는 '텍스트 레이어를 가진 PDF'를 만든다. 실무 기획서처럼 표를
실제 PDF 표(선과 셀을 가진 구조)로 렌더링하는 것이 중요하다. pdfplumber의
extract_tables()가 이 구조를 읽어야 하기 때문이다. 텍스트를 단순히 흘려 쓰면
표 추출 경로를 검증할 수 없다.

사용법:
    uv run python scripts/make_spec_pdf.py                    # 전체 변환
    uv run python scripts/make_spec_pdf.py fixtures/specs/login_spec.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

FONT_DIR = Path("C:/Windows/Fonts")
BODY_FONT = "Malgun"
BOLD_FONT = "MalgunBold"


def register_fonts() -> None:
    """한글 폰트 등록. 없으면 즉시 실패시킨다 — 조용히 깨진 PDF를 만들면 안 된다."""
    regular, bold = FONT_DIR / "malgun.ttf", FONT_DIR / "malgunbd.ttf"
    if not regular.exists():
        raise SystemExit(f"한글 폰트를 찾을 수 없습니다: {regular}")
    pdfmetrics.registerFont(TTFont(BODY_FONT, str(regular)))
    pdfmetrics.registerFont(TTFont(BOLD_FONT, str(bold if bold.exists() else regular)))
    pdfmetrics.registerFontFamily(BODY_FONT, normal=BODY_FONT, bold=BOLD_FONT)


def build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName=BOLD_FONT,
                             fontSize=18, leading=24, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName=BOLD_FONT,
                             fontSize=14, leading=19, spaceBefore=12, spaceAfter=6),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontName=BOLD_FONT,
                             fontSize=12, leading=16, spaceBefore=8, spaceAfter=4),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName=BODY_FONT,
                               fontSize=10, leading=15, alignment=TA_LEFT),
        "bullet": ParagraphStyle("bullet", fontName=BODY_FONT, fontSize=10,
                                 leading=15, leftIndent=12, spaceAfter=2),
        "cell": ParagraphStyle("cell", fontName=BODY_FONT, fontSize=9, leading=13),
        "cellhead": ParagraphStyle("cellhead", fontName=BOLD_FONT, fontSize=9, leading=13),
    }


def inline_markup(text: str) -> str:
    """**bold** -> <b>bold</b>, `code` -> <font face=Courier>. reportlab 마크업으로."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`(.+?)`", r"<font name='Courier'>\1</font>", text)
    return text


def is_table_row(line: str) -> bool:
    return line.startswith("|") and line.endswith("|")


def is_table_divider(line: str) -> bool:
    return bool(re.fullmatch(r"\|[\s:|-]+\|", line))


def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def make_table(rows: list[list[str]], styles: dict, avail_width: float) -> Table:
    """첫 행을 헤더로 렌더링. 셀은 Paragraph로 감싸 한글 줄바꿈이 되게 한다."""
    ncols = max(len(r) for r in rows)
    data = []
    for i, row in enumerate(rows):
        padded = row + [""] * (ncols - len(row))
        style = styles["cellhead"] if i == 0 else styles["cell"]
        data.append([Paragraph(inline_markup(c), style) for c in padded])

    table = Table(data, colWidths=[avail_width / ncols] * ncols, repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#888888")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EAF0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def md_to_flowables(md: str, styles: dict, avail_width: float) -> list:
    flow: list = []
    lines = md.splitlines()
    i = 0
    bullets: list[str] = []

    def flush_bullets() -> None:
        """불릿을 본문 폰트로 직접 찍는다.

        reportlab 의 ListFlowable 은 불릿 글리프를 기본 폰트(Helvetica)로 그리려
        하는데, 그 폰트에 U+2022 가 없으면 PDF 에 (cid:127) 같은 깨진 글리프가
        남는다. 그러면 pdfplumber 추출 텍스트에 그 문자열이 그대로 섞여 LLM
        프롬프트를 오염시킨다. 접두어로 찍으면 본문 한글 폰트가 쓰인다.
        """
        nonlocal bullets
        if bullets:
            for b in bullets:
                flow.append(Paragraph("• " + inline_markup(b), styles["bullet"]))
            flow.append(Spacer(1, 4))
            bullets = []

    while i < len(lines):
        line = lines[i].rstrip()

        if is_table_row(line):
            flush_bullets()
            rows = []
            while i < len(lines) and is_table_row(lines[i].rstrip()):
                if not is_table_divider(lines[i].rstrip()):
                    rows.append(split_row(lines[i].rstrip()))
                i += 1
            if rows:
                flow.append(Spacer(1, 4))
                flow.append(make_table(rows, styles, avail_width))
                flow.append(Spacer(1, 8))
            continue

        if line.startswith("### "):
            flush_bullets(); flow.append(Paragraph(inline_markup(line[4:]), styles["h3"]))
        elif line.startswith("## "):
            flush_bullets(); flow.append(Paragraph(inline_markup(line[3:]), styles["h2"]))
        elif line.startswith("# "):
            flush_bullets(); flow.append(Paragraph(inline_markup(line[2:]), styles["h1"]))
        elif line.startswith("- "):
            bullets.append(line[2:])
        elif line == "":
            flush_bullets()
        else:
            flush_bullets(); flow.append(Paragraph(inline_markup(line), styles["body"]))
        i += 1

    flush_bullets()
    return flow


def convert(md_path: Path) -> Path:
    pdf_path = md_path.with_suffix(".pdf")
    styles = build_styles()
    margin = 20 * mm
    avail = A4[0] - 2 * margin

    doc = SimpleDocTemplate(
        str(pdf_path), pagesize=A4,
        leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin,
        title=md_path.stem, author="기획팀",
    )
    doc.build(md_to_flowables(md_path.read_text(encoding="utf-8"), styles, avail))
    return pdf_path


def main() -> None:
    register_fonts()
    targets = ([Path(a) for a in sys.argv[1:]]
               or sorted(Path("fixtures/specs").glob("*.md")))
    if not targets:
        raise SystemExit("변환할 .md 파일이 없습니다.")
    for md in targets:
        out = convert(md)
        print(f"  {md} -> {out}  ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
