"""기획서 본문에 없는 문구를 요구사항으로 쓰지 않는다.

## 무엇을 막는가 — 실측으로 확인한 오탐

기획서 요소 표에서 '안내 문구' 열을 지우고 실물 7B 로 돌렸더니 모델이
`'이메일 입력'` 을 **지어냈다.** 문서에 그런 말이 한 글자도 없다. 그러자 도구는 안내
문구 대조 케이스를 만들어 **올바른 구현을 FAIL 로 보고했다.**

    FAIL 입력 안내 문구 확인
         문구가 다름 — '이메일': 기대 '이메일 입력', 화면 '이메일을 입력하세요'

없는 결함을 자신 있게 보고한 것이고, 경고도 없었다. 개발자는 없는 버그를 찾다가 도구를
믿지 않게 된다.

## 이 파일이 지키는 두 성질

    1. 지어낸 문구는 버린다        오탐을 만들지 않는다
    2. 적힌 문구는 절대 안 버린다   검증을 잃지 않는다

**2번이 더 위험하다.** PDF 는 원문을 그대로 복원하지 못하므로, 이 검사가 진짜 요구사항을
조용히 지우면 리포트가 근거 없이 초록불이 된다. 그래서 픽스처 3종의 정답 문구 전체를
대조하는 테스트를 함께 둔다.

## 왜 '표에 있는가' 가 아니라 '본문에 있는가' 인가

표 기반으로만 신뢰하면 산문으로 쓴 기획서에서 검증이 사라진다. 실측에서 7B 는 산문에
적힌 안내 문구를 정확히 읽어냈고, 그건 버릴 이유가 없는 정보다. 본문 대조는 표든
산문이든 통한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prova.models import ScreenSpec, UIElement
from prova.s1_spec_extractor.extractor import _drop_invented_strings
from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage, normalize_ws


def doc_with(*lines: str) -> ParsedDocument:
    """본문에 주어진 줄들이 있는 문서."""
    return ParsedDocument(
        source="x",
        pages=[ParsedPage(page_no=1, body_text="\n".join(lines))],
    )


def spec_with(*elements: UIElement, required_message: str | None = None) -> ScreenSpec:
    return ScreenSpec(
        screen_id="login", screen_name="로그인", url_path="/login",
        elements=list(elements), required_message=required_message,
    )


def field(**kwargs) -> UIElement:
    base = dict(element_id="email", type="input", label="이메일")
    base.update(kwargs)
    return UIElement(**base)


class TestDropsInvented:
    def test_본문에_없는_안내_문구를_버린다(self):
        """실측에서 나온 그 값이다 — 문서에 '이메일 입력' 이 없다."""
        spec = spec_with(field(placeholder="이메일 입력"))
        _drop_invented_strings(spec, doc_with("이메일은 필수입니다."))
        assert spec.elements[0].placeholder is None

    def test_버린_사실을_경고로_남긴다(self):
        """조용히 버리면 '왜 안내 문구를 확인하지 않았는가' 를 알 수 없다."""
        spec = spec_with(field(placeholder="이메일 입력"))
        _drop_invented_strings(spec, doc_with("이메일은 필수입니다."))
        assert any("이메일 입력" in w for w in spec.warnings)

    def test_본문에_없는_에러_문구를_버린다(self):
        spec = spec_with(field(error_message="이메일이 틀렸어요"))
        _drop_invented_strings(spec, doc_with("이메일은 필수입니다."))
        assert spec.elements[0].error_message is None

    def test_본문에_없는_필수_문구를_버린다(self):
        spec = spec_with(field(), required_message="입력해 주세요")
        _drop_invented_strings(spec, doc_with("이메일은 필수입니다."))
        assert spec.required_message is None

    def test_요소가_여럿이면_각각_판단한다(self):
        """하나가 지어낸 값이라고 다른 것까지 버리면 검증을 잃는다."""
        spec = spec_with(
            field(label="이메일", placeholder="이메일을 입력하세요"),
            field(element_id="password", label="비밀번호", placeholder="비번 입력"),
        )
        _drop_invented_strings(spec, doc_with("이메일을 입력하세요"))
        assert spec.elements[0].placeholder == "이메일을 입력하세요"
        assert spec.elements[1].placeholder is None


class TestKeepsDeclared:
    """**이쪽이 더 위험하다.** 진짜 요구사항을 지우면 리포트가 근거 없이 초록불이 된다."""

    def test_본문에_있는_안내_문구는_남긴다(self):
        spec = spec_with(field(placeholder="이메일을 입력하세요"))
        _drop_invented_strings(spec, doc_with("| 이메일 | 이메일을 입력하세요 |"))
        assert spec.elements[0].placeholder == "이메일을 입력하세요"

    def test_산문에_적힌_문구도_남긴다(self):
        """표 기반으로만 신뢰하면 산문 기획서에서 검증이 사라진다. 실측에서 7B 는
        산문에 적힌 안내 문구를 정확히 읽어냈다 — 버릴 이유가 없는 정보다."""
        spec = spec_with(field(placeholder="이메일을 입력하세요"))
        _drop_invented_strings(
            spec, doc_with("안내 문구는 '이메일을 입력하세요' 입니다."))
        assert spec.elements[0].placeholder == "이메일을 입력하세요"

    def test_공백_차이는_문제되지_않는다(self):
        """PDF 는 줄바꿈과 공백을 원문대로 복원하지 않는다. 그것 때문에 진짜
        요구사항을 버리면 이 검사가 해를 끼친다."""
        spec = spec_with(field(placeholder="이메일을  입력하세요"))
        _drop_invented_strings(spec, doc_with("이메일을 입력하세요"))
        assert spec.elements[0].placeholder is not None

    def test_남긴_경우_경고가_없다(self):
        spec = spec_with(field(placeholder="이메일을 입력하세요"))
        _drop_invented_strings(spec, doc_with("이메일을 입력하세요"))
        assert spec.warnings == []

    def test_문구가_없는_요소는_건드리지_않는다(self):
        """버튼처럼 안내 문구가 없는 요소에 경고를 붙이면 안 된다."""
        spec = spec_with(UIElement(element_id="btn", type="button", label="로그인"))
        _drop_invented_strings(spec, doc_with("로그인 버튼"))
        assert spec.warnings == []


GOLDENS = sorted(Path("fixtures/specs").glob("*.golden.json"))


@pytest.mark.parametrize("golden", GOLDENS, ids=lambda p: p.name)
def test_픽스처_정답_문구는_모두_본문에서_찾아진다(golden):
    """**이 검사의 안전 근거다.**

    `_drop_invented_strings` 는 본문 대조로 문구를 버린다. 정답 문구 하나라도 본문에서
    찾아지지 않으면, 이 장치가 진짜 요구사항을 조용히 지운다는 뜻이다.

    측정 시점에 3종 19개가 모두 통과했다. 픽스처를 고치거나 PDF 생성을 바꿀 때
    이 성질이 깨지면 여기서 잡힌다.
    """
    from prova.s1_spec_extractor.pdf_parser import parse_pdf

    pdf = golden.with_name(golden.name.replace(".golden.json", ".pdf"))
    text = normalize_ws(parse_pdf(pdf).to_llm_text())
    data = json.loads(golden.read_text(encoding="utf-8"))

    missing = []
    for element in data["elements"]:
        for name in ("placeholder", "error_message"):
            value = element.get(name)
            if value and normalize_ws(value) not in text:
                missing.append(f"{element['label']}.{name}={value!r}")
    if data.get("required_message"):
        value = data["required_message"]
        if normalize_ws(value) not in text:
            missing.append(f"required_message={value!r}")

    assert not missing, (
        "정답 문구가 PDF 본문에서 찾아지지 않는다 — _drop_invented_strings 가 "
        "진짜 요구사항을 버리게 된다:\n  " + "\n  ".join(missing)
    )
