"""rule_expander 테스트 — 규칙 하나당 위반값 하나.

이 모듈이 Prova 의 심장이다. 기획서에 적힌 검증 규칙 하나하나를 '그 규칙만
깨뜨린 입력값' 으로 전개해서, 구현이 각 규칙을 실제로 강제하는지 규칙 단위로
확인한다.

가장 중요한 성질: **위반값은 대상 규칙만 깨고 나머지 규칙은 모두 만족해야 한다.**
그러지 않으면 FAIL 이 떴을 때 어느 규칙이 미구현인지 분리되지 않는다.
"""

import pytest

from prova.models import ScreenSpec, UIElement
from prova.s2_case_generator.rule_expander import (
    CHECKED,
    Violation,
    resolve_values,
    satisfies,
    spec_defects,
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


class TestNonTextElements:
    """체크박스·선택 요소 — 사용자가 문자를 직접 입력하지 않는 요소.

    이 요소들에 문자 규칙을 전개하면 '8자 미달인 체크 상태' 같은 만들 수 없는
    입력이 나오고, 실행이 조작 오류로 실패해 판정이 뭉개진다. 검증할 수 있는
    것은 '체크/선택하지 않았을 때' 뿐이다.
    """

    def test_체크박스의_정상값은_체크된_상태다(self):
        e = UIElement(element_id="agree", type="checkbox", label="약관 동의", required=True)
        assert valid_value_for(e) == CHECKED

    def test_체크박스는_required_위반만_만든다(self):
        e = UIElement(element_id="agree", type="checkbox", label="약관 동의",
                      required=True, constraints={"min_length": 3})
        assert [v.rule for v in violations_for_element(e)] == ["required"]

    def test_선택요소의_정상값은_첫_선택지다(self):
        e = UIElement(element_id="path", type="select", label="가입 경로",
                      required=True, options=["검색", "광고"])
        assert valid_value_for(e) == "검색"

    def test_선택지가_없으면_빈값이_되고_기획서_결함으로_경고된다(self):
        spec = ScreenSpec(
            screen_id="s", screen_name="화면", url_path="/s",
            elements=[UIElement(element_id="path", type="select", label="가입 경로",
                                required=True)],
        )
        assert valid_value_for(spec.elements[0]) == ""
        assert any("선택 목록" in d for d in spec_defects(spec))

    def test_필수_아닌_체크박스는_위반이_없다(self):
        e = UIElement(element_id="news", type="checkbox", label="뉴스레터 수신")
        assert violations_for_element(e) == []


class TestSameAs:
    """교차 필드 규칙 — 값 하나만 보고는 판정할 수 없는 유일한 규칙."""

    @staticmethod
    def pair(**confirm_kw) -> list[UIElement]:
        base = dict(element_id="pw_confirm", type="input", label="비밀번호 확인",
                    required=True, constraints={"same_as": "pw"},
                    error_message="비밀번호가 일치하지 않습니다.")
        base.update(confirm_kw)
        return [
            UIElement(element_id="pw", type="input", label="비밀번호", required=True,
                      constraints={"min_length": 8, "require_uppercase": 1,
                                   "require_special": 1},
                      sample_value="Signup1!"),
            UIElement(**base),
        ]

    def test_정상값은_참조_요소의_값과_같다(self):
        values, warnings = resolve_values(self.pair())
        assert values["pw_confirm"] == values["pw"] == "Signup1!"
        assert warnings == []

    def test_위반값은_참조값과_다르다(self):
        values, _ = resolve_values(self.pair())
        v = next(v for v in violations_for_element(self.pair()[1], values["pw"])
                 if v.rule == "same_as")
        assert v.value != values["pw"]

    def test_참조값을_모르면_위반값을_만들지_않는다(self):
        """'무엇과 다른 값' 인지 정할 수 없다. 아무 값이나 넣으면 우연히 참조값과
        같아져서, 구현에 일치 검증이 없어도 PASS 가 나올 수 있다(미탐)."""
        rules = {v.rule for v in violations_for_element(self.pair()[1], None)}
        assert "same_as" not in rules

    def test_참조_요소에_위반값이_들어가면_의존값도_함께_바뀐다(self):
        """이것이 '한 케이스는 한 규칙만 위반한다' 계약을 지키는 지점이다.
        비밀번호에 위반값을 넣고 확인값을 원래대로 두면 두 규칙이 함께 깨진다."""
        values, _ = resolve_values(self.pair(), overrides={"pw": "a1!aaaaa"})
        assert values["pw"] == values["pw_confirm"] == "a1!aaaaa"

    def test_없는_요소를_가리키면_기획서_결함으로_경고한다(self):
        elements = self.pair()
        elements[1].constraints = {"same_as": "존재하지않음"}
        _, warnings = resolve_values(elements)
        assert any("존재하지않음" in w for w in warnings)

    def test_서로를_가리키면_순환으로_경고한다(self):
        elements = [
            UIElement(element_id="a", type="input", label="A", constraints={"same_as": "b"}),
            UIElement(element_id="b", type="input", label="B", constraints={"same_as": "a"}),
        ]
        _, warnings = resolve_values(elements)
        assert any("순환" in w for w in warnings)

    def test_예시값이_참조값과_다르면_기획서_결함으로_경고한다(self):
        spec = ScreenSpec(
            screen_id="s", screen_name="화면", url_path="/s",
            elements=self.pair(sample_value="다른값1!"),
        )
        assert any("예시값" in d for d in spec_defects(spec))


class TestMinLengthWithoutCharRules:
    """문자 종류 규칙이 없는 짧은 필드 — 닉네임 같은 경우.

    위반값을 만들 때 소문자·숫자를 최소 1자 넣는 것은 값을 읽기 좋게 하려는
    정책이고 규칙이 아니다. 그 정책 때문에 '2자 이상' 규칙의 위반값(1자)을
    만들지 못하면, 구현에 최소 길이 검증이 없어도 케이스가 생기지 않아 조용히
    넘어간다.
    """

    def test_두자_이상_규칙의_위반값이_한자로_생성된다(self):
        e = UIElement(element_id="nickname", type="input", label="닉네임",
                      required=True, constraints={"min_length": 2, "max_length": 10})
        v = next(v for v in violations_for_element(e) if v.rule == "min_length")
        assert len(v.value) == 1
        assert satisfies(v.value, {"max_length": 10})

    def test_한자_이상_규칙은_위반값을_만들지_않는다(self):
        """길이 0 은 빈 값이고, 그건 required 위반과 구분되지 않는다."""
        e = UIElement(element_id="f", type="input", label="필드",
                      required=True, constraints={"min_length": 1})
        assert "min_length" not in {v.rule for v in violations_for_element(e)}

    def test_비밀번호의_위반값은_문자_종류_요건을_유지한다(self):
        """정책이 적용되는 쪽은 그대로여야 한다 — 로그인 화면 회귀 방지."""
        c = {"min_length": 8, "require_uppercase": 1, "require_special": 1}
        e = elem(constraints=c)
        v = next(v for v in violations_for_element(e) if v.rule == "min_length")
        assert v.value == "Aa1!aaa"
