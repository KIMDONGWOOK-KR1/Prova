"""기획자용 보고서(planner.html) — 리포트와 같은 카드, 기획자가 판단하는 데 쓰는 것만 (2026-11-19).

실물 기획서 실행(화면 21개·43건·경고 150줄)에서 리포트가 길고 지저분해져 문서를 둘로 나눴다.
기획자용은 화면 단위로 넘겨 보고, 고치는 사람용(report.html)은 그대로 두고 PDF 로 받는다.

여기서 고정하는 것:
- 팀원 리포트(PR 4)의 실패 카드 요소가 기획자용 카드에 빠짐없이 있다.
- 원인 추적용 자료(실행 조건·추출 경고·단계별 기록)는 기획자용에 없다.
- 재현 절차는 멈춘 단계를 강조하고 그 뒤의 실행하지 못한 단계까지 보인다.
- 화면이 여럿이면 장으로 나뉘고, 하나면 한 장이다.
"""

from __future__ import annotations

import json

from prova.models import (
    Expectation, SpecSource, StepResult, TestCase, TestReport, TestStep, Verdict,
)
from prova.s5_verifier.assertion_engine import pending_steps
from prova.s6_report.planner_view import (
    fill_pending_from_plan, render_planner_html, save_planner_html,
)
from prova.s6_report.report_builder import _repro_html, render_html


def _defect(screen="signup") -> Verdict:
    return Verdict(
        case_id=f"{screen}-rule-001", title="비밀번호 확인 일치 규칙 강제 여부 확인",
        plain="'비밀번호 확인'에 다른 값을 넣으면 막힌다", screen_id=screen, verdict="FAIL",
        failure_category="assertion_mismatch", violates="match", target_element="pw2",
        target_label="비밀번호 확인",
        failure_detail="'비밀번호 확인'에 다른 값을 넣어도 막히지 않습니다. 가입이 됐습니다.",
        evidence={"expected": "오류 문구 '비밀번호가 일치하지 않습니다' 가 화면에 나타난다",
                  "actual": "오류 문구 없이 가입 완료 화면으로 넘어갔습니다",
                  "url": "https://example.test/done"},
        spec_sources=[SpecSource(page=3, quote="비밀번호 확인 | 비밀번호가 일치하지 않습니다",
                                 table=True)],
        elapsed_ms=4321,
        step_results=[
            StepResult(seq=1, action="navigate", target="/signup", screenshot=f"{screen}-rule-001/step1.png"),
            StepResult(seq=2, action="fill", target="비밀번호", value="Signup1!"),
            StepResult(seq=3, action="fill", target="비밀번호 확인", value="Signup1!a"),
            StepResult(seq=4, action="click", target="가입하기", screenshot=f"{screen}-rule-001/step4.png"),
        ])


def _stuck(i: int, screen="contact", pending=True) -> Verdict:
    return Verdict(
        case_id=f"{screen}-req-{i:03}", title=f"필수 {i}", plain=f"항목 {i}을 비워 두면 막힌다",
        screen_id=screen, verdict="FAIL", failure_category="element_not_found",
        failure_detail="스텝 3(fill '내용') 실패: 일치하는 요소가 없음",
        step_results=[
            StepResult(seq=1, action="navigate", target="/contact", screenshot=f"{screen}-req-{i:03}/step1.png"),
            StepResult(seq=2, action="fill", target="성명", value="홍길동"),
            StepResult(seq=3, action="fill", target="내용", value="x", status="error",
                       error_detail="일치하는 요소가 없음", screenshot=f"{screen}-req-{i:03}/step3.png"),
        ],
        pending_steps=[{"action": "check", "target": "개인정보 수집 동의", "value": None, "phase": "test"},
                       {"action": "click", "target": "문의 등록", "value": None, "phase": "test"}]
        if pending else [])


def _pass(screen="main") -> Verdict:
    return Verdict(case_id=f"{screen}-valid-001", title="열림", plain="화면이 열린다",
                   screen_id=screen, verdict="PASS", evidence={"actual": "확인됨"},
                   step_results=[StepResult(seq=1, action="navigate", target="/",
                                            screenshot=f"{screen}-valid-001/step1.png")])


def _report(cases, **summary) -> TestReport:
    return TestReport(run_id="ui-20261119-000000", target_url="https://example.test",
                      spec_source="spec.pdf", summary={**TestReport.summarize(cases), **summary},
                      cases=cases, created_at="2026-11-19T10:00:00+09:00")


