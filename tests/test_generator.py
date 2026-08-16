"""generator 테스트 — 기대 문구의 출처와 케이스 구성.

여기서 지키려는 성질은 두 가지다.
1) 기대 문구를 억측하지 않는다 (오탐 방지). 문구를 모르면 error_shown 으로 격하.
2) 위반 케이스는 대상 요소만 위반값이고 나머지는 유효값이다 (원인 분리).
"""

import json
from pathlib import Path

import pytest

from prova.models import ScreenSpec, UIElement
from prova.s2_case_generator.generator import (
    generate_cases,
    parse_success_expectation,
)

GOLDEN = Path("fixtures/specs/login_spec.golden.json")


@pytest.fixture
def login_spec() -> ScreenSpec:
    return ScreenSpec.model_validate(json.loads(GOLDEN.read_text(encoding="utf-8")))


def minimal_spec(**kw) -> ScreenSpec:
    base = dict(
        screen_id="s", screen_name="화면", url_path="/s",
        elements=[
            UIElement(element_id="f", type="input", label="필드", required=True,
                      constraints={"min_length": 4}, error_message="4자 이상 입력하세요."),
            UIElement(element_id="btn", type="button", label="확인"),
        ],
        success_condition="/done 으로 이동하고 \"완료\" 를 노출한다",
    )
    base.update(kw)
    return ScreenSpec(**base)


class TestParseSuccessExpectation:
    def test_경로와_문구를_모두_뽑는다(self, login_spec):
        exp = parse_success_expectation(login_spec)
        assert exp.url_contains == "/dashboard"
        assert exp.value == "환영합니다"

    def test_자기_경로는_이동_대상으로_보지_않는다(self):
        spec = minimal_spec(url_path="/login",
                            success_condition="/login 에서 /dashboard 로 이동한다")
        assert parse_success_expectation(spec).url_contains == "/dashboard"

    def test_성공조건이_비면_기대도_비어있다(self):
        spec = minimal_spec(success_condition="")
        exp = parse_success_expectation(spec)
        assert exp.value == "" and exp.url_contains is None


class TestGenerateCases:
    def test_정상케이스가_맨_앞에_온다(self, login_spec):
        """정상 케이스가 실패하면 화면 자체가 동작하지 않는다는 뜻이므로,
        리포트를 읽는 사람이 그 사실을 가장 먼저 봐야 한다."""
        cases = generate_cases(login_spec)
        assert cases[0].type == "positive"
        assert all(c.type == "negative" for c in cases[1:])

    def test_규칙마다_케이스가_하나씩_생긴다(self, login_spec):
        cases = generate_cases(login_spec)
        violated = [c.violates for c in cases if c.type == "negative"]
        assert sorted(violated) == sorted([
            "required", "format",              # email
            "required", "min_length", "require_uppercase", "require_special",  # password
        ])

    def test_정상케이스는_기획서_예시값을_쓴다(self, login_spec):
        """코드가 만든 값은 규칙만 만족한다. 등록된 계정 값이 아니면 정상
        케이스가 구현 결함 없이 실패한다(오탐)."""
        case = generate_cases(login_spec)[0]
        values = {s.target: s.value for s in case.steps if s.action == "fill"}
        assert values["이메일"] == "user@test.com"
        assert values["비밀번호"] == "Abcd123!"

    def test_위반케이스는_대상_요소만_위반값이다(self, login_spec):
        """나머지 요소에 유효값이 들어가야 실패 원인이 대상 규칙으로 좁혀진다."""
        cases = generate_cases(login_spec)
        case = next(c for c in cases if c.violates == "require_uppercase")
        values = {s.target: s.value for s in case.steps if s.action == "fill"}
        assert values["이메일"] == "user@test.com"          # 유효값 유지
        assert not any(ch.isupper() for ch in values["비밀번호"])  # 대상만 위반

    def test_스텝_순서는_navigate_fill_click(self, login_spec):
        steps = generate_cases(login_spec)[0].steps
        assert [s.action for s in steps] == ["navigate", "fill", "fill", "click"]
        assert steps[0].target == "/login"
        assert steps[-1].target == "로그인"

    def test_case_id가_고유하다(self, login_spec):
        ids = [c.case_id for c in generate_cases(login_spec)]
        assert len(ids) == len(set(ids))

    def test_case_id에_한글이_섞이지_않는다(self, login_spec):
        """case_id 는 스크린샷 저장 경로에 쓰인다."""
        for c in generate_cases(login_spec):
            assert c.case_id.isascii(), c.case_id


class TestExpectationSource:
    """기대 문구의 출처가 규칙에 따라 다르다 — 이 모듈의 핵심 계약."""

    def test_required는_화면_공통문구를_쓴다(self, login_spec):
        case = next(c for c in generate_cases(login_spec)
                    if c.violates == "required" and c.target_element == "email")
        assert case.expected.value == "필수 입력 항목입니다."

    def test_형식위반은_요소의_에러메시지를_쓴다(self, login_spec):
        case = next(c for c in generate_cases(login_spec) if c.violates == "format")
        assert case.expected.value == "올바른 이메일 형식을 입력하세요."

    def test_공통문구가_없으면_요소_메시지로_폴백(self):
        spec = minimal_spec(required_message=None)
        case = next(c for c in generate_cases(spec) if c.violates == "required")
        assert case.expected.value == "4자 이상 입력하세요."

    def test_문구를_전혀_모르면_error_shown으로_격하한다(self):
        """억측한 문구로 오탐을 만드는 것보다 '에러가 떴는지' 만 보는 게 낫다."""
        spec = minimal_spec(
            required_message=None,
            elements=[
                UIElement(element_id="f", type="input", label="필드", required=True,
                          constraints={"min_length": 4}, error_message=None),
                UIElement(element_id="btn", type="button", label="확인"),
            ],
        )
        for case in generate_cases(spec):
            if case.type == "negative":
                assert case.expected.type == "error_shown"
                assert case.expected.value == ""


