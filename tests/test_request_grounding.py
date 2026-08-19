"""요청이 기획서 안의 것을 가리키는지 먼저 확인한다.

## 왜 이 검사가 필요한가

실모델 측정에서 뚫려 있는 것이 드러났다 (`scripts/probe_request_selection.py`).

    "결제 화면 확인해줘"   -> login-placeholders-001, login-labels-001, login-scenario-008
    "장바구니 담기가 되는지" -> (같은 3건)

**기획서에 결제 화면이 없는데 로그인 케이스를 골랐다.** 리포트에는 이렇게 남는다 —
"요청 '결제 화면 확인해줘' → 3건 실행, 통과율 100%". 결제 화면을 확인한 적이 없는데
초록불이다.

기존 안전장치 넷 중 어느 것도 이걸 막지 못한다. 부분집합이고(2), 0건이 아니고(4),
해석도 '성공' 했다(3). 모델은 빈 목록을 주지 않고 무엇이든 집어 온다.

## 그래서 모델에게 묻기 전에 코드가 먼저 본다

요청이 기획서의 어휘와 하나도 겹치지 않으면 거부한다. 이건 LLM 판단이 아니라
문자열 대조라 결정적이고, 모델이 아무거나 집는 상황 자체를 만들지 않는다.

## 거부가 통과보다 안전한 방향인가

여기서는 그렇다. 잘못 거부하면 **사람이 즉시 안다** — 화면에 "이 기획서는 로그인
화면을 다룹니다" 가 뜨고, 다시 쓰거나 요청을 비우면 전체가 돈다. 잘못 통과하면
**아무도 모른다** — 엉뚱한 3건이 돌고 통과율만 남는다.
"""

import pytest

from prova.llm.mock_backend import MockLLM
from prova.models import (
    Expectation,
    ScreenSpec,
    SpecDocument,
    TestCase,
    TestStep,
    UIElement,
)
from prova.s2_case_generator.selector import select_cases


def case(case_id: str, title: str, screen: str = "login") -> TestCase:
    return TestCase(
        case_id=case_id,
        screen_id=screen,
        title=title,
        type="negative",
        steps=[TestStep(seq=1, action="navigate", target=f"/{screen}")],
        expected=Expectation(type="error_shown"),
    )


@pytest.fixture
def cases() -> list[TestCase]:
    return [
        case("login-valid-001", "정상 로그인 (모든 입력 규칙 충족)"),
        case("login-email-format-003", "이메일 형식 규칙 위반"),
        case("login-password-min_length-005", "비밀번호 최소 길이 규칙 위반"),
        case("login-labels-001", "기획서의 라벨로 요소를 찾을 수 있는지 확인"),
    ]


@pytest.fixture
def doc() -> SpecDocument:
    return SpecDocument(screens=[ScreenSpec(
        screen_id="login",
        screen_name="로그인",
        url_path="/login",
        elements=[
            UIElement(element_id="email", type="input", label="이메일"),
            UIElement(element_id="password", type="input", label="비밀번호"),
        ],
    )])


def llm_picking(case_ids) -> MockLLM:
    llm = MockLLM()
    llm.register("CaseSelection", {"case_ids": list(case_ids), "reason": "테스트"})
    return llm


class TestGrounded:
    """기획서의 말을 쓴 요청은 그대로 모델에게 넘어간다."""

    def test_요소_이름을_쓰면_통과한다(self, cases, doc):
        picked, _ = select_cases(
            cases, "비밀번호 규칙만 봐줘", llm_picking(["login-password-min_length-005"]), doc=doc)
        assert [c.case_id for c in picked] == ["login-password-min_length-005"]

    def test_화면_이름을_쓰면_통과한다(self, cases, doc):
        picked, _ = select_cases(
            cases, "로그인이 되는지 봐줘", llm_picking(["login-valid-001"]), doc=doc)
        assert picked

    def test_조사가_붙어도_인식한다(self, cases, doc):
        """'로그인되는지', '회원가입이' 처럼 조사·어미가 붙어 온다."""
        for text in ("로그인되는지 확인해줘", "이메일을 제대로 검사하는지",
                     "비밀번호가 규칙대로 걸리는지"):
            picked, _ = select_cases(cases, text, llm_picking(["login-valid-001"]), doc=doc)
            assert picked, text

    def test_영어_규칙_이름도_인식한다(self, cases, doc):
        picked, _ = select_cases(
            cases, "min_length 만 봐줘", llm_picking(["login-password-min_length-005"]), doc=doc)
        assert picked

    def test_전체를_뜻하는_말은_어휘가_없어도_통과한다(self, cases, doc):
        """'전부 다 확인해줘' 에는 기획서의 말이 하나도 없지만 뜻은 명확하다."""
        for text in ("전부 다 확인해줘", "모두 확인", "전체 다"):
            picked, _ = select_cases(
                cases, text, llm_picking([c.case_id for c in cases]), doc=doc)
            assert len(picked) == len(cases), text


