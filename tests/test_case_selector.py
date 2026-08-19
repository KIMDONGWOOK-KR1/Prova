"""자연어 요청 -> 케이스 선택 테스트.

이 층은 **미탐을 만들 수 있는 유일한 경로**다. 지금까지 케이스 선택에 LLM 이
관여하지 않았기 때문에 "리포트에 없는 결함은 없는 결함" 이 성립했다. 요청 해석이
케이스를 고르기 시작하면 그 보장이 깨진다 — 모델이 케이스를 잘못 골라서 결함을
못 본 것과 결함이 정말 없는 것이 리포트에서 같아 보인다.

그래서 이 모듈의 계약은 세 가지다.

1. **부분집합** — 고른 결과는 항상 원본 케이스의 부분집합이다. 모델이 없는
   case_id 를 지어내도 케이스가 생기지 않는다.
2. **빈 선택 거부** — 아무것도 못 고르면 예외다. `filter_cases` 와 같은 이유로,
   0건 실행은 "통과율 100%" 리포트가 된다.
3. **실패는 더 많이 검사하는 쪽으로 넘어진다** — LLM 이 죽으면 전체를 실행한다.
   적게 고르면 결함이 숨지만 많이 고르면 숨지 않는다. 방향이 한쪽뿐이다.
"""

import pytest

from prova.llm.base import LLMError
from prova.llm.mock_backend import MockLLM
from prova.models import (
    Expectation,
    ScreenSpec,
    SpecDocument,
    TestCase,
    TestStep,
    UIElement,
)
from prova.s2_case_generator.selector import select_by_ids, select_cases

# 이 파일은 선택 '동작' 을 다룬다. 요청이 기획서 안의 것을 가리키는지 보는 어휘
# 검사는 test_request_grounding.py 가 맡으므로, 여기서는 실제 기획서를 물려 주어
# 그 관문을 통과시킨 뒤의 동작만 본다.
DOC = SpecDocument(screens=[
    ScreenSpec(screen_id="login", screen_name="로그인", url_path="/login", elements=[
        UIElement(element_id="email", type="input", label="이메일"),
        UIElement(element_id="password", type="input", label="비밀번호"),
    ]),
    ScreenSpec(screen_id="signup", screen_name="회원가입", url_path="/signup"),
])


def select(cases, request, llm):
    return select_cases(cases, request, llm, doc=DOC)

ALL_IDS = [
    "login-valid-001",
    "login-email-format-003",
    "login-password-min_length-005",
    "signup-password-same_as-002",
]


def case(case_id: str) -> TestCase:
    screen = case_id.split("-")[0]
    return TestCase(
        case_id=case_id,
        screen_id=screen,
        title=case_id,
        type="negative",
        steps=[TestStep(seq=1, action="navigate", target=f"/{screen}")],
        expected=Expectation(type="error_shown"),
    )


@pytest.fixture
def cases() -> list[TestCase]:
    return [case(cid) for cid in ALL_IDS]


def llm_returning(case_ids, reason="테스트용 근거") -> MockLLM:
    llm = MockLLM()
    llm.register("CaseSelection", {"case_ids": list(case_ids), "reason": reason})
    return llm


class TestNoRequest:
    def test_요청이_없으면_전부_실행한다(self, cases):
        """요청이 없으면 해석할 것도 없다. 기존 CLI 동작과 같아야 한다."""
        picked, sel = select(cases, None, llm_returning([]))
        assert picked == cases
        assert sel.selected == ALL_IDS
        assert sel.excluded == []

    def test_빈_문자열도_전부_실행한다(self, cases):
        picked, _ = select(cases, "   ", llm_returning([]))
        assert picked == cases

    def test_요청이_없으면_LLM_을_부르지_않는다(self, cases):
        llm = llm_returning([])
        select(cases, None, llm)
        assert llm.calls == []


