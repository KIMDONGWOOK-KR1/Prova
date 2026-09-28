"""요소 표의 '에러 메시지' 열은 코드가 읽는다 (2026-09-28, Qwen3.5-4B 스파이크).

파서는 이 열을 이미 읽고 있었지만(declared_element_rows) 모델이 빠뜨린 요소를
백필할 때만 썼다. 안내 문구 열(declared_placeholders)과 달리 모델 답을 맞추지
않아, 4B 가 회원가입 '약관 동의' 의 error_message 를 비우자 표에 적힌
"약관에 동의해야 합니다." 가 명세에서 사라졌다.
"""

from __future__ import annotations

from prova.models import ScreenSpec, UIElement
from prova.s1_spec_extractor.extractor import _apply_declared_error_messages
from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage, ParsedTable

HEADER = ["요소 ID", "유형", "라벨", "필수", "입력 검증 규칙", "안내 문구", "에러 메시지"]


def _doc(*rows) -> ParsedDocument:
    return ParsedDocument(source="x", pages=[ParsedPage(
        page_no=1, tables=[ParsedTable(rows=[HEADER, *rows])])])


def _spec(error_message=None) -> ScreenSpec:
    return ScreenSpec(screen_id="s", screen_name="s", url_path="/s", elements=[
        UIElement(element_id="agree_terms", type="checkbox", label="약관 동의",
                  required=True, error_message=error_message),
        UIElement(element_id="submit", type="button", label="가입하기")])


DOC = _doc(["agree_terms", "체크박스", "약관 동의", "필수", "-", "-", "약관에 동의해야 합니다."],
           ["submit", "버튼", "가입하기", "-", "-", "-", "-"])


def test_표의_에러_메시지_열을_라벨로_읽는다():
    assert DOC.declared_error_messages() == {"약관 동의": "약관에 동의해야 합니다."}


def test_모델이_비운_문구를_표로_채운다():
    spec = _spec()
    _apply_declared_error_messages(spec, DOC.declared_error_messages())
    assert spec.elements[0].error_message == "약관에 동의해야 합니다."


def test_모델이_다르게_적었으면_표로_맞추고_알린다():
    spec = _spec("약관에 동의하세요")
    _apply_declared_error_messages(spec, DOC.declared_error_messages())
    assert spec.elements[0].error_message == "약관에 동의해야 합니다."
    assert any("약관 동의" in w for w in spec.warnings)


def test_공백만_다르면_모델_값을_둔다():
    """PDF 표 칸은 줄바꿈 자리에 공백이 끼어 '특수문 자' 가 된다. 공백만 다른 같은
    문구를 표 값으로 덮으면 모델이 옳게 쓴 문구가 깨진다(픽스처 27줄이 그렇게 바뀌었다)."""
    doc = _doc(["agree_terms", "체크박스", "약관 동의", "필수", "-", "-", "약관에 동의해 야 합니다."])
    spec = _spec("약관에 동의해야 합니다.")
    _apply_declared_error_messages(spec, doc.declared_error_messages())
    assert spec.elements[0].error_message == "약관에 동의해야 합니다."
    assert spec.warnings == []


def test_표가_비운_요소는_건드리지_않는다():
    """'-' 는 '없음' 이다. 모델이 본문에서 읽은 값을 지우지 않는다(안내 문구와 같은 판단)."""
    spec = _spec()
    spec.elements[1].error_message = "본문에서 읽음"
    _apply_declared_error_messages(spec, DOC.declared_error_messages())
    assert spec.elements[1].error_message == "본문에서 읽음"


def test_에러_메시지_열이_없으면_아무것도_읽지_않는다():
    doc = ParsedDocument(source="x", pages=[ParsedPage(page_no=1, tables=[ParsedTable(
        rows=[HEADER[:6], ["agree_terms", "체크박스", "약관 동의", "필수", "-", "-"]])])])
    assert doc.declared_error_messages() == {}
