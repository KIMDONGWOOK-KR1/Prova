"""rule_expander 테스트 — 규칙 하나당 위반값 하나.

이 모듈이 Prova 의 심장이다. 기획서에 적힌 검증 규칙 하나하나를 '그 규칙만
깨뜨린 입력값' 으로 전개해서, 구현이 각 규칙을 실제로 강제하는지 규칙 단위로
확인한다.

가장 중요한 성질: **위반값은 대상 규칙만 깨고 나머지 규칙은 모두 만족해야 한다.**
그러지 않으면 FAIL 이 떴을 때 어느 규칙이 미구현인지 분리되지 않는다.
"""

import pytest

from prova.models import UIElement
from prova.s2_case_generator.rule_expander import (
    Violation,
    satisfies,
    valid_value_for,
    violations_for_element,
)


def elem(**kw) -> UIElement:
    base = dict(element_id="password", type="input", label="비밀번호", required=True,
                constraints={}, error_message="비밀번호 규칙 위반")
    base.update(kw)
    return UIElement(**base)


class TestSatisfies:
    """satisfies 는 '이 값이 이 규칙들을 모두 만족하는가' 를 판정한다.
    위반값 생성이 옳은지 검사하는 기준이 되므로 먼저 못 박는다."""

    def test_비밀번호_규칙_전부_충족(self):
        c = {"min_length": 8, "require_uppercase": 1, "require_special": 1}
        assert satisfies("Abcd123!", c)

    @pytest.mark.parametrize("value,why", [
        ("Abcd12!", "8자 미달"),
        ("abcd123!", "대문자 없음"),
        ("Abcd1234", "특수문자 없음"),
    ])
    def test_하나라도_어기면_불만족(self, value, why):
        c = {"min_length": 8, "require_uppercase": 1, "require_special": 1}
        assert not satisfies(value, c), why

    def test_이메일_형식(self):
        assert satisfies("user@test.com", {"format": "email"})
        assert not satisfies("not-an-email", {"format": "email"})

    def test_최대길이(self):
        assert satisfies("abc", {"max_length": 5})
        assert not satisfies("abcdef", {"max_length": 5})

    def test_정규식(self):
        assert satisfies("010-1234-5678", {"pattern": r"\d{3}-\d{4}-\d{4}"})
        assert not satisfies("01012345678", {"pattern": r"\d{3}-\d{4}-\d{4}"})

    def test_빈_constraints는_항상_만족(self):
        assert satisfies("아무값", {})


class TestValidValueFor:
    def test_모든_규칙을_만족하는_값을_만든다(self):
        c = {"min_length": 12, "require_uppercase": 2, "require_special": 2,
             "require_digit": 1, "require_lowercase": 1}
        v = valid_value_for(elem(constraints=c))
        assert satisfies(v, c), f"생성값 {v!r} 이 규칙을 만족하지 않는다"

    def test_이메일은_이메일_형식으로(self):
        v = valid_value_for(elem(element_id="email", constraints={"format": "email"}))
        assert satisfies(v, {"format": "email"})

    def test_min과_max가_함께_있어도_만족(self):
        c = {"min_length": 6, "max_length": 8}
        v = valid_value_for(elem(constraints=c))
        assert satisfies(v, c), f"생성값 {v!r} 길이 {len(v)}"


class TestViolationsForElement:
    """핵심 계약: 규칙 하나당 위반 하나, 그리고 나머지 규칙은 만족."""

    def test_비밀번호_규칙_3개가_3개의_위반으로_전개된다(self):
        e = elem(constraints={"min_length": 8, "require_uppercase": 1, "require_special": 1})
        vs = violations_for_element(e)
        rules = {v.rule for v in vs}
        assert rules == {"required", "min_length", "require_uppercase", "require_special"}

    def test_각_위반값은_대상_규칙만_깨뜨린다(self):
        """이 테스트가 이 모듈의 존재 이유다.

        명세서 예시는 대문자와 특수문자를 동시에 빠뜨린 값을 썼는데, 그러면
        FAIL 이 떴을 때 어느 규칙이 미구현인지 알 수 없다.
        """
        c = {"min_length": 8, "require_uppercase": 1, "require_special": 1,
             "require_digit": 1, "require_lowercase": 1}
        for v in violations_for_element(elem(constraints=c)):
            if v.rule == "required":
                continue
            assert not satisfies(v.value, {v.rule: c[v.rule]}), \
                f"{v.rule}: 값 {v.value!r} 이 대상 규칙을 위반하지 않는다"
            others = {k: val for k, val in c.items() if k != v.rule}
            assert satisfies(v.value, others), \
                f"{v.rule}: 값 {v.value!r} 이 다른 규칙({others})까지 위반한다"

    def test_required_위반은_빈값(self):
        v = next(v for v in violations_for_element(elem(required=True)) if v.rule == "required")
        assert v.value == ""

    def test_필수가_아니면_required_위반을_만들지_않는다(self):
        vs = violations_for_element(elem(required=False, constraints={"min_length": 8}))
        assert "required" not in {v.rule for v in vs}

    def test_이메일_형식_위반값은_at이_없다(self):
        e = elem(element_id="email", label="이메일", constraints={"format": "email"})
        v = next(v for v in violations_for_element(e) if v.rule == "format")
        assert "@" not in v.value

    def test_버튼처럼_규칙없는_요소는_위반이_없다(self):
        e = UIElement(element_id="login_btn", type="button", label="로그인")
        assert violations_for_element(e) == []

    def test_위반에_사람이_읽을_설명이_붙는다(self):
        """리포트에서 '왜 이 값을 넣었는지' 를 개발자가 알 수 있어야 한다."""
        for v in violations_for_element(elem(constraints={"require_uppercase": 1})):
            assert v.description, f"{v.rule} 에 설명이 없다"
            assert isinstance(v, Violation)