EXPECTED = Expectation(type="error_message", value="내용을 입력해주세요")
NAMES = {"main": "메인화면", "signup": "회원가입", "contact": "CONTACT", "faq": "FAQ"}


def _many() -> TestReport:
    cases = [_pass(), _defect(), _stuck(1), _stuck(2), _stuck(3)]
    return _report(
        cases, screen_names=NAMES,
        spec_warnings=["[faq] 화면 경로가 기획서에 없어 실행하지 않습니다",
                       "[contact] 모델 메모: 표가 두 쪽에 걸쳐 있습니다"],
        coverage_gaps=["[contact] 첨부파일 용량 제한은 확인하지 않았습니다"],
        model="qwen3.5-4b-awq", history={"round": 2, "previous_run": "ui-x", "regressed": [], "fixed": []})


# ── 팀원 리포트(PR 4)의 실패 카드 요소가 빠지지 않는다 ─────────────────────────────

def test_실패_카드의_요소가_기획자용에도_다_있다():
    html = render_planner_html(_report([_defect()], screen_names={"signup": "회원가입"}))
    assert "<span class='no defect'>1</span>" in html                 # 번호
    assert "다른 값을 넣어도 막히지 않습니다" in html                    # 대제목
    assert "<div class='want'><h4>기획서</h4>" in html                 # 좌우 대조
    assert "<div class='got'><h4>실제 화면</h4>" in html
    assert "<table class='src'" in html and "class=hit" in html        # 근거 표의 강조 칸
    assert "<h4>재현 절차</h4>" in html
    assert "<li class=broke>" in html and "기획서를 어긴 단계" in html  # 어긴 단계 강조
    assert "signup-rule-001/step4.png" in html                         # 판정한 화면
    assert "재현 절차 복사" in html and "data-copy=" in html
    assert "비밀번호 확인 · " in html                                   # 어느 항목의 어느 규칙인지


def test_재현_절차는_리포트와_같다():
    v = _defect()
    repro = _repro_html(v, "비밀번호 확인")
    report = _report([v], screen_names={"signup": "회원가입"})
    assert repro in render_planner_html(report)
    assert repro in render_html(report)


def test_원인_추적용_자료는_기획자용에_없다():
    html = render_planner_html(_many())
    for dev_only in ("class='raw'", "4321ms", "<b>그때의 주소</b>", "모델 메모", "qwen3.5",
                     "설계 문서 추출 경고", "class='tag FAIL'", "report.csv"):
        assert dev_only not in html, dev_only
    # 내부 말('스텝 3(fill …) 실패')은 화면에 쓰지 않는다. 개발사에 넘기는 복사 글에만 남는다.
    assert "<span class=head>스텝" not in html and "<p>스텝 3" not in html
    # 통과한 건은 카드가 아니라 수로만.
    assert "id='c-main-valid-001'" not in html
    assert "기획서대로인 항목 1건" in html


def test_판정의_뜻을_바꾸는_알림은_남는다():
    html = render_planner_html(_report([_pass()], llm_backend="mock", filtered_by={"only": "x"},
                                       cases_available=9))
    assert "연습용으로 실행한 결과입니다" in html
    assert "일부 케이스만 실행했습니다" in html and "전체 9건 중 1건" in html


# ── 재현 절차: 멈춘 단계 강조와 그 뒤 단계 ─────────────────────────────────────

def test_멈춘_단계는_강조하고_뒤_단계를_흐리게_잇는다():
    html = _repro_html(_stuck(1))
    assert html.count("<li") == 5
    assert "<li class='broke stuck'>&#x27;내용&#x27; 칸에" in html or "<li class='broke stuck'>'내용' 칸에" in html
    assert "<em class='stop'>여기서 멈춤</em>" in html
    assert html.count("<li class='todo'>") == 2
    assert html.index("여기서 멈춤") < html.index("<li class='todo'>")
    assert "실행하지 못했습니다" in html


def test_끝까지_간_케이스에는_남은_단계가_없다():
    html = _repro_html(_defect(), "비밀번호 확인")
    assert "class='todo'" not in html and "여기서 멈춤" not in html


