"""모델에게 보내는 추출 스키마는 핵심 사실의 키를 생략하지 못하게 한다 (2026-09-28).

Qwen3.5-4B 스파이크에서 표 머리글이 바뀐 기획서(코드가 표를 못 읽어 모델만 읽는 경우)에
`{"screen_id", "screen_name", "url_path", "precondition"}` 만 돌려받았다 — 요소·실패 조건을
통째로 생략했다. ScreenSpec 에서 그 필드들은 기본값이 있어 스키마상 선택이라, 정형 출력이
생략을 허용한 것이다. 필수로 두자 같은 모델이 요소 3·규칙 4·안내 2 를 7B 와 똑같이 읽었다.
구멍은 7B 에도 있다 — 지금까지 우연히 생략하지 않았을 뿐이다.

**빈 목록은 허용한다.** 최소 개수를 강제하면 요소가 정말 없는 문서에서 모델이 요소를
지어낸다. 키를 쓰게 하는 것까지가 스키마의 몫이다.
"""

from __future__ import annotations

from prova.models import ScreenSpec
from prova.s1_spec_extractor.extractor import EXTRACTION_REQUIRED, extract_screen_spec
from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage


class _Capture:
    def __init__(self):
        self.schema = None

    def complete_json(self, *, system, user, schema, max_tokens=2048, temperature=0.0):
        self.schema = schema
        return {"screen_id": "s", "screen_name": "화면", "url_path": "/s",
                "elements": [], "success_condition": "", "failure_conditions": []}


def _extract() -> dict:
    llm = _Capture()
    doc = ParsedDocument(source="x", pages=[ParsedPage(page_no=1, body_lines=[("본문", 10.0)])])
    extract_screen_spec(doc, llm)
    return llm.schema


def test_요소_성공_실패_조건은_생략할_수_없다():
    required = set(_extract()["required"])
    assert {"elements", "success_condition", "failure_conditions"} <= required
    assert {"screen_id", "screen_name", "url_path"} <= required


def test_빈_목록은_허용한다():
    """최소 개수를 강제하면 요소가 없는 문서에서 모델이 지어낸다."""
    assert "minItems" not in _extract()["properties"]["elements"]


class TestNonTextConstraints:
    """선택·체크 요소의 문자 규칙은 버린다 (S2 NON_TEXT_TYPES 와 같은 원칙).

    키를 필수로 두자 7B 가 주문조회 '상태' select 에 선택지를 이어 붙인
    pattern('전체|배송중|배송완료|취소')을 지어냈다. 필드 셋 중 무엇 하나만 필수로
    둬도 같았다 — 스키마가 조금만 바뀌어도 흔들리는 경계 항목이다. 고르는 요소에는
    '규칙 하나만 어긴 입력' 을 만들 방법이 없어 S2 가 이미 무시하므로, 남겨 두면
    검증하지 않을 규칙을 명세에 적어 두는 셈이다.
    """

    def _spec(self, el_type, constraints):
        from prova.models import UIElement
        return ScreenSpec(screen_id="s", screen_name="화면", url_path="/s", elements=[
            UIElement(element_id="status", type=el_type, label="상태",
                      constraints=constraints, options=["전체", "배송중"])])

    def test_select_의_규칙을_버리고_알린다(self):
        from prova.s1_spec_extractor.extractor import _drop_non_text_constraints
        spec = self._spec("select", {"pattern": "전체|배송중"})
        _drop_non_text_constraints(spec)
        assert spec.elements[0].constraints == {}
        assert any("상태" in w and "pattern" in w for w in spec.warnings)

    def test_입력란의_규칙은_그대로_둔다(self):
        from prova.s1_spec_extractor.extractor import _drop_non_text_constraints
        spec = self._spec("input", {"pattern": "^[0-9]+$"})
        _drop_non_text_constraints(spec)
        assert spec.elements[0].constraints == {"pattern": "^[0-9]+$"}
        assert spec.warnings == []

    def test_버릴_것이_없으면_경고하지_않는다(self):
        from prova.s1_spec_extractor.extractor import _drop_non_text_constraints
        spec = self._spec("checkbox", {})
        _drop_non_text_constraints(spec)
        assert spec.warnings == []


def test_ScreenSpec_자체는_바꾸지_않는다():
    """코드와 테스트는 요소 없는 화면을 만들 수 있어야 한다(전제 화면 등)."""
    assert "elements" not in ScreenSpec.model_json_schema().get("required", [])
    assert set(EXTRACTION_REQUIRED) >= {"elements"}
