"""리포트(HTML)를 PDF 로 내보낸다 (2026-11-19).

리포트(report.html)를 파일 하나로 넘길 때 쓴다.
HTML 은 스크린샷을 상대 경로로 참조해서 폴더째 보내야 하지만 PDF 는 한 파일이다.

이미 의존성인 Playwright(Chromium)로 찍는다. 실행이 끝날 때 만들지 않고 받을 때 만든다 —
매 실행에 수 초가 붙는 것을 피한다.
"""

from __future__ import annotations

from pathlib import Path

# 찍기 전에 펼친다 — 접힌 카드, 넘겨 보는 장, 늦게 불러오는 그림. 종이는 늘 밝은 화면이다.
# 통과 케이스는 펼치지 않는다 — 한 줄씩 목록으로 남는다. 열세 건을 다 펼치면 같은 여덟 단계와 캡처
# 여덟 장이 열세 번 찍혀 32쪽 가운데 23쪽이 통과였다(2026-11-25). 통과의 근거는 HTML·엑셀에 그대로 있다.
_PREPARE_JS = """async () => {
  document.documentElement.setAttribute('data-theme', 'light');
  document.documentElement.classList.remove('embedded');
  document.querySelectorAll('details').forEach(d => { d.open = true; });
  document.querySelectorAll('.passfold details.case').forEach(d => { d.open = false; });
  // 긴 단계의 접어 둔 앞 회차는 종이에서도 접힌 한 줄로 — 멈춘 회차만 펼쳐 둔다.
  document.querySelectorAll('.tr-grp > details').forEach(d => { d.open = false; });
  document.querySelectorAll('section.pg').forEach(p => { p.hidden = false; });
  const imgs = [...document.querySelectorAll('img')];
  imgs.forEach(i => { i.loading = 'eager'; });
  await Promise.all(imgs.map(i => i.complete ? null : new Promise(r => {
    i.addEventListener('load', r); i.addEventListener('error', r);
  })));
  await document.fonts.ready;  // 리포트 글꼴(fonts/PretendardVariable.woff2)이 다 읽힌 뒤 찍는다
}"""

# 화면용 꾸밈(넘기는 줄, 버튼)은 종이에 찍지 않는다. 장이 바뀌면 쪽을 넘긴다.
# 실패 카드는 한 쪽보다 길 때가 많다 — 카드째 '끊지 않기' 를 걸면 카드가 통째로 다음 쪽으로 넘어가
# 1쪽이 제목 한 줄만 남고 비었다. 카드 안의 덩어리(기대·실제 상자, 근거 표, 판정한 화면, 표의 줄)만
# 끊지 않고, 제목은 다음 덩어리와 떨어지지 않게 한다.
_PDF_CSS = """
.pgnav, .actions, button.copy, button.theme { display:none !important; }
.pg + .pg { break-before:page; }
.topbar { position:static !important; background:none !important; -webkit-backdrop-filter:none !important;
          backdrop-filter:none !important; }
h2, h3.grp, .case > summary, details.raw > summary, h4 { break-after:avoid; }
/* 실패 카드는 대개 한 쪽에 들어간다(아래 scale) — 들어가면 통째로 다음 쪽에서 시작한다. 한 쪽보다 길면
   브라우저가 카드 안 덩어리 경계에서 나눈다. */
.case.failed { break-inside:avoid; }
.chart, .warn, .heal, .gap, .cmp > div > p, table.src, .repro li, .trace, .shots.last, .shots a,
.steps tr, .stuck .fwhy, .fm-node, ul.brief li, .case:not([open]) { break-inside:avoid; }
/* 판정한 화면은 칸 폭에 맞춰 크게 — 종이에서는 누르면 크게 보기가 없다 */
.shots.last a > img { max-height:320px !important; }
/* 단계별 캡처 여덟 장은 거의 같은 그림이고 종이에서는 작아 읽히지 않는다 — 판정한 화면 한 장만 크게 두고
   나머지는 HTML 리포트에서 본다. '자료' 칸(화면 구조 파일 링크)도 종이에서 열 수 없어 뺀다. 이렇게 하면
   실패 카드 하나가 한 쪽에 들어간다. */
details.raw > .shots { display:none; }
details.raw > summary::after { content:" — 단계별 캡처는 HTML 리포트에서 봅니다"; }
.steps th:last-child, .steps td:last-child { display:none; }
/* 복사 버튼이 빠진 자리에 꼬리표가 올라와 제목 옆에서 좁게 꺾인다 — 대제목이 한 줄을 다 쓴다. */
.case .head { flex-basis:100% !important; }
"""

# 쪽 꼬리말 — 넘겨받은 사람이 낱장으로 뽑아도 어느 실행의 몇 쪽인지 안다. 꼬리말은 문서 밖에서
# 따로 그려져 문서의 CSS 변수를 읽지 못한다 — 색은 theme.light_value 로 토큰에서 가져온다.
def _footer(title: str) -> str:
    from html import escape

    from prova.theme import light_value

    return (
        f"<div style=\"width:100%;padding:0 10mm;display:flex;justify-content:space-between;"
        f"font-family:'Pretendard Variable',Pretendard,-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;font-size:8px;"
        f"color:{light_value('--fg-muted')}\"><span>{escape(title)}</span>"
        "<span><span class='pageNumber'></span> / <span class='totalPages'></span></span></div>")


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
            title = page.title().replace("Prova 검증 리포트 · ", "Prova 검증 리포트 · 실행 ")
            # scale 0.8 — 종이 폭(190mm ≈ 718px)에 화면처럼 두 칸(기획서 · 실제 화면)이 들어가게 약 900px 로
            # 배치한다. 본문 14px 가 종이에서 약 8.4pt 다.
            page.pdf(path=str(pdf_path), format="A4", print_background=True, scale=0.8,
                     display_header_footer=True, header_template="<span></span>",
                     footer_template=_footer(title),
                     margin={"top": "12mm", "bottom": "14mm", "left": "10mm", "right": "10mm"})
        finally:
            browser.close()
    return pdf_path
