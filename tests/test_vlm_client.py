"""VLM 서버 클라이언트 — 켰다고 믿는 실행이 실제로 켜져 있는지.

## 이 파일이 막는 것

2차 경로가 **통째로 죽었는데 리포트가 그것을 말하지 않는** 상태다.

실제로 겪었다. vLLM 을 `--served-model-name qwen-vl` 로 띄우고 클라이언트는 기본
이름(`Qwen/Qwen2.5-VL-3B-Instruct-AWQ`)으로 요청했다. 그러면

    GET  /v1/models            -> 200 (서버는 살아 있다)
    POST /v1/chat/completions  -> 404 (그런 모델 없다)

가 된다. `health()` 가 앞의 것만 봤으므로 실행은 정상 기동했고, 로그에는
`2차 경로: vllm-vl @ http://localhost:8001/v1` 이 찍혔다. 그런데 `locate()` 마다
VLMError 가 나고 호출부가 그것을 탐지 실패로 되돌리므로, 리포트는 **9건 전부
'일치하는 요소가 없음'** 으로 보였다. 보정을 켜기 전과 완전히 같은 결과였다.

이건 이 프로젝트가 반복해서 만나는 구멍과 같은 모양이다 —
**확인하지 않은 것과 확인해서 통과한 것은 다르다.** 이름 불일치는 기동 시점에 알 수
있는 사실이므로 그때 끊어야 한다.

## 왜 실물 서버 없이 시험하는가

httpx 를 가로채 `/models` 응답을 직접 만든다. 실물 서버가 필요하면 이 확인은 GPU 가
있을 때만 돌고, 정작 이름을 틀리기 쉬운 상황(서버 설정을 바꿀 때)에서 아무 경고도
주지 못한다.
"""

from __future__ import annotations

import json

import httpx
import pytest

from prova.vlm.base import VLMError
from prova.vlm.qwen_vl import QwenVLClient

BASE = "http://vlm.test/v1"


def _client_with_models(monkeypatch, served: list[str] | None, *, model: str | None = None,
                        status: int = 200):
    """`/models` 가 주어진 목록을 돌려주는 클라이언트."""

    def fake_get(url, **kwargs):
        body = json.dumps({"data": [{"id": name} for name in (served or [])]})
        return httpx.Response(status, content=body,
                              request=httpx.Request("GET", url),
                              headers={"content-type": "application/json"})

    monkeypatch.setattr(httpx, "get", fake_get)
    return (QwenVLClient(base_url=BASE, model=model) if model
            else QwenVLClient(base_url=BASE))


class TestHealth:
    def test_이름이_맞으면_통과한다(self, monkeypatch):
        client = _client_with_models(monkeypatch, ["qwen-vl"], model="qwen-vl")
        client.health()   # 예외가 없으면 통과

    def test_서빙하지_않는_이름이면_끊는다(self, monkeypatch):
        """**이 파일의 핵심.** 서버는 200 을 주지만 우리 모델이 없다.

        이걸 통과시키면 locate() 마다 실패하고, 리포트는 '요소를 못 찾았다' 로만
        보인다 — 보정이 꺼진 실행과 구분되지 않는다."""
        client = _client_with_models(monkeypatch, ["qwen-vl"])   # 기본 이름으로 요청
        with pytest.raises(VLMError) as exc:
            client.health()
        assert "서빙하지 않습니다" in str(exc.value)

    def test_사유에_서빙_중인_이름을_남긴다(self, monkeypatch):
        """이름을 어떻게 맞춰야 하는지 알려주지 않으면 사용자가 서버에 직접
        물어봐야 한다. 그 정보는 이미 응답에 있다."""
        client = _client_with_models(monkeypatch, ["qwen-vl", "other"])
        with pytest.raises(VLMError) as exc:
            client.health()
        message = str(exc.value)
        assert "qwen-vl" in message
        assert "--vlm-model" in message

    def test_모델이_하나도_없으면_끊는다(self, monkeypatch):
        client = _client_with_models(monkeypatch, [])
        with pytest.raises(VLMError):
            client.health()

    def test_서버에_닿지_못하면_끊는다(self, monkeypatch):
        def fake_get(url, **kwargs):
            raise httpx.ConnectError("연결 거부", request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "get", fake_get)
        with pytest.raises(VLMError) as exc:
            QwenVLClient(base_url=BASE).health()
        assert "연결할 수 없습니다" in str(exc.value)

    def test_오류_응답이면_끊는다(self, monkeypatch):
        client = _client_with_models(monkeypatch, ["qwen-vl"], model="qwen-vl",
                                     status=503)
        with pytest.raises(VLMError):
            client.health()


class TestModelName:
    def test_이름을_지정할_수_있다(self):
        """vLLM 은 --served-model-name 으로 임의의 이름을 쓴다. 배포마다 다르므로
        클라이언트가 고정 이름을 강요하면 안 된다."""
        assert QwenVLClient(base_url=BASE, model="아무개").model == "아무개"

    def test_기본_이름은_HF_경로다(self):
        """--served-model-name 을 주지 않으면 vLLM 이 모델 경로를 그대로 쓴다."""
        assert QwenVLClient(base_url=BASE).model == "Qwen/Qwen2.5-VL-3B-Instruct-AWQ"