class TestSelection:
    def test_모델이_고른_케이스만_남는다(self, cases):
        picked, sel = select(
            cases, "비밀번호 규칙만 봐줘", llm_returning(["login-password-min_length-005"])
        )
        assert [c.case_id for c in picked] == ["login-password-min_length-005"]
        assert sel.selected == ["login-password-min_length-005"]

    def test_제외된_케이스를_기록한다(self, cases):
        """무엇을 안 봤는지가 리포트에 남아야 '검사했는데 통과' 와
        '아예 안 봤다' 가 구분된다."""
        _, sel = select(cases, "로그인만", llm_returning(["login-valid-001"]))
        assert sel.excluded == [
            "login-email-format-003",
            "login-password-min_length-005",
            "signup-password-same_as-002",
        ]

    def test_모델의_근거를_보존한다(self, cases):
        _, sel = select(
            cases, "로그인만", llm_returning(["login-valid-001"], reason="로그인 화면 케이스만 골랐습니다")
        )
        assert sel.reason == "로그인 화면 케이스만 골랐습니다"
        assert sel.request == "로그인만"

    def test_원본_순서를_유지한다(self, cases):
        """모델이 뒤섞어 돌려줘도 실행 순서는 생성 순서를 따른다 —
        흐름 케이스는 순서에 의미가 있다."""
        picked, _ = select(
            cases, "로그인과 회원가입 둘 다", llm_returning(["signup-password-same_as-002", "login-valid-001"])
        )
        assert [c.case_id for c in picked] == ["login-valid-001", "signup-password-same_as-002"]

    def test_중복을_준_경우_한_번만_실행한다(self, cases):
        picked, _ = select(
            cases, "로그인", llm_returning(["login-valid-001", "login-valid-001"])
        )
        assert len(picked) == 1


class TestSubsetGuarantee:
    def test_없는_case_id_는_무시한다(self, cases):
        """모델이 지어낸 id 로 케이스가 생기면 안 된다. 실행되지 않은 케이스가
        리포트에 나타나는 것은 판정을 통째로 거짓으로 만든다."""
        picked, sel = select(
            cases, "로그인 케이스 아무거나", llm_returning(["login-valid-001", "존재하지-않는-케이스"])
        )
        assert [c.case_id for c in picked] == ["login-valid-001"]
        assert any("존재하지-않는-케이스" in w for w in sel.warnings)

    def test_결과는_항상_원본의_부분집합이다(self, cases):
        picked, _ = select(cases, "전부", llm_returning(ALL_IDS + ["지어낸-것"]))
        assert set(c.case_id for c in picked) <= set(ALL_IDS)

    def test_원본_목록을_변경하지_않는다(self, cases):
        before = list(cases)
        select(cases, "로그인", llm_returning(["login-valid-001"]))
        assert cases == before


class TestEmptySelection:
    def test_아무것도_못_고르면_예외를_던진다(self, cases):
        """0건 실행은 '전체 0건, 통과율 100%' 리포트가 된다 — 아무것도
        검증하지 않았는데 초록불이 되는 가장 위험한 결과다."""
        with pytest.raises(ValueError) as exc:
            select(cases, "로그인 확인해줘", llm_returning([]))
        assert "로그인 확인해줘" in str(exc.value)

    def test_지어낸_id_만_돌려줘도_예외다(self, cases):
        with pytest.raises(ValueError):
            select(cases, "로그인 확인", llm_returning(["없는-것-1", "없는-것-2"]))

    def test_에러에_실행_가능한_케이스를_알려준다(self, cases):
        with pytest.raises(ValueError) as exc:
            select(cases, "로그인", llm_returning([]))
        message = str(exc.value)
        for cid in ALL_IDS:
            assert cid in message


class TestFallbackDirection:
    def test_LLM_이_실패하면_전체를_실행한다(self, cases):
        """적게 고르면 결함이 숨고 많이 고르면 숨지 않는다. 방향이 한쪽뿐이므로
        해석 실패는 반드시 '더 많이' 쪽으로 넘어져야 한다."""
        picked, sel = select(cases, "로그인만", MockLLM())  # 응답 미등록 -> LLMError
        assert picked == cases
        assert sel.fallback is True

    def test_실패_사실을_경고로_남긴다(self, cases):
        _, sel = select(cases, "로그인만", MockLLM())
        assert sel.warnings
        assert sel.selected == ALL_IDS
        assert sel.excluded == []

    def test_llm_이_None_이면_전체를_실행한다(self, cases):
        """백엔드가 없는데 요청만 들어온 경우. 조용히 일부만 도는 것보다
        전체를 돌고 그 사실을 남기는 편이 안전하다."""
        picked, sel = select(cases, "로그인만", None)
        assert picked == cases
        assert sel.fallback is True


