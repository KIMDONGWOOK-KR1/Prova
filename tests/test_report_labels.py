"""리포트는 내부 이름 대신 사람이 읽는 말을 쓴다 (2026-09-22 사용성 점검).

기획자·QA 담당자가 읽는 문서인데 규칙 태그가 `password.require_uppercase`,
스텝 표가 `fill`·`ok`, 제외 목록이 `login-password-require_uppercase-006` 이었다.
코드를 아는 사람만 읽는다. 식별자는 지우지 않는다 — 옆에 두거나 작게 둔다.
"""

from __future__ import annotations

from prova.models import CaseSelection, Expectation, StepResult, TestCase, Verdict
from prova.s2_case_generator.selector import select_by_ids
from prova.s6_report.report_builder import _case_html, _steps_html, render_html
from prova.models import TestReport


def _verdict(**kw):
    base = dict(case_id="login-password-require_uppercase-006", title="대문자 검증",
                type="negative", screen_id="login", verdict="FAIL",
                violates="require_uppercase", target_element="password",
                failure_category="assertion_mismatch", failure_detail="사유")
    base.update(kw)
    return Verdict(**base)


def test_규칙_태그는_한글_이름을_쓴다():
    html = _case_html(_verdict(), open_by_default=True)
    assert "password · 대문자 포함" in html
    assert "password.require_uppercase" not in html


def test_모르는_규칙은_키를_그대로_둔다():
    html = _case_html(_verdict(violates="brand_new_rule"), open_by_default=True)
    assert "password · brand_new_rule" in html


def test_스텝_표는_동작과_상태를_한글로():
    v = _verdict(step_results=[
        StepResult(seq=1, action="fill", target="이메일", status="ok"),
        StepResult(seq=2, action="click", target="로그인", status="error",
                   error_detail="가려짐"),
    ])
    html = _steps_html(v)
    assert "<td>입력</td>" in html and "<td>클릭</td>" in html
    assert ">성공<" in html and ">오류<" in html
    assert "<td>fill</td>" not in html


def _case(cid, title):
    return TestCase(case_id=cid, title=title, type="negative", screen_id="login",
                    expected=Expectation(type="error_message", value="x"))


def test_제외한_케이스는_제목으로_보인다():
    cases = [_case("login-a-001", "형식 검증"), _case("login-b-002", "길이 검증")]
    _, sel = select_by_ids(cases, ["login-a-001"])
    assert sel.excluded_titles == {"login-b-002": "길이 검증"}

    report = TestReport(run_id="r", target_url="http://x/good", selection=sel,
                        summary={"total": 1, "pass": 1, "fail": 0, "pass_rate": 100.0})
    html = render_html(report)
    assert "길이 검증" in html
    assert "login-b-002" in html  # id 는 옆에 남는다


def test_옛_계획의_선택에도_읽힌다():
    """excluded_titles 가 없는 옛 plan.json·report.json 도 그대로 읽혀야 한다."""
    sel = CaseSelection.model_validate({"request": "x", "selected": ["a"],
                                        "excluded": ["b"]})
    assert sel.excluded_titles == {}