def test_판정이_남은_단계를_싣는다():
    case = TestCase(
        case_id="c-1", screen_id="contact", title="t", type="negative", expected=EXPECTED,
        setup_steps=[TestStep(seq=1, action="navigate", target="/login")],
        steps=[TestStep(seq=1, action="navigate", target="/contact"),
               TestStep(seq=2, action="fill", target="내용", value="x"),
               TestStep(seq=3, action="click", target="문의 등록")])
    done = [StepResult(seq=1, action="navigate", target="/login", phase="setup"),
            StepResult(seq=1, action="navigate", target="/contact"),
            StepResult(seq=2, action="fill", target="내용", value="x", status="error")]
    assert pending_steps(case, done) == [
        {"action": "click", "target": "문의 등록", "value": None, "phase": "test"}]
    ok = [r.model_copy(update={"status": "ok"}) for r in done]
    assert pending_steps(case, ok) == []
    # 전제에서 멈추면 본 스텝 전부가 남는다.
    setup_fail = [StepResult(seq=1, action="navigate", target="/login", phase="setup", status="error")]
    assert [s["target"] for s in pending_steps(case, setup_fail)] == ["/contact", "내용", "문의 등록"]


def test_옛_실행은_계획_파일에서_남은_단계를_채운다(tmp_path):
    report = _report([_stuck(1, pending=False)], screen_names={"contact": "CONTACT"})
    (tmp_path / "plan.json").write_text(json.dumps({"all_cases": [{
        "case_id": "contact-req-001", "setup_steps": [],
        "steps": [{"action": "navigate", "target": "/contact"},
                  {"action": "fill", "target": "성명", "value": "홍길동"},
                  {"action": "fill", "target": "내용", "value": "x"},
                  {"action": "click", "target": "문의 등록"}]}]}), encoding="utf-8")
    fill_pending_from_plan(report, tmp_path)
    assert report.cases[0].pending_steps == [
        {"action": "click", "target": "문의 등록", "value": None, "phase": "test"}]


def test_계획_파일이_없어도_만든다(tmp_path):
    path = save_planner_html(_report([_stuck(1, pending=False)]), tmp_path)
    assert path.name == "planner.html" and "여기서 멈춤" in path.read_text(encoding="utf-8")


# ── 화면 단위로 넘겨 본다 ────────────────────────────────────────────────────

def test_화면이_여럿이면_장으로_나눈다():
    html = render_planner_html(_many())
    # 요약 장 + 케이스가 있는 화면 3개.
    assert html.count("<section class='pg'") == 4
    assert "<nav class='pgnav'" in html
    assert "화면별 결과 (4)" in html
    # 요약 장의 목록이 각 장으로 간다.
    assert "<a class='scr' href='#p-3'>" in html
    # 보지 않은 화면은 장이 없고 까닭을 적는다.
    assert "<b class='unseen'>보지 않음</b> — 화면 주소가 기획서에 없어 열지 못했습니다" in html
    # 요약 장에는 카드가 없다 — 길어지지 않는다.
    top = html[html.index("id='p-top'"):html.index("id='p-1'")]
    assert "<details class='case" not in top
    # 그 화면의 건은 그 화면의 장에 있다.
    contact = html[html.index("id='p-3'"):]
    assert "id='c-contact-req-001'" in contact and "id='c-signup-rule-001'" not in contact
    assert "첨부파일 용량 제한은 확인하지 않았습니다" in contact


def test_화면이_하나면_한_장이다():
    html = render_planner_html(_report([_defect(), _pass("signup")], screen_names={"signup": "회원가입"}))
    assert html.count("<section class='pg'") == 1
    assert "<nav class='pgnav'" not in html
    assert "id='c-signup-rule-001'" in html


def test_같은_이유로_멈춘_건은_이유를_한_번만_적는다():
    html = render_planner_html(_many())
    assert "같은 이유로 3건" in html
    sentence = "칸에 입력하려다 멈췄습니다. 화면에서 그 이름을 찾지 못했습니다."
    contact = html[html.index("id='p-3'"):]
    # 묶음 머리에 한 번. 건마다의 제목은 확인하려던 것이고, 이유는 펼친 칸 안에 있다.
    assert contact.count(f"<span class=head>") == 3
    assert "<span class=head>항목 1을 비워 두면 막힌다</span>" in contact
    assert sentence in contact


