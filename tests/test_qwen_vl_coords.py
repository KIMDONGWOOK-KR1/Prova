"""VLM 응답 좌표를 0~1 로 맞추는 규약 (2026-09-28, Qwen3.5-4B 스파이크).

Qwen3.5 는 0~1 상대값을 달라는 프롬프트에도 한 화면 안에서 0~1 과 0~1000 을
섞어 냈다. 1 보다 크면 픽셀로 보고 이미지 크기(1280x800)로 나누는 기존 규칙은
365 -> 0.285(정답 0.367)를 만들고, 그 값이 화면 안이라 is_sane() 을 통과한다 —
엉뚱한 곳을 조용히 누른다. 모델이 학습된 규약을 명시해 받는다.
"""

from __future__ import annotations

import struct
import zlib

import pytest

from prova.vlm.base import VLMError
from prova.vlm.qwen_vl import QwenVLClient, _parse


def _png(w: int, h: int) -> bytes:
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr
            + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr)))


PNG = _png(1280, 800)


class TestPixel:
    """기존 규약(Qwen2.5-VL) — 동작이 바뀌지 않아야 한다."""

    def test_상대값은_그대로(self):
        got = _parse('{"bbox": [0.1, 0.2, 0.3, 0.4], "confidence": 0.9}', PNG)
        assert got.bbox == (0.1, 0.2, 0.3, 0.4)

    def test_1보다_크면_이미지_크기로_나눈다(self):
        got = _parse('{"bbox": [640, 400, 1280, 800], "confidence": 0.9}', PNG)
        assert got.bbox == (0.5, 0.5, 1.0, 1.0)


class TestNorm1000:
    def test_0_1000_값을_1000으로_나눈다(self):
        got = _parse('{"bbox": [365, 532, 630, 580], "confidence": 0.95}', PNG,
                     coords="norm1000")
        assert got.bbox == pytest.approx((0.365, 0.532, 0.63, 0.58))

    def test_모든_값이_1_이하여도_0_1000_으로_읽는다(self):
        """규약을 정했으면 섞어 읽지 않는다. 작은 값을 상대값으로 추측하면
        화면 왼쪽 위 구석(0~1 픽셀 상당)의 요소가 화면 전체로 부풀려진다."""
        got = _parse('{"bbox": [0, 0, 1, 1], "confidence": 0.9}', PNG, coords="norm1000")
        assert got.bbox == pytest.approx((0.0, 0.0, 0.001, 0.001))

    def test_프롬프트가_0_1000_규약을_요구한다(self):
        client = QwenVLClient(coords="norm1000")
        assert "1000" in client.system_prompt
        assert "1000" not in QwenVLClient().system_prompt

    def test_모르는_규약은_거부한다(self):
        with pytest.raises(ValueError):
            QwenVLClient(coords="percent")
        with pytest.raises(VLMError):
            _parse('{"bbox": [1, 2, 3, 4], "confidence": 1}', PNG, coords="percent")
