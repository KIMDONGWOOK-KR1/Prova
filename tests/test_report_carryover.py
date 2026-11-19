"""기획자용 보고서에서 리포트로 옮겨 온 것 (2026-11-19).

기획자용 보고서(planner.html)는 따로 두지 않고 리포트 하나로 간다. 다만 그 보고서에만 있던
네 가지는 실물 기획서 실행(43건: 기획서와 다름 14 · 판정 못 함 19)에서 읽는 양을 크게 줄였다.

- 판정하지 못한 건을 멈춘 이유가 같은 것끼리 묶는다 (19건 중 10건이 한 자리에서 멈췄다).
- 이름 대조는 '몇 개 중 몇 개' 와 못 찾은 이름·찾은 이름으로 나눠 적는다 (14건 전부 이 유형).
- 기획서 화면 중 이번에 보지 않은 화면을 밝힌다 (21개 중 16개만 확인).
- 기획서 시안과 실제 화면을 나란히 둔다 (test_spec_figures.py).
"""

from __future__ import annotations

from prova.models import StepResult, TestReport, Verdict
from prova.s6_report.report_builder import _case_html, _fail_list_html, render_html
from prova.wording import stop_reason


def _labels(screen="contact") -> Verdict:
    return Verdict(
        case_id=f"{screen}-labels-001", title="라벨 요소 존재 검증", screen_id=screen,
        plain="기획서의 항목 이름으로 화면에서 칸을 찾을 수 있다", verdict="FAIL",
        failure_category="assertion_mismatch",
        failure_detail="라벨로 찾을 수 없음 — '내용', '문의 등록': 일치하는 요소가 없음.",
        evidence={"expected": "기획서의 이름으로 화면에서 요소를 찾을 수 있다",
                  "actual": "라벨로 찾을 수 없음 — '내용', '문의 등록': 일치하는 요소가 없음.",
                  "findable": {"성명": "", "내용": "일치하는 요소가 없음",
                               "문의 등록": "일치하는 요소가 없음"}},
        step_results=[StepResult(seq=1, action="navigate", target="/contact",
                                 screenshot=f"{screen}-labels-001/step1.png")])


def _stuck(i: int, target="내용", screen="contact") -> Verdict:
    return Verdict(
        case_id=f"{screen}-req-{i:03}", title=f"필수 {i}", plain=f"항목 {i}을 비워 두면 막힌다",
        screen_id=screen, verdict="FAIL", failure_category="element_not_found",
        failure_detail=f"스텝 3(fill '{target}') 실패: 일치하는 요소가 없음",
        step_results=[
            StepResult(seq=1, action="navigate", target="/contact"),
            StepResult(seq=2, action="fill", target="성명", value="홍길동"),
            StepResult(seq=3, action="fill", target=target, value="x", status="error",
                       error_detail="일치하는 요소가 없음"),
        ])


def _pass(screen="main") -> Verdict:
    return Verdict(case_id=f"{screen}-valid-001", title="열림", plain="화면이 열린다",
                   screen_id=screen, verdict="PASS", evidence={"actual": "확인됨"},
                   step_results=[StepResult(seq=1, action="navigate", target="/",
                                            screenshot=f"{screen}-valid-001/step1.png")])


def _report(cases, **summary) -> TestReport:
    return TestReport(run_id="ui-20261119-000000", target_url="https://example.test",
                      spec_source="spec.pdf", summary={**TestReport.summarize(cases), **summary},
                      cases=cases, created_at="2026-11-19T10:00:00+09:00")


def _numbers(cases) -> dict:
    return {v.case_id: i for i, v in enumerate(cases, 1)}


# ── 멈춘 이유가 같은 것끼리 ────────────────────────────────────────────────

def test_멈춘_이유_문장():
    target, sentence = stop_reason(_stuck(1))
    assert target == "내용"
    assert sentence == "'내용' 칸에 입력하려다 멈췄습니다. 화면에서 그 이름을 찾지 못했습니다."


