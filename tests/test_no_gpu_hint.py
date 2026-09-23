"""GPU 가 없을 때 웹 UI 가 다음에 할 수 있는 것을 알려 주는가.

## 무엇이 문제였나

`configs/default.yaml` 의 기본 백엔드는 `vllm` 이고, 웹 UI 의 드롭다운도 '실제
모델 — GPU 서버의 7B' 로 열린다. 그래서 GPU 서버가 없는 사람이 처음 화면을 열고
'계획 만들기' 를 누르면 이렇게 끝난다.

    계획을 만들지 못했습니다
    vLLM 서버에 연결할 수 없습니다: http://localhost:8000/v1
      - SSH 터널이 열려 있는지 확인: ssh -N -L 8000:localhost:8000 <user>@<host>
      - CHEETAH 에서 vllm serve 가 실행 중인지 확인

원인은 정확하다. 그런데 **GPU 가 아예 없는 사람에게는 다음 행동이 없다.** 답은
바로 위 드롭다운('연습용 — 저장된 정답 사용')에 있는데 화면이 그 얘기를 하지
않는다. 인수인계받은 사람이 처음 부딪히는 벽이 여기다(2026-09-23).

## 고친 방향과 지키는 선

연결 실패 사유 **뒤에** 안내를 덧붙인다. 세 가지를 지킨다.

1. **mock 으로 대신 돌려 주지 않는다.** 조용한 폴백은 이 도구에서 가장 위험한
   실패다 — 아무 추론도 하지 않은 리포트가 실제 결과처럼 보인다
   (`llm/factory.py` 의 약속). 고르는 것은 사람이다.
2. **무엇을 고르는 것인지 함께 적는다.** 연습용은 저장된 정답을 쓰므로 배관은
   증명해도 추출 정확도는 증명하지 못한다. 그 말을 빼고 권하면 연습용으로 낸
   수치가 실측으로 보고되는 길을 화면이 열어 주는 셈이다.
3. **연결 실패 사유를 덮지 않는다.** 터널이 안 열린 것뿐인 사람에게는 원래 안내가
   맞는 답이다. 덧붙이는 것이지 바꾸는 것이 아니다.
"""

from __future__ import annotations

import pytest

from prova.server.app import _NO_GPU_HINT, _backend


class _Boom:
    """make_llm 이 BackendError 를 내는 상황을 만든다."""


@pytest.fixture
def broken_vllm(monkeypatch):
    from prova.llm.factory import BackendError
    from prova.server import app as server_app

    def fake_make_llm(name, cfg, pdf):
        raise BackendError(
            "vLLM 서버에 연결할 수 없습니다: http://localhost:8000/v1\n"
            "  - SSH 터널이 열려 있는지 확인\n  원인: Connection error."
        )

    monkeypatch.setattr(server_app, "make_llm", fake_make_llm)


def _error_text(backend: str) -> str:
    with pytest.raises(RuntimeError) as got:
        _backend(backend, {}, None, lambda msg: None)
    return str(got.value)


class TestHint:
    def test_연결_실패_사유를_그대로_남긴다(self, broken_vllm):
        """터널만 안 열린 사람에게는 원래 안내가 맞는 답이다."""
        text = _error_text("vllm")
        assert "vLLM 서버에 연결할 수 없습니다" in text
        assert "SSH 터널" in text

    def test_다음에_할_수_있는_것을_알려_준다(self, broken_vllm):
        text = _error_text("vllm")
        assert "연습용" in text, "화면의 드롭다운에 답이 있는데 말해 주지 않았다"

    def test_연습용이_증명하지_못하는_것을_함께_적는다(self, broken_vllm):
        """권하기만 하고 한계를 빼면, 연습용 수치가 실측으로 보고되는 길이 열린다."""
        text = _error_text("vllm")
        assert "추출" in text and "증명하지 못" in text

    def test_mock_으로_조용히_돌려_주지_않는다(self, broken_vllm):
        """안내는 하되 대신 실행하지 않는다 — 고르는 것은 사람이다."""
        text = _error_text("vllm")
        assert "바꿔" in text or "바꾸" in text, "사람이 고르라는 말이어야 한다"

    def test_mock_백엔드의_실패에는_붙이지_않는다(self, broken_vllm):
        """이미 연습용을 고른 사람에게 연습용을 권하면 길이 막힌다."""
        text = _error_text("mock")
        assert _NO_GPU_HINT not in text
