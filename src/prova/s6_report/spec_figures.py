"""기획서 시안을 화면별로 잘라 둔다 — 리포트가 실제 화면 옆에 놓는다 (2026-11-19).

## 왜 판정하지 않고 나란히 두기만 하는가

기획서에는 색·글꼴·크기 같은 디자인 수치가 없고(실물 화면기획서 31쪽에 0건), 디자인 정보는
시안 그림에만 있다. 시안과 실제 화면을 GPU 없이 자동으로 '같다/다르다' 판정하는 것은 믿을 만하지
않다 — 시안은 자리표시 그림·회색 상자로 그려지고, 실제 화면은 진짜 사진과 글이 들어간다.
틀린 판정을 내는 것보다 사람이 대조하기 좋게 나란히 놓는 것이 정직하다.

## 무엇을 자르는가

화면기획서(Figma 출력)는 쪽마다 위에 '프로젝트 · 페이지명' 머리말 표, 왼쪽에 화면 시안, 오른쪽에
'화면상세설명' 칸이 있다. 머리말 아래 · 설명 칸 왼쪽을 시안으로 본다. 실제 스크린샷은 첫 화면
(1280×800)만 찍으므로 시안도 같은 비율로 첫 화면 부분을 자르고, 전체는 따로 둔다.

화면은 머리말의 페이지명으로 찾는다 — 기획서를 화면으로 나눌 때(split_screens)와 같은 이름이라
AI 없이 짝이 맞는다. 같은 페이지명이 여러 쪽이면 첫 쪽(화면의 기본 모습)을 쓴다.

이 단계가 실패해도 보고서는 나와야 한다 — 실패하면 빈 결과를 돌려준다.
"""

from __future__ import annotations

import re
from pathlib import Path

from prova.models import TestReport

FIG_DIR = "spec_figures"
_VIEW_RATIO = 800 / 1280  # 실행 화면 크기(execution.viewport)의 세로/가로
_TARGET_W = 1000  # 잘라 낸 시안의 가로 픽셀


def _norm(name: str) -> str:
    return "".join(str(name).split())


def _header(page) -> tuple[str | None, float]:
    """그 쪽 머리말 표의 페이지명과 머리말의 아래 끝."""
    from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage, _extract_tables

    band = page.crop((0, 0, page.width, min(page.height, max(120.0, page.height * 0.12))))
    names = ParsedDocument._page_names(
        ParsedPage(page_no=page.page_number, tables=_extract_tables(band)))
    if not names:
        return None, 0.0
    # 페이지명이 든 줄의 아래 끝을 본다 — 시안의 틀 선이 머리말 표에 칸으로 붙어 표 전체는
    # 띠 끝까지 늘어난다(실물 메인화면 쪽: 표 310pt, 페이지명 줄 ~60pt). 표 끝을 쓰면 시안
    # 윗부분(로고·메뉴 줄)이 잘려 나갔다.
    bottom = 0.0
    for table in band.find_tables():
        for row, cells in zip(table.rows, table.extract()):
            if any(str(c or "").strip().startswith("페이지명") for c in cells):
                bottom = max(bottom, row.bbox[3])
    return names[0], bottom


def _panel_left(page) -> float:
    """오른쪽 '화면상세설명' 칸의 왼쪽 끝 — 그 왼쪽이 시안이다. 칸이 없으면 쪽 전체.

    칸의 테두리 상자(쪽 오른쪽의 세로로 긴 사각형)가 가장 정확하다. 칸 뒤의 배경 그림은 시안
    오른쪽 끝(햄버거 메뉴 아이콘)보다 왼쪽에서 시작해서 그걸 쓰면 아이콘이 잘렸다. 상자가 없는
    쪽은 제목 글자 '화면상세설명' 의 왼쪽(실물: 상자보다 50pt 안쪽)으로 어림한다.
    """
    boxes = [r["x0"] for r in page.rects
             if r["x0"] > page.width * 0.55 and r["bottom"] - r["top"] > page.height * 0.3]
    if boxes:
        return min(boxes)
    hits = page.search("화면상세설명")
    if hits:
        return max(min(h["x0"] for h in hits) - 50, page.width * 0.3)
    return float(page.width)


def _first_pages(pdf_path: Path) -> dict[str, tuple[int, float, float]]:
    """페이지명(공백 없이) → (쪽 번호 0부터, 시안 위 끝, 시안 오른쪽 끝)."""
    import pdfplumber

    found: dict[str, tuple[int, float, float]] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            name, top = _header(page)
            if name and _norm(name) not in found:
                found[_norm(name)] = (i, top, _panel_left(page))
    return found


def build_spec_figures(report: TestReport, run_dir: Path) -> dict[str, tuple[str, str]]:
    """기획서 화면마다 시안을 잘라 run_dir/spec_figures 에 둔다.

    Returns:
        {screen_id: (첫 화면 부분 경로, 전체 경로)} — run_dir 기준 상대 경로. 기획서가 없거나
        화면기획서 모양이 아니면 빈 dict.
    """
    try:
        src = Path(str(report.spec_source or ""))
        if src.suffix.lower() != ".pdf" or not src.exists():
            return {}
        names = (report.summary or {}).get("screen_names") or {}
        # 보지 않은 화면도 자른다 — 화면별 확인 범위가 실제 화면 대신 시안을 보인다.
        checked = list(dict.fromkeys([v.screen_id for v in report.cases if v.screen_id] + list(names)))
        pages = _first_pages(src)
        wanted = {sid: pages[_norm(names.get(sid) or sid)] for sid in checked
                  if _norm(names.get(sid) or sid) in pages}
        if not wanted:
            return {}

        import pypdfium2 as pdfium

        out_dir = Path(run_dir) / FIG_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        figures: dict[str, tuple[str, str]] = {}
        pdf = pdfium.PdfDocument(str(src))
        try:
            for sid, (index, top, right) in wanted.items():
                scale = _TARGET_W / right
                image = pdf[index].render(scale=scale).to_pil().convert("RGB")
                y, w = int(top * scale), int(right * scale)
                stem = re.sub(r"[^\w-]", "_", sid)
                image.crop((0, y, w, min(image.height, y + int(w * _VIEW_RATIO)))).save(
                    out_dir / f"{stem}.jpg", quality=85)
                image.crop((0, y, w, image.height)).save(out_dir / f"{stem}_full.jpg", quality=85)
                figures[sid] = (f"{FIG_DIR}/{stem}.jpg", f"{FIG_DIR}/{stem}_full.jpg")
        finally:
            pdf.close()
        return figures
    except Exception:
        return {}
