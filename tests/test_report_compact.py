"""리포트 압축판 (2026-11-19) — 실패·통과 케이스가 맨 위, 나머지는 '참고' 한 절.

실물 기획서 실행(화면 21개·43건·경고 150줄)에서 팀원 리포트(PR 4)가 길고 지저분했다.
문서를 둘로 나누는 안(기획자용 planner.html)을 만들어 봤으나, 리포트 하나를 압축하는 쪽으로 정했다.

여기서 고정하는 것:
- 재현 절차는 멈춘 단계를 강조하고 그 뒤의 실행하지 못한 단계까지 보인다 — 카드·복사 글·엑셀 모두.
- 실패·통과 케이스가 맨 위고, 그 밖의 내용은 아래 '참고' 하나다.
- 밝게/어둡게 버튼이 있고, 인쇄는 늘 밝게 찍는다.
"""

from __future__ import annotations

import json

from prova.models import (
    Expectation, SpecSource, StepResult, TestCase, TestReport, TestStep, Verdict,
)
from prova.s5_verifier.assertion_engine import pending_steps
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
def test_리포트도_멈춘_단계를_강조하고_뒤_단계를_잇는다():
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
def test_리포트도_옛_실행은_계획_파일에서_채운다(tmp_path):
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
    # 압축판(2026-11-19): 케이스 아래에는 '참고' 하나뿐이다. 한 줄 목록·화면별 범위는 없다.
    assert html.index("<h2 class='brief-h'>참고</h2>") > pass_at
    assert "<div class='flist" not in html and "<h2>화면별 확인 범위" not in html
    for later in ("두 단계 실행(",):
        if later in html:
            assert html.index(later) > pass_at, later
    assert html.index("<div class='chart'") < fail_at



def test_밝게_어둡게_버튼이_있고_인쇄는_밝게_찍는다():
    html = render_html(_report([_pass()]))
    assert "id='themeBtn'" in html
    assert "localStorage.setItem('prova-theme'" in html
    assert "setAttribute('data-theme', 'light')" in html

