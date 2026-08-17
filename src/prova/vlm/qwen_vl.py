"""vLLM 이 서빙하는 시각-언어 모델 백엔드 (OpenAI 호환 chat/completions + 이미지).

## 왜 별도 서버 주소인가

LLM 과 다른 포트를 쓴다. 같은 vLLM 프로세스는 모델 하나만 서빙하고, 우리는 텍스트
7B 와 시각 모델을 둘 다 쓴다. 코드 입장에서는 base_url 이 다른 두 서버다.

**GPU 에서 두 모델이 함께 올라갈 수 있는지는 아직 실측하지 않았다.** 10GiB MIG 조각에
Qwen2.5-7B-AWQ 가 약 5.6GB 를 쓰므로 3B 급 4bit 모델(약 2GB)이 들어갈 여지가 있어
보이지만, vLLM 은 기본으로 GPU 메모리의 90% 를 미리 잡는다(gpu_memory_utilization).
둘을 함께 올리려면 양쪽 값을 낮춰야 하고, 그 조정이 이미 동작하는 7B 서빙을 건드린다.
그래서 이 파일은 **주소만 다르면 붙는 형태**로 두고, 실측은 별도 단계로 남긴다.

## 좌표 규약을 이 파일이 흡수한다

Qwen2.5-VL 계열은 리사이즈된 이미지 기준 **절대 픽셀**로 bbox 를 낸다. 그런데 리사이즈
크기는 모델 전처리가 정하므로 호출자가 알 수 없다. 그래서 프롬프트로 **0~1 상대값**을
요구하고, 받은 값이 1 보다 크면 픽셀로 낸 것으로 보고 이미지 크기로 나눈다.

정규화를 프롬프트에 맡기는 것이 못마땅하지만, 대안은 모델별 리사이즈 규칙을 여기에
복제하는 것이다. 그건 모델을 바꿀 때마다 틀린다. 대신 받은 값이 화면 안에 있는지를
Located.is_sane() 이 확인하고, 벗어나면 보정을 포기한다 — 이상한 좌표로 아무 데나
누르는 것보다 못 찾았다고 말하는 편이 낫다.
"""

from __future__ import annotations

import base64
import json
import re

import httpx

from prova.vlm.base import Located, VLMError

_SYSTEM = """\
당신은 웹 화면 스크린샷에서 UI 요소의 위치를 찾는 도구입니다.
찾은 요소를 감싸는 사각형을 JSON 으로만 답하세요.

{"bbox": [x1, y1, x2, y2], "confidence": 0.0~1.0}

좌표는 **이미지 왼쪽 위를 (0, 0), 오른쪽 아래를 (1, 1) 로 두는 상대값**입니다.
픽셀 값을 쓰지 마세요.

요소를 찾지 못했으면 confidence 를 0.0 으로 두세요. 그럴듯한 위치를 지어내지 마세요 —
엉뚱한 곳을 누르면 그 뒤의 판정이 전부 무의미해집니다.
"""

_BBOX_SCHEMA = {
    "title": "Located",
    "type": "object",
    "properties": {
        "bbox": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 4,
            "maxItems": 4,
        },
        "confidence": {"type": "number"},
    },
    "required": ["bbox", "confidence"],
}


class QwenVLClient:
    """vLLM 의 OpenAI 호환 엔드포인트로 시각 모델을 부른다."""

    name = "vllm-vl"

    def __init__(
        self,
        base_url: str = "http://localhost:8001/v1",
        model: str = "Qwen/Qwen2.5-VL-3B-Instruct-AWQ",
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def health(self, timeout: float = 4.0) -> None:
        """서버가 살아 있는지. 없으면 즉시 알린다 — 조용히 넘어가면 안 된다."""
        try:
            r = httpx.get(f"{self.base_url}/models", timeout=timeout)
            r.raise_for_status()
        except Exception as exc:
            raise VLMError(f"VLM 서버에 연결할 수 없습니다 ({self.base_url}): {exc}")

    def locate(self, *, image_png: bytes, target: str, hint: str = "") -> Located:
        what = f"{target} ({hint})" if hint else target
        data_uri = "data:image/png;base64," + base64.b64encode(image_png).decode()

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}},
                    {"type": "text", "text": f"이 화면에서 '{what}' 의 위치를 찾으세요."},
                ]},
            ],
            "max_tokens": 128,
            "temperature": 0.0,
            # LLM 쪽과 같은 이유로 정형 출력을 강제한다. 좌표를 문장 속에서 정규식으로
            # 긁어내면 모델이 말투를 바꿀 때마다 깨진다.
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "Located",
                                                "schema": _BBOX_SCHEMA}},
        }

        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=payload,
                           timeout=self.timeout)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            raise VLMError(f"VLM 호출 실패: {exc}")

        return _parse(content, image_png)


def _parse(content: str, image_png: bytes) -> Located:
    """응답에서 bbox 를 뽑고 0~1 상대값으로 맞춘다."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # 정형 출력이 조용히 무시되는 백엔드도 있다(guided_json 이 그랬다).
        # 마지막 방어선으로 JSON 객체만 긁어낸다.
        match = re.search(r"\{.*\}", content, re.S)
        if not match:
            raise VLMError(f"응답에서 JSON 을 찾을 수 없습니다: {content[:120]!r}")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise VLMError(f"JSON 파싱 실패: {exc}")

    raw = data.get("bbox")
    if not isinstance(raw, list) or len(raw) != 4:
        raise VLMError(f"bbox 가 없거나 형식이 다릅니다: {data!r}")

    values = [float(v) for v in raw]
    if any(v > 1.0 for v in values):
        # 픽셀로 낸 것으로 본다. 이미지 크기로 나눈다.
        width, height = _png_size(image_png)
        values = [values[0] / width, values[1] / height,
                  values[2] / width, values[3] / height]

    return Located(
        bbox=(values[0], values[1], values[2], values[3]),
        confidence=float(data.get("confidence", 1.0)),
    )


def _png_size(data: bytes) -> tuple[int, int]:
    """PNG 헤더에서 크기를 읽는다. Pillow 없이 되는 일이라 의존을 늘리지 않는다."""
    if len(data) < 24 or data[12:16] != b"IHDR":
        raise VLMError("PNG 헤더를 읽을 수 없습니다")
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    if not width or not height:
        raise VLMError("PNG 크기가 0 입니다")
    return width, height
