"""리포트·엑셀·계획 화면이 기획서의 말로 적고, 넣은 값을 보여 준다 (2026-11-10).

화면을 직접 보고 찾은 두 가지다.

1. **실패를 손으로 재현할 수 없었다.** 단계 표에 '입력 · 닉네임' 만 있고 무슨 값을 넣었는지가
   없었다. 계획 화면도 제목만 보여 줘, 무슨 값으로 무엇을 기대하는지 모른 채 승인했다.
2. **식별자로 적혀 있었다.** `'password_confirm' 의 'same_as' 검증 규칙`,
   `type=error_message 문구='…'`. 읽는 사람은 기획자와 테스트 담당자다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

from prova.models import (
    Expectation, ExpectedType, ScreenSpec, StepResult, TestCase, TestReport, TestStep, Verdict,
)
from prova.s2_case_generator.generator import generate_cases
from prova.s5_verifier.assertion_engine import _expected_summary, _failure_detail
from prova.s6_report.report_builder import _case_html, _steps_html
from prova.s6_report.xlsx_export import CASE_COLUMNS, DEFECT_COLUMNS, _case_rows, _defect_rows
from prova.wording import expectation_sentence, reproduction_lines, step_sentence

SPEC_DIR = Path("fixtures/specs")


def _signup_cases() -> list[TestCase]:
    spec = ScreenSpec.model_validate(
        json.loads((SPEC_DIR / "signup_spec.golden.json").read_text(encoding="utf-8")))
    return generate_cases(spec)


# ── 기대 문장 ────────────────────────────────────────────────────────────────

_SAMPLES = {
    "error_message": Expectation(type="error_message", value="비밀번호가 일치하지 않습니다."),
    "error_shown": Expectation(type="error_shown"),
    "text_visible": Expectation(type="text_visible", value="환영합니다"),
    "text_absent": Expectation(type="text_absent", value="가입되지 않은 이메일"),
    "redirect": Expectation(type="redirect", url_contains="/dashboard"),
    "toast_or_redirect": Expectation(type="toast_or_redirect", value="가입 완료",
                                     url_contains="/welcome"),
    "result_count": Expectation(type="result_count", count=3, count_target="검색 결과"),
    "options_present": Expectation(type="options_present", options=["검색", "광고"],
                                   option_target="가입 경로"),
    "placeholders_match": Expectation(type="placeholders_match",
                                      placeholders={"이메일": "example@prova.dev"}),
    "labels_findable": Expectation(type="labels_findable", labels=["이메일", "비밀번호"]),
    "sorted_desc": Expectation(type="sorted_desc", order_target="주문일"),
    "sum_matches": Expectation(type="sum_matches", sum_row_target="금액",
                               sum_total_target="합계"),
}


def test_기대_유형마다_문장이_있다():
    """유형이 늘면 여기서 걸린다 — 문장 없는 유형은 코드 이름이 그대로 리포트에 나간다."""
    assert set(_SAMPLES) == set(get_args(ExpectedType))
    for kind, expected in _SAMPLES.items():
        sentence = expectation_sentence(expected)
        assert sentence and sentence != kind, kind
        assert "type=" not in sentence and "None" not in sentence, sentence


def test_기대_문장은_기획서의_문구와_이름을_담는다():
    assert "'비밀번호가 일치하지 않습니다.'" in expectation_sentence(_SAMPLES["error_message"])
    assert expectation_sentence(_SAMPLES["result_count"]) == "'검색 결과' 목록에 3건이 보인다"
    both = expectation_sentence(_SAMPLES["toast_or_redirect"])
    assert "'가입 완료'" in both and "'/welcome'" in both and "또는" in both
    assert "'검색', '광고'" in expectation_sentence(_SAMPLES["options_present"])


def test_근거의_기대_줄이_문장이다():
    assert _expected_summary(_SAMPLES["error_message"]).startswith("오류 문구 ")


# ── 재현 절차 ────────────────────────────────────────────────────────────────

def test_스텝을_따라_할_수_있는_말로_적는다():
    assert step_sentence("navigate", "/signup") == "'/signup' 주소로 이동"
    assert step_sentence("fill", "닉네임", "a1aaaaaaaaa") == "'닉네임' 칸에 'a1aaaaaaaaa' 입력"
    assert step_sentence("fill", "이메일", "") == "'이메일' 칸을 비워 둔다"
    assert step_sentence("select", "가입 경로", "검색") == "'가입 경로' 에서 '검색' 선택"
    assert step_sentence("uncheck", "약관 동의") == "'약관 동의' 체크 해제"
    assert step_sentence("click", "가입하기") == "'가입하기' 클릭"


def test_재현_절차는_준비와_실행을_가른다():
    setup = [TestStep(seq=1, action="navigate", target="/login")]
    steps = [TestStep(seq=1, action="navigate", target="/orders"),
             TestStep(seq=2, action="click", target="조회")]
    assert reproduction_lines(steps, setup) == [
        "준비 1. '/login' 주소로 이동", "1. '/orders' 주소로 이동", "2. '조회' 클릭"]


def test_단계_표가_넣은_값을_보여_준다():
    verdict = Verdict(case_id="c", verdict="FAIL", step_results=[
        StepResult(seq=1, action="navigate", target="/signup"),
        StepResult(seq=2, action="fill", target="닉네임", value="a1aaaaaaaaa"),
    ])
    html = _steps_html(verdict)
    assert "<th>값</th>" in html
    assert "a1aaaaaaaaa" in html
    assert "None" not in html  # 값이 없는 스텝은 빈칸


def test_엑셀에_재현_절차_칸이_있다():
    verdict = Verdict(
        case_id="signup-nickname-max_length-012", title="닉네임 최대 길이", type="negative",
        screen_id="signup", verdict="FAIL", failure_category="assertion_mismatch",
        step_results=[
            StepResult(seq=1, action="navigate", target="/signup"),
            StepResult(seq=2, action="fill", target="닉네임", value="a1aaaaaaaaa"),
            StepResult(seq=3, action="click", target="가입하기"),
        ])
    report = TestReport(run_id="r", target_url="http://x", total=1, passed=0, failed=1,
                        cases=[verdict])
    want = "1. '/signup' 주소로 이동\n2. '닉네임' 칸에 'a1aaaaaaaaa' 입력\n3. '가입하기' 클릭"
    for columns, rows in ((CASE_COLUMNS, _case_rows(report, {})),
                          (DEFECT_COLUMNS, _defect_rows(report, {}))):
        assert len(rows[0]) == len(columns)
        assert rows[0][columns.index("재현 절차")] == want


# ── 식별자 대신 기획서의 이름 ────────────────────────────────────────────────

def test_케이스가_요소의_기획서_이름을_갖는다():
    cases = _signup_cases()
    rule_cases = [c for c in cases if c.target_element]
    assert rule_cases
    assert all(c.target_label for c in rule_cases)
    same_as = next(c for c in cases if c.violates == "same_as")
    assert same_as.target_element == "password_confirm"
    assert same_as.target_label == "비밀번호 확인"


def test_실패_사유가_기획서의_이름으로_적힌다():
    same_as = next(c for c in _signup_cases() if c.violates == "same_as")
    detail = _failure_detail(same_as, "에러가 전혀 노출되지 않음")
    assert "'비밀번호 확인' 칸의 '다른 항목과 일치' 검증 규칙" in detail
    assert "password_confirm" not in detail and "same_as" not in detail


def test_요소_이름이_없으면_식별자로_적는다():
    """예전에 저장한 계획(plan.json)에는 이름이 없다 — 빈칸이 아니라 식별자가 나와야 한다."""
    case = TestCase(case_id="c", screen_id="s", title="t", type="negative",
                    violates="min_length", target_element="password",
                    expected=Expectation(type="error_shown"))
    assert "'password' 칸의 '최소 길이' 검증 규칙" in _failure_detail(case, "사유")


def test_리포트_규칙_표시가_기획서의_이름을_쓴다():
    verdict = Verdict(case_id="c", verdict="FAIL", violates="same_as",
                      target_element="password_confirm", target_label="비밀번호 확인",
                      failure_category="assertion_mismatch")
    html = _case_html(verdict, open_by_default=True)
    assert "비밀번호 확인 · 다른 항목과 일치" in html
    assert "title='password_confirm'" in html  # 식별자는 지우지 않고 작게 둔다