class TestSelectByIds:
    """사람이 승인한 목록으로 좁히는 경로 (UI 의 계획 확인 단계).

    `select_cases` 와 계약이 같아야 한다 — 계약이 갈리면 UI 로 돌린 실행과 CLI 로
    돌린 실행의 안전성이 달라진다.
    """

    def test_승인한_것만_실행한다(self, cases):
        picked, sel = select_by_ids(cases, ["login-valid-001"], request="로그인만")
        assert [c.case_id for c in picked] == ["login-valid-001"]
        assert sel.request == "로그인만"

    def test_모델을_부르지_않는다(self, cases):
        """계획 화면에서 이미 해석을 마쳤다. 실행 시점에 다시 물으면 사람이
        승인한 것과 다른 것이 돌 수 있다."""
        # llm 인자를 받지 않는다는 사실 자체가 계약이다.
        picked, _ = select_by_ids(cases, ALL_IDS)
        assert len(picked) == len(ALL_IDS)

    def test_없는_id_는_무시하고_경고를_남긴다(self, cases):
        picked, sel = select_by_ids(cases, ["login-valid-001", "사라진-케이스"])
        assert [c.case_id for c in picked] == ["login-valid-001"]
        assert any("사라진-케이스" in w for w in sel.warnings)

    def test_원본_순서를_유지한다(self, cases):
        picked, _ = select_by_ids(cases, ["signup-password-same_as-002", "login-valid-001"])
        assert [c.case_id for c in picked] == ["login-valid-001", "signup-password-same_as-002"]

    def test_제외된_것을_기록한다(self, cases):
        _, sel = select_by_ids(cases, ["login-valid-001"])
        assert len(sel.excluded) == len(ALL_IDS) - 1

    def test_빈_목록이면_예외다(self, cases):
        with pytest.raises(ValueError):
            select_by_ids(cases, [])

    def test_전부_없는_id_면_예외다(self, cases):
        with pytest.raises(ValueError) as exc:
            select_by_ids(cases, ["없는-것"])
        assert "없는-것" in str(exc.value)


class TestWhoChose:
    """모델이 고른 것과 사람이 승인한 것을 구분한다.

    사람의 선택을 모델이 한 것처럼 리포트에 적으면, 도구가 한 판단을 감추는 것과
    반대 방향의 같은 부정확이다. 리포트는 누가 무엇을 정했는지를 틀리게 쓰면 안 된다.
    """

    def test_모델이_고르면_승인_표시가_없다(self, cases):
        _, sel = select(cases, "로그인만", llm_returning(["login-valid-001"]))
        assert sel.approved is False

    def test_사람이_승인하면_표시가_남는다(self, cases):
        _, sel = select_by_ids(cases, ["login-valid-001"], request="로그인만")
        assert sel.approved is True

    def test_해석_실패_전체_실행은_승인이_아니다(self, cases):
        _, sel = select(cases, "로그인만", None)
        assert sel.approved is False
        assert sel.fallback is True


class TestIdTranscription:
    """모델이 case_id 를 옮겨 적다 틀리는 경우.

    실모델 측정에서 나왔다. 7B 는 "비밀번호 확인란이 제대로 동작하는지" 에 대해
    **올바른 케이스 6건을 골랐는데** id 를 이렇게 썼다.

        signup-password_required-004        실제: signup-password-required-004
        signup-password_confirm_same_as-009 실제: signup-password_confirm-same_as-009

    case_id 가 '-' 와 '_' 를 섞어 쓰기 때문이다(요소 id 와 규칙 이름에 '_' 가
    들어간다). 6건 전부 무효가 되어 0건 거부로 떨어졌다 — **판단은 맞았는데
    옮겨적기 실패가 그 판단을 통째로 날렸다.**

    구분자만 다르고 **유일하게 대응되는** 케이스가 있으면 그것으로 읽는다.
    유일하지 않으면 읽지 않는다 — 엉뚱한 케이스로 이어지면 그게 더 나쁘다.
    """

    def test_구분자만_다르면_고쳐_읽는다(self, cases):
        picked, sel = select(
            cases, "로그인 확인", llm_returning(["login_valid_001"]))
        assert [c.case_id for c in picked] == ["login-valid-001"]

    def test_고쳐_읽은_사실을_남긴다(self, cases):
        """도구가 판단을 했으면 그 사실이 리포트에 있어야 한다."""
        _, sel = select(cases, "로그인 확인", llm_returning(["login_valid_001"]))
        assert any("login_valid_001" in w and "login-valid-001" in w
                   for w in sel.warnings)

    def test_대소문자와_공백도_넘어간다(self, cases):
        picked, _ = select(
            cases, "로그인 확인", llm_returning([" LOGIN-VALID-001 "]))
        assert [c.case_id for c in picked] == ["login-valid-001"]

    def test_존재하지_않는_것은_여전히_무시한다(self, cases):
        """고쳐 읽기가 없던 케이스를 만들어내면 안 된다."""
        with pytest.raises(ValueError):
            select(cases, "로그인 확인", llm_returning(["signup_없는_케이스_999"]))

    def test_원본_id_는_그대로_통과한다(self, cases):
        picked, sel = select(cases, "로그인 확인", llm_returning(["login-valid-001"]))
        assert [c.case_id for c in picked] == ["login-valid-001"]
        assert sel.warnings == []