def test_같은_곳에서_멈춘_건은_한_묶음이다():
    cases = [_stuck(1), _stuck(2), _stuck(3)]
    html = _fail_list_html(cases, {"contact": "CONTACT"}, _numbers(cases))
    assert "같은 이유로 3건" in html
    # 이유는 묶음 머리에 한 번만 적는다.
    assert html.count("칸에 입력하려다 멈췄습니다") == 1
    # 줄마다 확인하려던 것을 적고, 누르면 그 카드로 간다.
    for i in (1, 2, 3):
        assert f"href='#c-contact-req-00{i}'" in html
        assert f"항목 {i}을 비워 두면 막힌다" in html


def test_멈춘_이유가_다르면_따로_둔다():
    cases = [_stuck(1), _stuck(2), _stuck(3, target="연락처")]
    html = _fail_list_html(cases, {"contact": "CONTACT"}, _numbers(cases))
    assert "같은 이유로 2건" in html
    # 혼자인 건은 묶음 머리 없이 한 줄에 이유를 적는다.
    assert "&#x27;연락처&#x27; 칸에 입력하려다 멈췄습니다" in html
    assert "같은 이유로 1건" not in html


def test_화면이_다르면_같은_이유라도_따로_묶는다():
    cases = [_stuck(1), _stuck(2), _stuck(3, screen="about"), _stuck(4, screen="about")]
    html = _fail_list_html(cases, {"contact": "CONTACT", "about": "회사소개"}, _numbers(cases))
    assert html.count("같은 이유로 2건") == 2


def test_못_찾은_이름에서_멈췄으면_그_결함을_가리킨다():
    cases = [_labels(), _stuck(1), _stuck(2)]
    html = _fail_list_html(cases, {"contact": "CONTACT"}, _numbers(cases))
    assert "1번에서 화면에 없던 이름입니다" in html
    assert "같은 차이 때문에 멈춘 것으로 보입니다" in html


# ── 이름 대조 ──────────────────────────────────────────────────────────────

def test_이름_대조는_몇_개_중_몇_개인지와_이름을_나눠_적는다():
    html = _case_html(_labels(), True)
    # 대제목은 수만 — 못 찾은 이름을 전부 이은 긴 사유 문장을 제목으로 쓰지 않는다.
    assert "<span class=head>기획서의 이름 3개 가운데 2개를 화면에서 찾지 못했습니다.</span>" in html
    got = html[html.index("<h4>실제 화면</h4>"):]
    assert "기획서의 이름 3개 가운데 2개를 화면에서 찾지 못했습니다" in got
    assert "<b>찾지 못함</b>" in got and "내용" in got and "문의 등록" in got
    assert "<b>확인됨</b>" in got and "성명" in got
    # 이름마다의 까닭(없음·후보 여럿)은 원래 문장으로 남긴다.
    assert "일치하는 요소가 없음" in got


def test_이름_대조가_아니면_그대로다():
    html = _case_html(_stuck(1), True)
    assert "찾지 못함" not in html and "확인됨" not in html


# ── 화면별 확인 범위 ──────────────────────────────────────────────────────
#
# 보지 않은 화면·확인하지 않은 것·요소를 못 찾은 건·추출 경고가 저마다 상자였고, 줄마다
# [화면 ID] 를 단 긴 목록이었다. 실물 기획서(화면 21개)에서 경고만 150줄이었다. 화면마다 한 줄로
# 모으고, 경고는 접는다.

_NAMES = {"main": "메인화면", "contact": "CONTACT", "about": "회사소개", "history": "연혁"}


def test_보지_않은_화면을_참고에_한_줄로_밝힌다():
    html = render_html(_report(
        [_pass("main")], screen_names=_NAMES,
        spec_warnings=["[history] 화면 경로가 기획서에 없어 실행하지 않습니다 — 모델이 '/x' 를 지었지만 "
                       "쓰지 않습니다. --screen-url 'history=/경로' 로 알려 주면 실행합니다."]))
    row = html[html.index("<b>보지 않은 화면 3개</b>"):]
    row = row[:row.index("</li>")]
    assert "CONTACT" in row and "회사소개" in row and "연혁" in row
    assert "통과한 것이 아닙니다" in row
    # 명령줄 옵션 이름은 기획자가 읽을 말이 아니다.
    assert "--screen-url" not in html


