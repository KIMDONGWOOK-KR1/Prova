"""선택 넓히기 — 모델이 가리킨 곳을 코드가 결정적으로 넓힌다.

## 왜

홀드아웃 A 의 빠뜨림 3건(흐름·건수·정렬)은 모두 같은 모양이었다 — 7B 가 **맞는 곳을
가리키고도 묶음을 대표 하나로 접는다**(count-005 만, valid 둘만). 프롬프트로
"전부 고르라" 고 세 번 말해도 접는다. 그래서 모델에게 더 잘 고르라고 하지 않고,
모델이 가리킨 곳을 코드가 넓힌다. 방향은 넓히기뿐이다 — 이 층의 안전 방향("더
많이 검사하는 쪽") 그대로다.

## 계약

- 순수 함수. 넓힌 결과는 여전히 원본의 부분집합이다.
- 빈 입력엔 아무것도 더하지 않는다 (0건 거부 계약은 그대로).
- 넓힌 케이스마다 (case_id, 규칙) 이 남는다 — 모델이 고른 것과 코드가 더한 것을
  리포트에서 구분할 수 있어야 "해석이 맞았는가" 를 되짚을 수 있다.
"""

from __future__ import annotations

from prova.models import Flow, SpecDocument, TestCase
from prova.s2_case_generator.selector import widen_selection


def tc(case_id: str, screen: str, flow: str | None = None, violates: str | None = None) -> TestCase:
    return TestCase(case_id=case_id, title=case_id, type="positive", screen_id=screen,
                    flow_id=flow, violates=violates, steps=[],
                    expected={"type": "error_shown"})


MULTI = [
    tc("login-valid-001", "login"),
    tc("login-email-required-002", "login", violates="required"),
    tc("login-placeholders-001", "login"),
    tc("login-labels-001", "login"),
    tc("signup-valid-001", "signup"),
    tc("signup-email-format-003", "signup", violates="format"),
    tc("signup-options-signup_path-015", "signup"),
    tc("search-valid-001", "search"),
    tc("search-scenario-005", "search"),
    tc("search-count-005", "search"),
    tc("search-scenario-006", "search"),
    tc("search-count-006", "search"),
    tc("flow-signup_link_to_login-001", "login", flow="signup_link_to_login"),
    tc("flow-signup_then_login-001", "login", flow="signup_then_login"),
]
ORDERS = [
    tc("login-valid-001", "login"),
    tc("orders-valid-001", "orders"),
    tc("orders-sorted-002", "orders"),
    tc("orders-sum-003", "orders"),
    tc("orders-seedcount-004", "orders"),
    tc("orders-precondition-guard-005", "orders"),
]
DOC = SpecDocument(screens=[], flows=[
    Flow(flow_id="signup_link_to_login", screen_ids=["signup", "login"]),
    Flow(flow_id="signup_then_login", screen_ids=["signup", "login"]),
])


def ids(cases):
    return [c.case_id for c in cases]


class TestR1묶음완성:
    def test_건수_하나를_고르면_같은_화면의_건수_전부(self):
        picked, added = widen_selection(MULTI, ["search-count-005"], "상품 검색 결과 개수가 맞게 나오는지")
        assert "search-count-006" in ids(picked)
        assert ("search-count-006", "R1") in added

    def test_다른_화면의_같은_종류는_더하지_않는다(self):
        cases = MULTI + [tc("orders-count-001", "orders")]
        picked, added = widen_selection(cases, ["search-count-005"], "검색")
        assert "orders-count-001" not in ids(picked)

    def test_규칙_위반_케이스는_묶음이_아니다(self):
        """'이메일 형식만' 을 골랐을 때 required 까지 더하면 범위 지목을 무시하는 것이다."""
        picked, added = widen_selection(MULTI, ["signup-email-format-003"], "이메일 형식")
        assert ids(picked) == ["signup-email-format-003"]
        assert added == []


class TestR2흐름보강:
    def test_두_화면의_정상을_함께_고르면_그_흐름을_더한다(self):
        picked, added = widen_selection(
            MULTI, ["signup-valid-001", "login-valid-001"], "회원가입 마치고 그 계정으로 바로 로그인까지 되는지")
        assert "flow-signup_then_login-001" in ids(picked)
        assert ("flow-signup_then_login-001", "R2") in added

    def test_한_화면만_골랐으면_흐름을_더하지_않는다(self):
        picked, added = widen_selection(MULTI, ["signup-valid-001"], "가입")
        assert not any(c.flow_id for c in picked)


class TestR3종류낱말:
    def test_정렬_낱말이_있으면_고른_화면의_정렬_케이스를_더한다(self):
        picked, added = widen_selection(ORDERS, ["orders-valid-001"], "주문 내역이 최신순으로 나오는지 확인해줘")
        assert "orders-sorted-002" in ids(picked)
        assert ("orders-sorted-002", "R3") in added

    def test_낱말이_있어도_그_화면을_고르지_않았으면_더하지_않는다(self):
        picked, added = widen_selection(ORDERS, ["login-valid-001"], "최신순")
        assert "orders-sorted-002" not in ids(picked)

    def test_문구_낱말은_placeholders_와_labels_둘_다(self):
        picked, _ = widen_selection(MULTI, ["login-valid-001"], "로그인 쪽 안내 문구랑 라벨이 기획서랑 같은지")
        assert {"login-placeholders-001", "login-labels-001"} <= set(ids(picked))

    def test_낱말이_없으면_아무것도_더하지_않는다(self):
        picked, added = widen_selection(ORDERS, ["orders-valid-001"], "주문조회 들어가지는지")
        assert ids(picked) == ["orders-valid-001"] and added == []


class TestContract:
    def test_부분집합이다(self):
        picked, _ = widen_selection(MULTI, ["search-count-005", "signup-valid-001", "login-valid-001"], "전부 정렬 합계 문구")
        assert set(ids(picked)) <= set(ids(MULTI))

    def test_빈_입력엔_아무것도_더하지_않는다(self):
        picked, added = widen_selection(MULTI, [], "최신순 전부")
        assert picked == [] and added == []

    def test_생성_순서를_유지한다(self):
        picked, _ = widen_selection(MULTI, ["search-count-006"], "개수")
        assert ids(picked) == ["search-count-005", "search-count-006"]

    def test_이미_고른_것은_다시_더하지_않는다(self):
        _, added = widen_selection(MULTI, ["search-count-005", "search-count-006"], "개수")
        assert added == []
