"""로그인 전제는 화면 문서에 '전제' 절이 있을 때만 둔다 (2026-09-28, Qwen3.5-4B 전환).

프롬프트는 "'전제' 절이 있으면 requires_login=true, 없으면 null" 이라고 지시하지만
코드가 확인하지 않았다. 4B 를 다시 띄운 뒤 onboarding(회원가입→로그인→상품 등록)
문서에서 **회원가입 화면**에 로그인 전제를 붙였고, "비로그인으로 회원가입에 들어가면
로그인으로 보내야 한다" 는 가드 케이스가 생겼다 — 올바른 구현이 FAIL 인 오탐이다.
'5. 전제' 절은 상품 등록 화면 몫에만 있었다.

버리는 쪽이 안전하다. 정말 로그인이 필요한 화면이었다면 요소를 못 찾는 시끄러운
실패와 경고로 드러난다.
"""

from __future__ import annotations

from prova.models import Precondition, ScreenSpec
from prova.s1_spec_extractor.extractor import _drop_undeclared_precondition
from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage


def _doc(*lines: str) -> ParsedDocument:
    return ParsedDocument(source="x", pages=[ParsedPage(
        page_no=1, body_lines=[(t, float(i * 10)) for i, t in enumerate(lines)])])


def _spec() -> ScreenSpec:
    return ScreenSpec(screen_id="signup", screen_name="회원가입", url_path="/signup",
                      precondition=Precondition(requires_login=True))


def test_전제_절이_없으면_모델이_붙인_로그인_전제를_버리고_알린다():
    spec = _spec()
    _drop_undeclared_precondition(spec, _doc("1. 화면 개요", "3. 성공 조건"))
    assert spec.precondition is None
    assert any("전제" in w and "회원가입" in w for w in spec.warnings)


def test_전제_절이_있으면_둔다():
    spec = _spec()
    _drop_undeclared_precondition(spec, _doc("1. 화면 개요", "5. 전제", "로그인한 상태에서 동작한다."))
    assert spec.precondition is not None and spec.precondition.requires_login


def test_문장_속_낱말은_절_제목이_아니다():
    """'...상태를 전제한다' 는 절이 아니다 (declared_precondition_account 와 같은 판별)."""
    spec = _spec()
    _drop_undeclared_precondition(spec, _doc("이 화면은 로그인 상태를 전제로 한다."))
    assert spec.precondition is None


def test_로그인_전제가_아니면_건드리지_않는다():
    spec = _spec()
    spec.precondition = Precondition(requires_login=False)
    _drop_undeclared_precondition(spec, _doc("1. 화면 개요"))
    assert spec.precondition is not None and spec.warnings == []