class TestTitlePolish:
    def test_llm이_없으면_규칙기반_제목을_쓴다(self, login_spec):
        for c in generate_cases(login_spec, llm=None):
            assert c.title

    def test_llm이_실패해도_케이스는_살아있다(self, login_spec):
        """제목은 판정 근거가 아니므로 LLM 실패가 파이프라인을 세우면 안 된다."""
        from prova.llm.mock_backend import MockLLM

        broken = MockLLM()  # CaseTitles 응답이 등록되지 않아 LLMError 를 던진다
        cases = generate_cases(login_spec, llm=broken)
        assert len(cases) == 7
        assert all(c.title for c in cases)
        assert any("제목 다듬기" in w for w in login_spec.warnings)


SIGNUP_GOLDEN = Path("fixtures/specs/signup_spec.golden.json")


@pytest.fixture
def signup_spec() -> ScreenSpec:
    return ScreenSpec.model_validate(json.loads(SIGNUP_GOLDEN.read_text(encoding="utf-8")))


class TestElementTypeActions:
    """요소 유형마다 다른 액션을 낸다.

    체크박스에 fill() 을 부르면 Playwright 가 조작 오류로 실패한다. 그러면
    '약관 미동의 시 에러가 뜨는가' 를 검증하려던 케이스가 요소 조작 실패로
    뭉개져, 구현에 결함이 있는지 없는지 알 수 없게 된다.
    """

    def test_정상케이스의_액션이_유형별로_갈린다(self, signup_spec):
        steps = generate_cases(signup_spec)[0].steps
        by_target = {s.target: s.action for s in steps}
        assert by_target["이메일"] == "fill"
        assert by_target["가입 경로"] == "select"
        assert by_target["약관 동의"] == "check"
        assert by_target["가입하기"] == "click"

    def test_체크박스_미체크_케이스는_uncheck를_쓴다(self, signup_spec):
        case = next(c for c in generate_cases(signup_spec)
                    if c.target_element == "agree_terms")
        action = next(s.action for s in case.steps if s.target == "약관 동의")
        assert action == "uncheck"

    def test_선택요소_미선택_케이스는_빈값을_고른다(self, signup_spec):
        case = next(c for c in generate_cases(signup_spec)
                    if c.target_element == "signup_path")
        step = next(s for s in case.steps if s.target == "가입 경로")
        assert step.action == "select" and step.value == ""

    def test_체크박스에는_fill_액션이_나오지_않는다(self, signup_spec):
        for c in generate_cases(signup_spec):
            for s in c.steps:
                if s.target == "약관 동의":
                    assert s.action in ("check", "uncheck"), s.action


class TestRequiredMessageSource:
    """필수 입력 문구의 출처 — 오탐이 가장 나기 쉬운 지점."""

    def test_검증규칙이_있는_요소는_화면_공통문구를_쓴다(self, signup_spec):
        case = next(c for c in generate_cases(signup_spec)
                    if c.violates == "required" and c.target_element == "email")
        assert case.expected.value == "필수 입력 항목입니다."

    def test_다른_규칙이_없는_요소는_자기_문구를_쓴다(self, signup_spec):
        """체크박스에 형식 검증이 있을 수 없으니 "약관에 동의해야 합니다." 는
        미동의 상태의 문구다. 화면 공통 문구를 쓰면 구현이 옳아도 FAIL 이 된다."""
        cases = generate_cases(signup_spec)
        agree = next(c for c in cases if c.target_element == "agree_terms")
        assert agree.expected.value == "약관에 동의해야 합니다."
        path = next(c for c in cases if c.target_element == "signup_path")
        assert path.expected.value == "가입 경로를 선택하세요."


class TestCrossFieldCases:
    def test_교차필드_위반_케이스가_생긴다(self, signup_spec):
        cases = generate_cases(signup_spec)
        case = next(c for c in cases if c.violates == "same_as")
        values = {s.target: s.value for s in case.steps if s.action == "fill"}
        assert values["비밀번호 확인"] != values["비밀번호"]
        assert case.expected.value == "비밀번호가 일치하지 않습니다."

    def test_참조_요소_위반시_의존값이_함께_바뀐다(self, signup_spec):
        """한 케이스가 두 규칙을 동시에 깨지 않게 하는 지점."""
        case = next(c for c in generate_cases(signup_spec)
                    if c.violates == "require_uppercase")
        values = {s.target: s.value for s in case.steps if s.action == "fill"}
        assert values["비밀번호 확인"] == values["비밀번호"]

    def test_회원가입_케이스가_14건이다(self, signup_spec):
        assert len(generate_cases(signup_spec)) == 14