class TestUngrounded:
    """기획서에 없는 것을 요청하면 모델에게 묻지 않고 거부한다."""

    def test_없는_화면을_요청하면_거부한다(self, cases, doc):
        with pytest.raises(ValueError) as exc:
            select_cases(cases, "결제 화면 확인해줘", llm_picking(["login-labels-001"]), doc=doc)
        assert "결제 화면 확인해줘" in str(exc.value)

    def test_모델을_부르지_않는다(self, cases, doc):
        """모델에게 물으면 무엇이든 집어 온다. 그 상황 자체를 만들지 않는다."""
        llm = llm_picking(["login-labels-001"])
        with pytest.raises(ValueError):
            select_cases(cases, "장바구니 담기가 되는지 봐줘", llm, doc=doc)
        assert llm.calls == [], "거부해야 할 요청으로 모델을 불렀다"

    def test_거부_메시지가_다루는_화면을_알려준다(self, cases, doc):
        """다시 쓸 수 있어야 한다. 무엇이 되는지 모르면 거부가 막다른 길이 된다."""
        with pytest.raises(ValueError) as exc:
            select_cases(cases, "결제 확인", llm_picking([]), doc=doc)
        msg = str(exc.value)
        assert "로그인" in msg
        assert "이메일" in msg or "비밀번호" in msg

    def test_거부_메시지가_빠져나갈_길을_알려준다(self, cases, doc):
        with pytest.raises(ValueError) as exc:
            select_cases(cases, "결제 확인", llm_picking([]), doc=doc)
        assert "비우면" in str(exc.value)


class TestNoDocument:
    """doc 없이도 계약이 깨지지 않는다 (단위 테스트·옛 호출부)."""

    def test_doc_이_없으면_케이스에서_어휘를_만든다(self, cases):
        picked, _ = select_cases(
            cases, "이메일 형식 확인", llm_picking(["login-email-format-003"]))
        assert picked

    def test_doc_이_없어도_없는_화면은_거부한다(self, cases):
        with pytest.raises(ValueError):
            select_cases(cases, "결제 화면 확인해줘", llm_picking(["login-labels-001"]))


class TestUnchanged:
    """기존 계약 넷은 그대로다."""

    def test_요청이_없으면_전부_실행한다(self, cases, doc):
        picked, sel = select_cases(cases, None, llm_picking([]), doc=doc)
        assert picked == cases and sel.request == ""

    def test_LLM_이_없으면_전체를_실행한다(self, cases, doc):
        """어휘 검사를 통과한 뒤 모델이 없으면, 여전히 '더 많이' 쪽으로 넘어진다."""
        picked, sel = select_cases(cases, "비밀번호 규칙만", None, doc=doc)
        assert picked == cases and sel.fallback is True


class TestSplitStopwords:
    """낱말 쪼개기가 만드는 일반어 조각이 검사를 무력화하지 않는다.

    홀드아웃 측정에서 "고객센터 문의가 접수되는지 확인" 이 통과했다 — 라벨
    '비밀번호 확인' 을 쪼갠 '확인' 이 매치된 것이다. '확인' 은 거의 모든 요청에
    들어가므로, 이 한 조각이 검사 전체를 사실상 꺼 버린다.
    """

    @pytest.fixture
    def confirm_doc(self) -> SpecDocument:
        return SpecDocument(screens=[ScreenSpec(
            screen_id="signup", screen_name="회원가입", url_path="/signup",
            elements=[
                UIElement(element_id="password", type="input", label="비밀번호"),
                UIElement(element_id="password_confirm", type="input", label="비밀번호 확인"),
            ],
        )])

    @pytest.fixture
    def signup_cases(self) -> list[TestCase]:
        return [case("signup-valid-001", "정상 회원가입", "signup"),
                case("signup-password_confirm-same_as-009", "비밀번호 일치 확인", "signup")]

    def test_일반어_조각만으로는_통과하지_못한다(self, signup_cases, confirm_doc):
        """'확인' 은 '비밀번호 확인' 의 조각이지만, 그것만 겹치는 요청은 이 기획서와
        무관하다."""
        with pytest.raises(ValueError):
            select_cases(signup_cases, "고객센터 문의가 접수되는지 확인",
                         llm_picking(["signup-valid-001"]), doc=confirm_doc)

    def test_온전한_이름은_그대로_통과한다(self, signup_cases, confirm_doc):
        """거르는 것은 쪼개진 조각뿐이다. '비밀번호 확인' 전체는 어휘에 남는다."""
        picked, _ = select_cases(
            signup_cases, "비밀번호 확인란이 제대로 동작하는지",
            llm_picking(["signup-password_confirm-same_as-009"]), doc=confirm_doc)
        assert picked

    def test_내용어_조각은_여전히_통과한다(self, signup_cases, confirm_doc):
        """'비밀번호' 는 내용어라 조각으로도 유효하다."""
        picked, _ = select_cases(
            signup_cases, "비밀번호가 일치하는지 봐줘",
            llm_picking(["signup-password_confirm-same_as-009"]), doc=confirm_doc)
        assert picked
