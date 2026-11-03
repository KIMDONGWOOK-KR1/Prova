"""모델 출력이 max_tokens 에서 잘린 것을 잘렸다고 말하고, S1 은 한 번 더 큰 한도로 부른다.

## 2026-11-03 WebTestBench 시범에서 잡은 구멍

요소가 많은 화면(GPT 가 쓴 기획서의 상세 화면)에서 S1 출력이 3072 토큰에서 끊겼다.
그런데 오류 문구는 "JSON 파싱 실패 — guided_json 이 적용되지 않았을 수 있습니다" 였다 —
**거짓이다.** 정형 출력은 걸려 있었고, 응답의 finish_reason 이 "length" 였다. 개발자가
서버 설정을 뒤지게 만든다. 고칠 것은 출력 한도다.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from prova.llm.base import LLMError, OutputTruncated
from prova.llm.vllm_backend import VLLMClient
from prova.s1_spec_extractor.extractor import S1_RETRY_MAX_TOKENS, extract_screen_spec
from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage


def _client_returning(monkeypatch, content, finish_reason):
    client = VLLMClient(model="m")
    resp = SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=content), finish_reason=finish_reason)])
    monkeypatch.setattr(client._client.chat.completions, "create", lambda **kw: resp)
    return client


def _call(client):
    return client.complete_json(system="s", user="u", schema={"title": "T"}, max_tokens=3072)


class TestVLLMTruncation:
    def test_잘린_출력은_OutputTruncated_이고_한도를_말한다(self, monkeypatch):
        client = _client_returning(monkeypatch, '{"elements": [{"id": "a", "la', "length")
        with pytest.raises(OutputTruncated) as info:
            _call(client)
        msg = str(info.value)
        assert "3072" in msg
        assert "guided_json" not in msg

    def test_OutputTruncated_는_LLMError_이기도_하다(self):
        assert issubclass(OutputTruncated, LLMError)

    def test_정상_종료는_그대로_돌려준다(self, monkeypatch):
        client = _client_returning(monkeypatch, '{"a": 1}', "stop")
        assert _call(client) == {"a": 1}


SPEC = {"screen_id": "s", "screen_name": "화면", "url_path": "/s",
        "elements": [], "success_condition": "", "failure_conditions": []}


class _TruncatesBelow:
    """한도가 `need` 보다 작으면 잘린다."""

    def __init__(self, need):
        self.need = need
        self.budgets = []

    def complete_json(self, *, system, user, schema, max_tokens=2048, temperature=0.0):
        self.budgets.append(max_tokens)
        if max_tokens < self.need:
            raise OutputTruncated(f"잘림 ({max_tokens})")
        return dict(SPEC)


def _doc():
    return ParsedDocument(source="x", pages=[ParsedPage(page_no=1, body_lines=[("본문", 10.0)])])


class TestS1Retry:
    def test_잘리면_한_번_더_큰_한도로_부른다(self):
        llm = _TruncatesBelow(need=S1_RETRY_MAX_TOKENS)
        spec = extract_screen_spec(_doc(), llm)
        assert spec.screen_id == "s"
        assert llm.budgets == [3072, S1_RETRY_MAX_TOKENS]

    def test_안_잘리면_처음_한도로_한_번만_부른다(self):
        # 기존 화면의 호출(과 그 캐시 키)이 바뀌지 않는다.
        llm = _TruncatesBelow(need=0)
        extract_screen_spec(_doc(), llm)
        assert llm.budgets == [3072]

    def test_큰_한도에서도_잘리면_조용히_넘기지_않는다(self):
        llm = _TruncatesBelow(need=10**9)
        with pytest.raises(OutputTruncated):
            extract_screen_spec(_doc(), llm)
        assert llm.budgets == [3072, S1_RETRY_MAX_TOKENS]