def test_보지_않은_화면이_모두_주소가_없으면_그렇게_말한다():
    html = render_html(_report(
        [_pass("main")], screen_names={"main": "메인화면", "history": "연혁"},
        spec_warnings=["[history] 화면 경로가 기획서에 없어 실행하지 않습니다"]))
    assert "연혁 — 화면 주소가 기획서에 없어 열지 못했습니다" in html


def test_결론_아래_줄은_화면이_많으면_이름을_잇지_않는다():
    html = render_html(_report([_pass("main")], screen_names=_NAMES))
    assert "<div class='cond'>기획서 화면 4개 중 1개 확인" in html
    assert "메인화면 · CONTACT" not in html
    few = render_html(_report([_pass("main")], screen_names={"main": "메인화면"}))
    assert "<div class='cond'>메인화면 화면" in few


def test_실행_문제가_멈춘_이유를_번호와_함께_적는다():
    html = render_html(_report([_labels(), _stuck(1), _stuck(2)], screen_names=_NAMES))
    row = html[html.index("<b>실행 문제 2건이 멈춘 이유</b>"):]
    row = row[:row.index("</li>")]
    assert "2건 — &#x27;내용&#x27; 칸에 입력하려다 멈췄습니다." in row
    assert "<a href='#c-contact-req-001'>2</a>, <a href='#c-contact-req-002'>3</a>" in row


def test_요소를_못_찾은_건의_제목을_늘어놓지_않는다():
    html = render_html(_report([_stuck(1), _stuck(2)], screen_names=_NAMES, not_found_without_vlm=2))
    box = html[html.index("화면 이미지로 찾기를 켜지 않은 실행입니다"):]
    box = box[:box.index("</p>")]  # 상자가 아니라 작은 글씨 문단이다 (2026-11-19)
    assert "항목 1을 비워 두면 막힌다" not in box
    assert "&#x27;멈춘 이유&#x27; 에 번호" in box or "'멈춘 이유' 에 번호" in box


def test_확인하지_않은_것은_화면_이름을_붙여_적는다():
    html = render_html(_report([_pass("contact")], screen_names={"contact": "CONTACT"},
                               coverage_gaps=["[contact] '파일첨부' 의 에러 문구를 확인하는 케이스가 없습니다."]))
    assert "[contact]" not in html
    row = html[html.index("<b>확인하지 않은 것 1건</b>"):]
    assert "CONTACT: &#x27;파일첨부&#x27; 의 에러 문구를" in row[:400]


def test_추출_경고와_모델_메모는_리포트에_싣지_않는다():
    same = "UI 요소 정의 표를 찾지 못했습니다."
    html = render_html(_report(
        [_pass("main")], screen_names=_NAMES,
        spec_warnings=[f"[{sid}] {same}" for sid in _NAMES]
        + ["[contact] '연락처' 은 예시값이 없습니다.", "[contact] 모델 메모: 파일 형식 제한이 없습니다."]))
    assert same not in html and "파일 형식 제한" not in html
    assert "설계 문서 추출 경고" not in html


def test_화면이_하나이고_적을_것이_없으면_절이_없다():
    html = render_html(_report([_pass("main")], screen_names={"main": "메인화면"}))
    assert "확인 범위" not in html.split("<body>")[1]


# ── 기획서 시안과 실제 화면 ────────────────────────────────────────────────

def test_시안이_있으면_실제_화면과_나란히_둔다():
    html = render_html(_report([_pass("main")], screen_names={"main": "메인화면"}),
                       spec_figures={"main": ("spec_figures/main.jpg", "spec_figures/main_full.jpg")})
    assert "기획서 시안과 실제 화면 (1)" in html
    assert "src='spec_figures/main.jpg'" in html and "href='spec_figures/main_full.jpg'" in html
    assert "main-valid-001/step1.png" in html
    assert "자동으로 대조하지 않았습니다" in html


def test_시안이_없으면_그_절이_없다():
    html = render_html(_report([_pass("main")], screen_names={"main": "메인화면"}))
    assert "<h2>기획서 시안과 실제 화면" not in html