def test_번호는_리포트와_같다():
    report = _many()
    planner, dev = render_planner_html(report), render_html(report)
    for no, cid in ((1, "signup-rule-001"), (2, "contact-req-001")):
        for html in (planner, dev):
            card = html[html.index(f"id='c-{cid}'"):]
            assert f">{no}</span>" in card[:card.index("</summary>")]


def test_인쇄하면_모든_장을_펼치고_밝게_찍는다():
    html = render_planner_html(_many())
    assert ".pg[hidden] { display:block !important; }" in html
    assert "setAttribute('data-theme', 'light')" in html


# ── 밝게 / 어둡게 ───────────────────────────────────────────────────────────

def test_두_리포트_모두_밝게_어둡게_버튼이_있다():
    report = _many()
    for html in (render_planner_html(report), render_html(report)):
        assert "id='themeBtn'" in html
        assert "localStorage.setItem('prova-theme'" in html


# ── 멈춘 단계는 어디서 보든 같다 — 리포트 카드·복사 글·엑셀 (2026-11-19) ─────────────
#
# 팀원 리포트(PR 4)에서는 멈춘 단계에 꼬리표만 있고 강조가 없었다. 복사 글과 엑셀은 멈춘 데서
# 끊겼고, 대제목과 '실제 화면' 칸은 내부 말('스텝 7(fill …) 실패', '스텝 7 에서 중단')이었다.

def test_고치는_사람용_리포트도_멈춘_단계를_강조하고_뒤_단계를_잇는다():
    v = _stuck(1)
    v.evidence = {"expected": "성공 안내가 보인다", "actual": "스텝 3 에서 중단"}
    html = render_html(_report([v], screen_names={"contact": "CONTACT"}))
    assert "<li class='broke stuck'>" in html and "여기서 멈춤" in html
    assert html.count("<li class='todo'>") == 2
    # 대제목과 '실제 화면' 칸은 무엇을 하려다 멈췄는지다.
    assert "<span class=head>스텝" not in html and "<p>스텝 3 에서 중단</p>" not in html
    assert "<span class=head>&#x27;내용&#x27; 칸에 입력하려다 멈췄습니다." in html


def test_복사_글과_엑셀도_멈춘_단계와_뒤_단계를_적는다():
    from prova.s6_report.xlsx_export import _reproduction
    from prova.wording import copy_text

    v = _stuck(1)
    v.evidence = {"actual": "스텝 3 에서 중단"}
    lines = _reproduction(v).split("\n")
    assert lines[2] == "3. '내용' 칸에 'x' 입력 ← 여기서 멈춤"
    assert lines[3:] == ["4. '개인정보 수집 동의' 체크 (실행하지 못함)", "5. '문의 등록' 클릭 (실행하지 못함)"]
    text = copy_text(v, "[실행 문제] 제목")
    assert "← 여기서 멈춤" in text and "(실행하지 못함)" in text
    assert "실제: '내용' 칸에 입력하려다 멈췄습니다." in text


def test_고치는_사람용_리포트도_옛_실행은_계획_파일에서_채운다(tmp_path):
    from prova.s6_report.report_builder import save_html

    report = _report([_stuck(1, pending=False)], screen_names={"contact": "CONTACT"})
    (tmp_path / "plan.json").write_text(json.dumps({"all_cases": [{
        "case_id": "contact-req-001", "setup_steps": [],
        "steps": [{"action": "navigate", "target": "/contact"},
                  {"action": "fill", "target": "성명", "value": "홍길동"},
                  {"action": "fill", "target": "내용", "value": "x"},
                  {"action": "click", "target": "문의 등록"}]}]}), encoding="utf-8")
    html = save_html(report, tmp_path).read_text(encoding="utf-8")
    assert html.count("<li class='todo'>") == 1


def test_리포트는_실패_케이스와_통과_케이스가_맨_위다():
    """결론 바로 아래가 실패·통과 케이스다. 실행 정보·직전 비교·화면별 범위는 그 아래 (2026-11-19)."""
    report = _many()
    report.summary["plan"] = {"backend": "replay", "created_at": "2026-11-19"}
    html = render_html(report)
    fail_at, pass_at = html.index("<h2>실패 케이스"), html.index("<h2>통과 케이스")
    for later in ("<b>두 단계 실행", "<h2>화면별 확인 범위"):
        if later in html:
            assert html.index(later) > pass_at, later
    assert html.index("<div class='chart'") < fail_at
