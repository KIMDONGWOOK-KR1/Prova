"""S1 출력이 잘렸을 때 다시 부르는 호출은 문자열 길이에 상한을 둔다 — 반복 루프를 끊는다.

## 2026-11-04 WebTestBench 0051 B 에서 잡은 구멍

S1 이 6144 토큰에서도 잘렸다. 화면 12개 중 `review_versions` 하나였고, 한도를 9000 으로
올려도 잘렸다. 출력이 긴 게 아니었다 — 모델이 요소 하나의 `constraints.pattern` 에
`\\b` 를 끝없이 쓰는 **반복 루프**에 빠졌다. constraints 는 자유 딕셔너리라 문자열 길이에
제한이 없다.

같은 화면을 문자열 상한(maxLength)이 있는 스키마로 다시 부르니 vLLM 정형 출력이 상한을
지켰고, 모델은 루프 없이 973 토큰에 끝냈다.

## 지키는 것

- 상한은 **잘려서 다시 부를 때만** 건다. 잘리지 않는 화면의 호출(과 캐시 키)은 그대로다.
- 상한에 딱 걸린 값은 반복으로 잘린 것으로 본다. 제약 값이면 버리고 경고를 남긴다 — 잘린
  정규식으로 위반 케이스를 만들면 없는 결함을 보고한다. 다른 칸(라벨·문구)이면 고칠 수 없으니
  조용히 넘기지 않고 실패시킨다.
"""

from __future__ import annotations

import pytest

from prova.llm.base import LLMError, OutputTruncated
from prova.s1_spec_extractor.extractor import (
    S1_CONSTRAINT_CAP,
    S1_RETRY_MAX_TOKENS,
    S1_STRING_CAP,
    extract_screen_spec,
)
from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage


def _doc():
    return ParsedDocument(source="x", pages=[ParsedPage(page_no=1, body_lines=[("본문", 10.0)])])


def _spec(elements):
    return {"screen_id": "s", "screen_name": "화면", "url_path": "/s", "elements": elements,
            "success_condition": "", "failure_conditions": []}


def _el(eid, label="이름", constraints=None):
    return {"element_id": eid, "type": "input", "label": label,
            "constraints": constraints or {}}


class _LoopsThenCapped:
    """첫 호출은 잘리고, 다시 부를 때 받은 스키마를 기록하고 정해 둔 답을 준다."""

    def __init__(self, answer):
        self.answer = answer
        self.schemas = []

    def complete_json(self, *, system, user, schema, max_tokens=2048, temperature=0.0):
        self.schemas.append(schema)
        if len(self.schemas) == 1:
            raise OutputTruncated("잘림")
        return self.answer


def _strings(node, out):
    if isinstance(node, dict):
        if node.get("type") == "string":
            out.append(node)
        for v in node.values():
            _strings(v, out)
    elif isinstance(node, list):
        for v in node:
            _strings(v, out)
    return out


class TestRetrySchema:
    def test_다시_부를_때만_문자열_상한을_건다(self):
        llm = _LoopsThenCapped(_spec([]))
        extract_screen_spec(_doc(), llm)
        first, retry = llm.schemas
        assert not any("maxLength" in s for s in _strings(first, []))
        assert all(s.get("maxLength") for s in _strings(retry, []))

    def test_제약_딕셔너리의_문자열_값에도_상한이_있다(self):
        llm = _LoopsThenCapped(_spec([]))
        extract_screen_spec(_doc(), llm)
        constraints = llm.schemas[1]["$defs"]["UIElement"]["properties"]["constraints"]
        kinds = constraints["additionalProperties"]["anyOf"]
        assert {"type": "string", "maxLength": S1_CONSTRAINT_CAP} in kinds


class TestCappedValues:
    def test_상한에_걸린_제약은_버리고_경고한다(self):
        loop = "^" + "\\b" * ((S1_CONSTRAINT_CAP - 1) // 2) + "x" * ((S1_CONSTRAINT_CAP - 1) % 2)
        assert len(loop) == S1_CONSTRAINT_CAP
        llm = _LoopsThenCapped(_spec([_el("v", constraints={"pattern": loop, "max_length": 20})]))
        spec = extract_screen_spec(_doc(), llm)
        el = spec.elements[0]
        assert "pattern" not in el.constraints
        assert el.constraints["max_length"] == 20
        assert any("pattern" in w and "반복" in w for w in spec.warnings)

    def test_상한_아래의_제약은_그대로다(self):
        llm = _LoopsThenCapped(_spec([_el("v", constraints={"pattern": "^[0-9]+$"})]))
        spec = extract_screen_spec(_doc(), llm)
        assert spec.elements[0].constraints["pattern"] == "^[0-9]+$"

    def test_다른_칸이_상한에_걸리면_조용히_넘기지_않는다(self):
        llm = _LoopsThenCapped(_spec([_el("v", label="가" * S1_STRING_CAP)]))
        with pytest.raises(LLMError) as info:
            extract_screen_spec(_doc(), llm)
        assert "반복" in str(info.value)

    def test_상한_뒤에도_잘리면_그대로_올린다(self):
        class _Always:
            def complete_json(self, **kw):
                raise OutputTruncated("잘림")
        with pytest.raises(OutputTruncated):
            extract_screen_spec(_doc(), _Always())


def test_다시_부르는_한도는_그대로다():
    llm = _LoopsThenCapped(_spec([]))
    budgets = []
    orig = llm.complete_json

    def spy(**kw):
        budgets.append(kw["max_tokens"])
        return orig(**kw)

    llm.complete_json = spy
    extract_screen_spec(_doc(), llm)
    assert budgets == [3072, S1_RETRY_MAX_TOKENS]
