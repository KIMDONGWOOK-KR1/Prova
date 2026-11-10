"""Claude 백엔드의 스키마 변환 — 네트워크 없이 확인한다.

## 왜 이 테스트가 있는가

2026-11-10 첫 측정에서 Claude 가 검증 규칙(`constraints`)을 전부 `{}` 로 냈다. 모델이
틀린 게 아니라 **백엔드가 그 자리를 '속성 없는 닫힌 객체' 로 바꿔 보낸 것**이었다 —
Claude 의 정형 출력은 키를 미리 정하지 않은 객체를 표현하지 못하고, SDK 변환은 오류 없이
빈 객체로 접는다. 로컬 대 API 비교에서 이게 남아 있으면 API 쪽 정확도가 거짓으로 낮게 나온다.

실제 호출은 `PROVA_LLM_BACKEND=claude uv run pytest tests/test_s1_golden.py` 가 맡는다.
"""

from __future__ import annotations

import pytest

from prova.llm.base import LLMError
from prova.llm.claude_backend import _restore_free_form, _stringify_free_form
from prova.s1_spec_extractor.extractor import _extraction_schema


def _free_form_paths(node, path: str = "") -> list[str]:
    found = []
    if isinstance(node, dict):
        if (node.get("type") == "object" and not node.get("properties")
                and node.get("additionalProperties", True) is not False):
            found.append(path)
        for key, value in node.items():
            found += _free_form_paths(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found += _free_form_paths(value, f"{path}[{index}]")
    return found


def test_S1_스키마에_자유_형태_객체가_있다():
    """이 테스트의 전제. 없어지면 아래 변환은 할 일이 없고, 늘면 여기서 눈에 띈다."""
    paths = _free_form_paths(_extraction_schema())
    assert any(p.endswith("/constraints") for p in paths), paths


def test_보내는_스키마에_자유_형태_객체가_남지_않는다():
    sent = _stringify_free_form(_extraction_schema())
    assert _free_form_paths(sent) == []
    constraints = sent["$defs"]["UIElement"]["properties"]["constraints"]
    assert constraints["type"] == "string"
    assert "JSON" in constraints["description"]


def test_원본_스키마를_건드리지_않는다():
    schema = _extraction_schema()
    before = _free_form_paths(schema)
    _stringify_free_form(schema)
    assert _free_form_paths(schema) == before


def test_문자열로_받은_객체를_되돌린다():
    schema = _extraction_schema()
    raw = {
        "elements": [
            {"element_id": "email", "constraints": '{"min_length": 8, "format": "email"}'},
            {"element_id": "btn", "constraints": "{}"},
            {"element_id": "memo", "constraints": ""},
        ],
        "seed_rows": ['{"아이디": "user01"}'],
    }
    restored = _restore_free_form(raw, schema, schema["$defs"])
    assert [e["constraints"] for e in restored["elements"]] == [
        {"min_length": 8, "format": "email"}, {}, {},
    ]
    assert restored["seed_rows"] == [{"아이디": "user01"}]
    # 자유 형태가 아닌 문자열은 그대로 둔다
    assert restored["elements"][0]["element_id"] == "email"


def test_읽을_수_없는_문자열은_조용히_넘기지_않는다():
    schema = _extraction_schema()
    for broken in ("min_length: 8", "[1, 2]"):
        with pytest.raises(LLMError):
            _restore_free_form({"elements": [{"constraints": broken}]}, schema, schema["$defs"])
