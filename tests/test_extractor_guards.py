"""S1 의 조용한 실패를 막는 장치들. LLM 없이 검증한다.

## 여기서 지키려는 것

S1 이 요소를 빠뜨리면 리포트에는 '구현 결함' 처럼 보인다. 원인은 추출인데
개발자는 자기 코드를 뒤진다. 특히 **제출 버튼이 빠지면 폼이 제출되지 않아
구현이 옳아도 모든 케이스가 실패로 나온다.** 실측에서 로컬 7B 가 7행 표의 버튼
행을 빠뜨린 일이 있었으므로, 가정이 아니라 관측된 실패다.

프롬프트에 요소 ID 목록을 넣어 예방하고, 그래도 빠지면 경고로 알린다. 예방과
검출을 둘 다 두는 이유는 프롬프트가 모델·버전에 따라 흔들리기 때문이다.
"""

from __future__ import annotations

from prova.models import ScreenSpec, UIElement
from prova.s1_spec_extractor.extractor import (
    _normalize_element_ids,
    build_user_prompt,
    structural_warnings,
)
from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage, ParsedTable


def element_table(*ids: str) -> ParsedDocument:
    rows = [["요소 ID", "유형", "라벨"]] + [[i, "입력", i] for i in ids]
    return ParsedDocument(
        source="x", pages=[ParsedPage(page_no=1, tables=[ParsedTable(rows=rows)])]
    )


def spec_with(*elements: UIElement) -> ScreenSpec:
    return ScreenSpec(screen_id="s", screen_name="화면", url_path="/s",
                      elements=list(elements))


def button(element_id: str = "submit") -> UIElement:
    return UIElement(element_id=element_id, type="button", label="확인")


class TestBuildUserPrompt:
    def test_요소_ID_목록을_프롬프트에_박는다(self):
        """코드가 확실히 아는 사실을 추론에 맡기지 않는다. 표의 몇 번째 열이
        ID 인지는 괘선으로 정해지므로 추론할 여지가 없다."""
        prompt = build_user_prompt("본문", ["email", "password", "login_btn"])
        assert "정확히 3개" in prompt
        assert "email, password, login_btn" in prompt

    def test_목록이_없으면_지시를_넣지_않는다(self):
        """ID 열이 없는 기획서도 있다. 없는 사실을 지어내 지시하면 LLM 이
        존재하지 않는 요소를 만들어 낸다."""
        assert "반드시 지킬 것" not in build_user_prompt("본문", [])
        assert "반드시 지킬 것" not in build_user_prompt("본문", None)


class TestStructuralWarnings:
    def test_표에_있는_요소가_빠지면_경고한다(self):
        doc = element_table("email", "password", "login_btn")
        spec = spec_with(
            UIElement(element_id="email", type="input", label="이메일"),
            button("login_btn"),
        )
        warnings = structural_warnings(spec, doc)
        assert any("password" in w for w in warnings)
        assert any("구현 결함이 아닙니다" in w for w in warnings), (
            "원인이 추출이라는 사실을 알려야 개발자가 자기 코드를 뒤지지 않는다"
        )

    def test_버튼이_없으면_경고한다(self):
        """제출 버튼이 없으면 폼이 제출되지 않아 전 케이스가 실패로 나온다."""
        doc = element_table("email")
        spec = spec_with(UIElement(element_id="email", type="input", label="이메일"))
        assert any("버튼" in w for w in structural_warnings(spec, doc))

    def test_모두_추출되면_경고가_없다(self):
        doc = element_table("email", "login_btn")
        spec = spec_with(
            UIElement(element_id="email", type="input", label="이메일"),
            button("login_btn"),
        )
        assert structural_warnings(spec, doc) == []

    def test_대조할_표가_없으면_누락_검사를_하지_않는다(self):
        """ID 열이 없는 기획서에서 없는 누락을 경고하면 안 된다."""
        doc = ParsedDocument(source="x", pages=[ParsedPage(page_no=1)])
        spec = spec_with(UIElement(element_id="email", type="input", label="이메일"),
                         button())
        assert structural_warnings(spec, doc) == []


class TestNormalizeElementIds:
    """실측에서 7B 가 password_confirm 을 'password_confir m' 으로 냈다.

    element_id 는 슬러그라서 공백이 들어갈 여지가 없고, 고칠 방법도 하나뿐이다.
    판정 강도를 낮추는 보정이 아니라 표기 복원이므로 조용히 처리한다.
    """

    def test_ID의_공백을_지운다(self):
        spec = spec_with(
            UIElement(element_id="password_confir m", type="input", label="확인")
        )
        _normalize_element_ids(spec)
        assert spec.elements[0].element_id == "password_confirm"

    def test_same_as_참조도_함께_고친다(self):
        """참조가 어긋나면 교차 필드 위반 케이스가 생성되지 않아, 구현에 일치
        검증이 없어도 조용히 넘어간다."""
        spec = spec_with(
            UIElement(element_id="pass word", type="input", label="비밀번호"),
            UIElement(element_id="confirm", type="input", label="비밀번호 확인",
                      constraints={"same_as": "pass word"}),
        )
        _normalize_element_ids(spec)
        assert spec.elements[0].element_id == "password"
        assert spec.elements[1].constraints["same_as"] == "password"

    def test_정상_ID는_건드리지_않는다(self):
        spec = spec_with(UIElement(element_id="login_btn", type="button", label="로그인"))
        _normalize_element_ids(spec)
        assert spec.elements[0].element_id == "login_btn"
