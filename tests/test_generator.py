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
        리포트를 읽는 사람이 그 사실을 가장 먼저 봐야 한다.

        그 뒤에 규칙 위반이 이어지고, 선택 목록·기획서 예시 케이스가 맨 뒤에 온다 —
        뒤쪽은 규칙 위반이 아니므로 positive 다."""
        cases = generate_cases(login_spec)
        assert cases[0].type == "positive"
        assert cases[0].case_id.endswith("valid-001")

        types = [c.type for c in cases]
        negatives = [i for i, t in enumerate(types) if t == "negative"]
        assert negatives, "위반 케이스가 있어야 한다"
        assert negatives == list(range(negatives[0], negatives[-1] + 1)), (
            "위반 케이스는 한 덩어리로 이어져야 읽는 사람이 규칙 목록으로 본다"
        )

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
        assert len(cases) == 9
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

    def test_회원가입_케이스가_16건이다(self, signup_spec):
        """정상 1 + 규칙 위반 13 + 선택 목록 1 + 안내 문구 1 = 16."""
        assert len(generate_cases(signup_spec)) == 16


SEARCH_GOLDEN = Path("fixtures/specs/search_spec.golden.json")


@pytest.fixture
def search_spec() -> ScreenSpec:
    return ScreenSpec.model_validate(json.loads(SEARCH_GOLDEN.read_text(encoding="utf-8")))


class TestScenarioCases:
    """기획서가 제시한 입력-결과 예시 — 규칙으로 표현할 수 없는 검증.

    로그인·회원가입은 '값이 규칙을 어겼는가' 였고, 그래서 규칙에서 위반값을 만들 수
    있었다. 검색은 '정상 입력에 정해진 결과가 나오는가' 다. 규칙이 없으니 위반값도
    만들 수 없고, 기획서가 데이터를 주지 않으면 검증 자체가 불가능하다.
    """

    def test_시나리오마다_케이스가_생긴다(self, search_spec):
        cases = generate_cases(search_spec)
        scenario_cases = [c for c in cases if "scenario" in c.case_id]
        assert len(scenario_cases) == len(search_spec.scenarios) == 2

    def test_시나리오는_positive다(self, search_spec):
        """negative 로 두면 S5 의 판정이 뒤집혀 '에러가 떠야 PASS' 가 된다.
        시나리오는 규칙을 어긴 값이 아니라 정상 입력이다."""
        for c in generate_cases(search_spec):
            if "scenario" in c.case_id:
                assert c.type == "positive"
                assert c.violates is None

    def test_기대는_문구_노출이다(self, search_spec):
        case = next(c for c in generate_cases(search_spec) if "scenario" in c.case_id)
        assert case.expected.type == "text_visible"
        assert case.expected.value == "검색 결과 3건"

    def test_지정한_입력값이_그대로_들어간다(self, search_spec):
        """위반값 생성을 거치지 않는다 — 'notebook' 은 규칙에서 유도되지 않는다."""
        cases = generate_cases(search_spec)
        values = [
            {s.target: s.value for s in c.steps if s.action == "fill"}
            for c in cases if "scenario" in c.case_id
        ]
        assert {"검색어": "notebook"} in values
        assert {"검색어": "zzzz"} in values

    def test_지정하지_않은_입력은_정상값으로_채운다(self):
        """입력이 여럿인 화면에서 시나리오가 하나만 지정하면, 나머지가 비어 있으면
        필수 검증에 먼저 걸려 시나리오가 확인되지 않는다."""
        from prova.models import Scenario

        spec = minimal_spec(
            elements=[
                UIElement(element_id="a", type="input", label="가", required=True,
                          constraints={"min_length": 2}, sample_value="유효값"),
                UIElement(element_id="b", type="input", label="나", required=True,
                          constraints={"min_length": 2}, sample_value="다른값"),
                UIElement(element_id="btn", type="button", label="확인"),
            ],
            scenarios=[Scenario(given={"a": "특정값"}, expect_text="안내 문구")],
        )
        case = next(c for c in generate_cases(spec) if "scenario" in c.case_id)
        values = {s.target: s.value for s in case.steps if s.action == "fill"}
        assert values == {"가": "특정값", "나": "다른값"}

    def test_시나리오가_없으면_케이스도_없다(self):
        """기획서가 예시를 주지 않으면 이 검증은 불가능하다 — 도구의 한계가 아니라
        기획서의 한계다. 없는 예시를 지어내면 화면에 없는 문구를 요구해 오탐이 된다.

        (로그인 기획서는 커버리지 검출기가 찾아낸 구멍을 닫으려고 예시를 추가했으므로
        더 이상 '시나리오 없는 화면' 이 아니다.)"""
        spec = minimal_spec()
        assert spec.scenarios == []
        assert not any("scenario" in c.case_id for c in generate_cases(spec))

    def test_검색_케이스가_9건이다(self, search_spec):
        """정상 1 + 규칙 위반 3(required·min_length·max_length) + 시나리오 2
        + 건수 2 + 안내 문구 1 = 9. 시나리오 하나가 문구 케이스와 건수 케이스로
        나뉜다."""
        assert len(generate_cases(search_spec)) == 9


class TestResultCountCases:
    """건수를 DOM 에서 직접 세는 케이스.

    문구 확인(text_visible)과 나란히 놓는 별도 경로다. 화면이 "검색 결과 3건" 을
    안 찍고 목록만 렌더해도 검증이 성립해야 한다 — 실물 화면이 건수를 문구로
    보여주지 않으면 문구 경로는 아무것도 확인하지 못한다.
    """

    def test_건수가_있는_시나리오마다_케이스가_생긴다(self, search_spec):
        cases = [c for c in generate_cases(search_spec) if "-count-" in c.case_id]
        assert len(cases) == 2
        assert {c.expected.count for c in cases} == {3, 0}

    def test_기대는_목록_라벨을_가리킨다(self, search_spec):
        """무엇을 셀지가 기대값에 담겨야 한다. 없으면 S3 가 화면에서 목록을
        추측해야 하고, 추측해서 센 숫자는 신뢰할 수 없다."""
        case = next(c for c in generate_cases(search_spec) if "-count-" in c.case_id)
        assert case.expected.type == "result_count"
        assert case.expected.count_target == "검색 결과 목록"

    def test_문구_케이스와_건수_케이스가_따로다(self, search_spec):
        """합치면 FAIL 하나가 두 가지를 뜻한다 — 문구가 틀렸는지 개수가 틀렸는지.
        원인도 고칠 곳도 다르므로 케이스를 나눈다."""
        cases = generate_cases(search_spec)
        text_cases = [c for c in cases if c.expected.type == "text_visible"]
        count_cases = [c for c in cases if c.expected.type == "result_count"]
        assert len(text_cases) == len(count_cases) == 2
        # 같은 입력을 쓰지만 확인하는 것이 다르다
        assert {tuple(s.value for s in c.steps if s.action == "fill")
                for c in text_cases} == \
               {tuple(s.value for s in c.steps if s.action == "fill")
                for c in count_cases}

    def test_건수_0도_케이스를_만든다(self, search_spec):
        """0 은 '건수 검증 없음'(None)이 아니라 '아무것도 나오지 않아야 한다' 다.
        None 으로 뭉개면 결과가 있어도 통과하는 미탐이 된다."""
        counts = [c.expected.count for c in generate_cases(search_spec)
                  if "-count-" in c.case_id]
        assert 0 in counts

    def test_목록_요소가_없으면_건수_케이스를_만들지_않는다(self, search_spec):
        """무엇을 셀지 모르는 상태에서 추측하지 않는다. 대신 spec_defects 가
        기획서 결함으로 알린다 — 조용히 빠뜨리지는 않는다."""
        from prova.s2_case_generator.rule_expander import spec_defects

        spec = search_spec.model_copy(deep=True)
        spec.elements = [e for e in spec.elements if e.type != "list"]

        assert not any("-count-" in c.case_id for c in generate_cases(spec))
        assert any("목록" in d for d in spec_defects(spec))

    def test_목록_요소는_입력_스텝에_들어가지_않는다(self, search_spec):
        """목록은 값을 채우는 대상이 아니다. fill 을 부르면 Playwright 가 조작
        오류를 내고, 그 케이스는 검증하려던 것과 무관하게 실패한다."""
        for case in generate_cases(search_spec):
            targets = [s.target for s in case.steps if s.action in ("fill", "select")]
            assert "검색 결과 목록" not in targets

    def test_로그인은_건수_케이스가_없다(self, login_spec):
        """건수 경로를 추가해도 기존 화면의 케이스 구성이 바뀌지 않아야 한다."""
        assert not any(c.expected.type == "result_count"
                       for c in generate_cases(login_spec))


class TestFlowCases:
    """화면을 이어서 밟는 케이스.

    회원가입 케이스가 전부 통과하고 로그인 케이스도 전부 통과하는데 가입한 계정으로
    로그인이 안 되는 구현이 있을 수 있다. 결함이 화면 안이 아니라 화면 사이에 있으므로
    이어서 밟아 봐야만 드러난다.
    """

    def doc(self, **kw):
        from prova.models import Flow, SpecDocument

        signup = ScreenSpec(
            screen_id="signup", screen_name="회원가입", url_path="/signup",
            elements=[
                UIElement(element_id="email", type="input", label="이메일",
                          required=True, constraints={"format": "email"},
                          sample_value="newuser@test.com"),
                UIElement(element_id="pw", type="input", label="비밀번호",
                          required=True, constraints={"min_length": 8},
                          sample_value="Signup1!"),
                UIElement(element_id="pw2", type="input", label="비밀번호 확인",
                          required=True, constraints={"same_as": "pw"}),
                UIElement(element_id="btn", type="button", label="가입하기"),
            ],
            success_condition='/welcome 으로 이동하고 "가입이 완료되었습니다" 노출',
        )
        login = ScreenSpec(
            screen_id="login", screen_name="로그인", url_path="/login",
            elements=[
                UIElement(element_id="email", type="input", label="이메일",
                          required=True, constraints={"format": "email"},
                          sample_value="user@test.com"),
                UIElement(element_id="pw", type="input", label="비밀번호",
                          required=True, constraints={"min_length": 8},
                          sample_value="Abcd123!"),
                UIElement(element_id="btn", type="button", label="로그인"),
            ],
            success_condition='/dashboard 로 이동하고 "환영합니다" 노출',
        )
        base = dict(
            screens=[signup, login],
            flows=[Flow(flow_id="signup_then_login", screen_ids=["signup", "login"])],
        )
        base.update(kw)
        return SpecDocument(**base)

    def flow_case(self, **kw):
        from prova.s2_case_generator.generator import generate_flow_cases

        cases = generate_flow_cases(self.doc(**kw))
        assert len(cases) == 1
        return cases[0]

    def test_두_화면을_순서대로_밟는다(self):
        case = self.flow_case()
        paths = [s.target for s in case.steps if s.action == "navigate"]
        assert paths == ["/signup", "/login"]

    def test_가입에_쓴_값을_로그인에_다시_넣는다(self):
        """라벨이 같으면 같은 값을 쓴다 — 사람이 손으로 확인할 때 하는 일이다.
        이어지지 않으면 흐름이 확인하는 것이 '가입한 계정으로 로그인되는가' 가
        아니게 되고, 등록되지 않은 계정으로 로그인을 시도해 항상 실패한다."""
        case = self.flow_case()
        emails = [s.value for s in case.steps if s.action == "fill" and s.target == "이메일"]
        assert emails == ["newuser@test.com", "newuser@test.com"], (
            "로그인의 sample_value(user@test.com)가 아니라 가입에 쓴 값을 써야 한다"
        )

    def test_이어받은_값의_의존값도_다시_계산한다(self):
        """비밀번호를 이어받으면 '비밀번호 확인' 도 그 값이어야 한다. dict 를 그대로
        덮으면 일치 규칙이 깨져 흐름이 첫 화면에서부터 실패한다."""
        case = self.flow_case()
        by_label = {s.target: s.value for s in case.steps if s.action == "fill"}
        assert by_label["비밀번호 확인"] == by_label["비밀번호"]

    def test_중간_화면마다_도착을_확인한다(self):
        """이 스텝이 없으면 앞 화면에서 끊겨도 마지막 화면이 지목된다."""
        case = self.flow_case()
        asserts = [s for s in case.steps if s.action == "assert"]
        assert len(asserts) == 1
        assert asserts[0].target == "signup 성공"
        assert asserts[0].expected.url_contains == "/welcome"

    def test_마지막_화면에는_도착_확인을_넣지_않는다(self):
        """마지막은 케이스의 기대(expected)가 확인한다. 스텝으로 또 넣으면 같은
        것을 두 번 보고, 실패가 '스텝 끊김' 으로 기록되어 판정 사유가 흐려진다."""
        case = self.flow_case()
        seqs = [s.seq for s in case.steps]
        assert case.steps[-1].action == "click"
        assert seqs == sorted(seqs)

    def test_기대는_마지막_화면의_성공조건이다(self):
        case = self.flow_case()
        assert case.expected.url_contains == "/dashboard"
        assert case.expected.value == "환영합니다"

    def test_확인_문구가_지정되면_그것을_쓴다(self):
        from prova.models import Flow

        case = self.flow_case(flows=[Flow(
            flow_id="signup_then_login", screen_ids=["signup", "login"],
            expect_text="직접 지정한 문구")])
        assert case.expected.type == "text_visible"
        assert case.expected.value == "직접 지정한 문구"

    def test_흐름_케이스는_positive다(self):
        """규칙을 어긴 값이 아니라 정상 입력이다. negative 로 두면 S5 의 판정이
        뒤집혀 '에러가 떠야 PASS' 가 된다."""
        case = self.flow_case()
        assert case.type == "positive" and case.violates is None

    def test_screen_id는_마지막_화면이다(self):
        """흐름의 목적이 '마지막 화면에 제대로 도달했는가' 이기 때문이다."""
        case = self.flow_case()
        assert case.screen_id == "login"
        assert case.flow_id == "signup_then_login"

    def test_없는_화면을_가리키면_만들지_않는다(self):
        """추측해서 만들면 그 케이스가 무엇을 확인하는지 알 수 없다. 그 사실은
        S1 의 _document_warnings 가 경고로 남긴다."""
        from prova.models import Flow
        from prova.s2_case_generator.generator import generate_flow_cases

        doc = self.doc(flows=[Flow(flow_id="f", screen_ids=["signup", "없는화면"])])
        assert generate_flow_cases(doc) == []

    def test_흐름이_없으면_케이스도_없다(self):
        from prova.s2_case_generator.generator import generate_flow_cases

        assert generate_flow_cases(self.doc(flows=[])) == []


class TestOptionCases:
    """선택 목록이 화면에 다 있는가 — 기획서에 적혀 있는데 아무도 확인하지 않던 것.

    기획서의 '선택 목록: 검색, 지인 추천, 광고' 는 정상 케이스가 넣을 값을 고르는 데만
    쓰였다. 첫 항목을 골라 넣고 그것이 있으면 통과하므로, 화면에 '지인 추천' 이 빠져
    있어도 아무 일도 일어나지 않았다.
    """

    def test_선택_요소마다_케이스가_생긴다(self, signup_spec):
        cases = [c for c in generate_cases(signup_spec) if "-options-" in c.case_id]
        assert len(cases) == 1
        assert cases[0].expected.type == "options_present"
        assert cases[0].expected.options == ["검색", "지인 추천", "광고"]
        assert cases[0].expected.option_target == "가입 경로"

    def test_요소마다_한_건이다(self, signup_spec):
        """선택 요소를 조작하는 케이스마다 대조하면 항목 하나가 빠진 결함이
        회원가입에서 FAIL 14건이 된다. 리포트를 읽는 사람이 규모를 잘못 읽는다."""
        cases = generate_cases(signup_spec)
        option_cases = [c for c in cases if c.expected.type == "options_present"]
        select_count = sum(1 for e in signup_spec.elements
                           if e.type == "select" and e.options)
        assert len(option_cases) == select_count

    def test_스텝은_navigate_하나뿐이다(self, signup_spec):
        """선택 항목은 화면에 들어간 시점에 정해져 있다. 입력하고 제출할 이유가
        없고, 필요 없는 스텝은 실패 지점만 늘린다."""
        case = next(c for c in generate_cases(signup_spec) if "-options-" in c.case_id)
        assert [s.action for s in case.steps] == ["navigate"]
        assert case.steps[0].target == "/signup"

    def test_대상_요소를_남긴다(self, signup_spec):
        case = next(c for c in generate_cases(signup_spec) if "-options-" in c.case_id)
        assert case.target_element == "signup_path"

    def test_선택_요소가_없으면_케이스도_없다(self, login_spec):
        assert not any(c.expected.type == "options_present"
                       for c in generate_cases(login_spec))

    def test_선택_목록이_비면_케이스를_만들지_않는다(self):
        """대조할 정답이 없으면 확인할 것이 없다. 빈 목록을 기대로 두면 무엇을
        확인했는지 알 수 없는 케이스가 늘어난다."""
        spec = minimal_spec(elements=[
            UIElement(element_id="s", type="select", label="선택", required=True),
            UIElement(element_id="btn", type="button", label="확인"),
        ])
        assert not any(c.expected.type == "options_present"
                       for c in generate_cases(spec))


class TestPlaceholderCase:
    """입력 안내 문구 — 기획서가 그 열을 적기 전까지 아무도 확인하지 않던 것.

    안내 문구는 사용자가 가장 먼저 읽는 글자인데, SUT 에는 있고 기획서에는 없었다.
    구현에 있는 UI 문구가 기획서 관할 밖이면 아무도 검증하지 않는다.
    """

    def test_화면당_한_건이다(self, signup_spec):
        """요소마다 만들면 회원가입에서만 4건이 늘어나는데, 각 케이스가 확인하는
        것은 문구 한 줄이다. 리포트에 늘어나는 줄 수가 정보량보다 많다."""
        cases = [c for c in generate_cases(signup_spec)
                 if c.expected.type == "placeholders_match"]
        assert len(cases) == 1

    def test_선언된_문구를_모두_담는다(self, signup_spec):
        case = next(c for c in generate_cases(signup_spec)
                    if c.expected.type == "placeholders_match")
        declared = {e.label: e.placeholder for e in signup_spec.elements if e.placeholder}
        assert case.expected.placeholders == declared
        assert len(declared) >= 3, "회원가입 기획서는 안내 문구를 여럿 적는다"

    def test_스텝은_navigate_하나뿐이다(self, signup_spec):
        """안내 문구는 입력 전에 보이는 글자다. 값을 채우면 오히려 가려진다."""
        case = next(c for c in generate_cases(signup_spec)
                    if c.expected.type == "placeholders_match")
        assert [s.action for s in case.steps] == ["navigate"]

    def test_안내_문구가_없으면_케이스도_없다(self):
        """기획서가 적지 않은 것을 확인한다고 하면 억측이 된다."""
        spec = minimal_spec()
        assert all(e.placeholder is None for e in spec.elements)
        assert not any(c.expected.type == "placeholders_match"
                       for c in generate_cases(spec))
