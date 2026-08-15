"""케이스 필터(`--only`) 테스트.

이 필터는 편의 기능이지만 **가장 위험한 리포트를 만들 수 있는 경로**다. 아무 케이스도
고르지 못한 상태로 진행하면 "전체 0건, 통과 0건, 통과율 100%" 라는 리포트가 나오는데,
그건 아무것도 검증하지 않은 상태다. 그래서 빈 결과를 조용히 넘기지 않는지 못 박는다.
"""

import pytest

from prova.models import Expectation, TestCase, TestStep
from prova.pipeline import filter_cases


def case(case_id: str) -> TestCase:
    return TestCase(
        case_id=case_id,
        screen_id="login",
        title=case_id,
        type="negative",
        steps=[TestStep(seq=1, action="navigate", target="/login")],
        expected=Expectation(type="error_shown"),
    )


@pytest.fixture
def cases() -> list[TestCase]:
    return [
        case("login-valid-001"),
        case("login-email-format-003"),
        case("login-password-require_uppercase-006"),
        case("login-password-require_special-007"),
    ]


class TestFilterCases:
    def test_패턴이_없으면_전부_반환한다(self, cases):
        assert filter_cases(cases, None) == cases
        assert filter_cases(cases, "") == cases

    def test_부분_문자열로_고른다(self, cases):
        picked = filter_cases(cases, "require_uppercase")
        assert [c.case_id for c in picked] == ["login-password-require_uppercase-006"]

    def test_여러_개가_걸리면_모두_반환한다(self, cases):
        picked = filter_cases(cases, "password")
        assert len(picked) == 2

    def test_아무것도_못_고르면_예외를_던진다(self, cases):
        """빈 목록으로 진행하면 '0건 실행, 통과율 100%' 리포트가 나온다 —
        아무것도 검증하지 않았는데 초록불이 되는 가장 위험한 결과다."""
        with pytest.raises(ValueError) as exc:
            filter_cases(cases, "존재하지않는패턴")
        assert "존재하지않는패턴" in str(exc.value)

    def test_에러에_실행_가능한_케이스를_알려준다(self, cases):
        """오타를 냈을 때 무엇을 쓸 수 있는지 바로 알 수 있어야 한다."""
        with pytest.raises(ValueError) as exc:
            filter_cases(cases, "오타")
        message = str(exc.value)
        for c in cases:
            assert c.case_id in message

    def test_원본_목록을_변경하지_않는다(self, cases):
        before = list(cases)
        filter_cases(cases, "password")
        assert cases == before
