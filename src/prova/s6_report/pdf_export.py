"""리포트(HTML)를 PDF 로 내보낸다 (2026-11-19).

기획자용 보고서(planner.html)와 고치는 사람용 리포트(report.html)를 파일 하나로 넘길 때 쓴다.
HTML 은 스크린샷을 상대 경로로 참조해서 폴더째 보내야 하지만 PDF 는 한 파일이다.

이미 의존성인 Playwright(Chromium)로 찍는다. 실행이 끝날 때 만들지 않고 받을 때 만든다 —
매 실행에 수 초가 붙는 것을 피한다.
"""

from __future__ import annotations

from pathlib import Path

# 찍기 전에 펼친다 — 접힌 카드, 넘겨 보는 장, 늦게 불러오는 그림. 종이는 늘 밝은 화면이다.
_PREPARE_JS = """async () => {
  document.documentElement.setAttribute('data-theme', 'light');
  document.documentElement.classList.remove('embedded');
  document.querySelectorAll('details').forEach(d => { d.open = true; });
  document.querySelectorAll('section.pg').forEach(p => { p.hidden = false; });
  const imgs = [...document.querySelectorAll('img')];
  imgs.forEach(i => { i.loading = 'eager'; });
  await Promise.all(imgs.map(i => i.complete ? null : new Promise(r => {
    i.addEventListener('load', r); i.addEventListener('error', r);
  })));
}"""

# 화면용 꾸밈(넘기는 줄, 버튼)은 종이에 찍지 않는다. 장이 바뀌면 쪽을 넘긴다.
_PDF_CSS = """
.pgnav, .actions, button.copy, button.theme { display:none !important; }
.pg + .pg { break-before:page; }
.case, .stuck .fwhy, .cmp, .shots a { break-inside:avoid; }
.topbar { position:static !important; }
/* 복사 버튼이 빠진 자리에 꼬리표가 올라와 제목 옆에서 좁게 꺾인다 — 대제목이 한 줄을 다 쓴다. */
.case .head { flex-basis:100% !important; }
"""


def save_pdf(html_path: Path, pdf_path: Path) -> Path:
    """html_path 를 A4 PDF 로 저장한다. 옆 폴더의 스크린샷이 그대로 들어간다."""
    from playwright.sync_api import sync_playwright

    html_path, pdf_path = Path(html_path).resolve(), Path(pdf_path)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1100, "height": 1400}, color_scheme="light")
            page.goto(html_path.as_uri(), wait_until="load")
            page.add_style_tag(content=_PDF_CSS)
            page.evaluate(_PREPARE_JS)
            page.emulate_media(media="print", color_scheme="light")
            page.pdf(path=str(pdf_path), format="A4", print_background=True,
                     margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"})
        finally:
            browser.close()
    return pdf_path
