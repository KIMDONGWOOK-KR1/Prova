"""vLLM `health()` 의 두 실패는 다른 사실이다 — 연결 실패와 모델 불일치.

## 왜 가르는가 (2026-08-22)

IoU 채점을 위해 7B 를 내리고 VL 을 띄운 채로 두면, S1 골든 대조 69개가 전부
skip 된다. 그 사유가 "vLLM 에 연결할 수 없습니다" 였다 — **거짓이다.** 서버는 살아
있고 다른 모델이 서빙 중이다. 연결 실패는 '측정 환경이 없다' 이고 skip 이 맞지만,
모델 불일치는 '측정 환경이 잘못 구성됐다' 이고 크게 실패해야 한다. 같은 예외로
접으면 둘 다 조용히 skip 되고, 통과처럼 보이는 결과가 추출 정확도를 아무것도
확인하지 않은 상태가 된다.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from prova.llm.base import LLMError
from prova.llm.vllm_backend import ModelNotServed, VLLMClient


def _client_with_models(monkeypatch, ids):
    client = VLLMClient(model="Qwen/Qwen2.5-7B-Instruct-AWQ")
    fake = SimpleNamespace(data=[SimpleNamespace(id=i) for i in ids])
    monkeypatch.setattr(
        client._client, "with_options",
        lambda **kw: SimpleNamespace(models=SimpleNamespace(list=lambda: fake)),
    )
    return client


class TestHealthDistinguishes:
    def test_다른_모델이_서빙_중이면_ModelNotServed(self, monkeypatch):
        client = _client_with_models(monkeypatch, ["qwen-vl"])
        with pytest.raises(ModelNotServed) as info:
            client.health()
        assert "qwen-vl" in str(info.value)

    def test_ModelNotServed_는_LLMError_이기도_하다(self, monkeypatch):
        """기존 호출자(`except LLMError`)가 깨지지 않는다."""
        client = _client_with_models(monkeypatch, [])
        with pytest.raises(LLMError):
            client.health()

    def test_연결_실패는_ModelNotServed_가_아니다(self, monkeypatch):
        client = VLLMClient(base_url="http://127.0.0.1:1/v1")

        def boom(**kw):
            raise ConnectionError("refused")

        monkeypatch.setattr(client._client, "with_options", boom)
        with pytest.raises(LLMError) as info:
            client.health()
        assert not isinstance(info.value, ModelNotServed)

    def test_이름이_맞으면_통과(self, monkeypatch):
        client = _client_with_models(monkeypatch, ["Qwen/Qwen2.5-7B-Instruct-AWQ"])
        assert client.health() == "Qwen/Qwen2.5-7B-Instruct-AWQ"
