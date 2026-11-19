"""기획서 시안과 실제 화면을 나란히 (2026-11-19).

리포트는 이름·문구·동작만 대조하고 디자인(색·배치)은 대조하지 않는다. GPU 없이 시안과 화면을
자동 판정하는 것은 믿을 만하지 않다. 대신 화면기획서(쪽마다 '페이지명' 머리말 · 왼쪽 시안 ·
오른쪽 '화면상세설명')에서 그 화면의 시안을 잘라 실제 스크린샷 옆에 둔다 — 대조는 사람이 한다.
"""

from __future__ import annotations

import pytest
from PIL import Image

from prova.models import StepResult, TestReport, Verdict
from prova.s6_report.report_builder import save_html
from prova.s6_report.spec_figures import build_spec_figures

_PAGE = """<section style="width:1000px;height:1100px;position:relative;page-break-after:always">
<table style="border-collapse:collapse;width:1000px;font-size:14px" border="1">
<tr><td>프로젝트</td><td>시험 홈페이지</td><td>작성자</td><td>홍길동</td></tr>
<tr><td>페이지명</td><td>{name}</td><td>페이지</td><td>사용자</td></tr></table>
<div style="position:absolute;left:0;top:80px;width:700px;height:1000px;background:{color}"></div>
<div style="position:absolute;left:720px;top:80px;font-size:16px">화면상세설명</div></section>"""


@pytest.fixture(scope="module")
def spec_pdf(tmp_path_factory):
    from playwright.sync_api import sync_playwright

    path = tmp_path_factory.mktemp("spec") / "spec.pdf"
    html = "<html><body style='margin:0'>" + "".join(
        _PAGE.format(name=n, color=c) for n, c in
        [("메인화면", "#c00000"), ("CONTACT", "#0000c0"), ("CONTACT", "#00c000")]) + "</body></html>"
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.set_content(html)
        pg.pdf(path=str(path), width="1000px", height="1100px", print_background=True)
        b.close()
    return path


def _report(spec, cases) -> TestReport:
    return TestReport(run_id="ui-20261119-000000", target_url="https://example.test",
                      spec_source=str(spec),
                      summary={**TestReport.summarize(cases),
                               "screen_names": {"main": "메인화면", "contact": "CONTACT",
                                                "about": "회사소개"}},
                      cases=cases, created_at="2026-11-19T10:00:00")


def _case(sid, shot=True) -> Verdict:
    return Verdict(case_id=f"{sid}-labels-001", title="라벨", screen_id=sid, verdict="PASS",
                   step_results=[StepResult(seq=1, action="navigate", target="/",
                                            screenshot=f"{sid}-labels-001/step1.png" if shot else None)])


def _main_color(path) -> tuple[int, int, int]:
    im = Image.open(path).convert("RGB")
    return im.getpixel((im.width // 2, im.height // 2))


def test_화면마다_그_쪽의_시안을_첫_화면_비율로_자른다(spec_pdf, tmp_path):
    figs = build_spec_figures(_report(spec_pdf, [_case("main"), _case("contact")]), tmp_path)
    assert set(figs) == {"main", "contact"}
    crop, full = figs["main"]
    im = Image.open(tmp_path / crop)
    assert abs(im.width / im.height - 1280 / 800) < 0.05
    r, g, b = _main_color(tmp_path / crop)
    assert r > 150 and g < 90 and b < 90  # 메인화면 쪽(빨강)의 시안 — 설명 칸·머리말이 아니다
    # 같은 이름의 쪽이 둘이면 첫 쪽(파랑)
    r, g, b = _main_color(tmp_path / figs["contact"][0])
    assert b > 150 and r < 90
    assert Image.open(tmp_path / full).height > im.height  # 전체 시안은 따로


def test_기획서가_없거나_머리말이_없으면_조용히_비운다(tmp_path):
    assert build_spec_figures(_report(tmp_path / "없음.pdf", [_case("main")]), tmp_path) == {}


def test_리포트에_시안과_실제_화면을_나란히_둔다(spec_pdf, tmp_path):
    report = _report(spec_pdf, [_case("main"), _case("contact")])
    html = save_html(report, tmp_path).read_text(encoding="utf-8")
    assert "기획서 시안과 실제 화면 (2)" in html
    assert "src='메인화면" not in html  # 파일 이름은 화면 ID 로
    assert "spec_figures/main.jpg" in html and "main-labels-001/step1.png" in html


def test_시안이_없으면_그_절이_없다(tmp_path):
    html = save_html(_report(tmp_path / "없음.pdf", [_case("main")]), tmp_path).read_text(encoding="utf-8")
    assert "<h2>기획서 시안과 실제 화면" not in html
