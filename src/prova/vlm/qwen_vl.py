"""vLLM 이 서빙하는 시각-언어 모델 백엔드 (OpenAI 호환 chat/completions + 이미지).

## 기본값은 LLM 과 같은 서버다 (2026-09-28 부터)

Qwen3.5-4B 가 추출(S1)과 요소 탐지를 함께 맡는다 — 기본 주소·이름이 LLM 과 같다
(`llm.vllm_backend.DEFAULT_MODEL`). 그 전에는 텍스트 7B 와 Qwen2.5-VL-3B 가 MIG
조각에 함께 올라가지 않아 포트 8001 의 VL 서버로 번갈아 띄웠다. 주소·이름·좌표
규약을 인자로 받으므로 옛 VL 서버에도 그대로 붙는다(`coords="pixel"`).

## 좌표 규약을 이 파일이 흡수한다

Qwen2.5-VL 계열은 리사이즈된 이미지 기준 **절대 픽셀**로 bbox 를 낸다. 그런데 리사이즈
크기는 모델 전처리가 정하므로 호출자가 알 수 없다. 그래서 프롬프트로 **0~1 상대값**을
요구하고, 받은 값이 1 보다 크면 픽셀로 낸 것으로 보고 이미지 크기로 나눈다.

정규화를 프롬프트에 맡기는 것이 못마땅하지만, 대안은 모델별 리사이즈 규칙을 여기에
복제하는 것이다. 그건 모델을 바꿀 때마다 틀린다. 대신 받은 값이 화면 안에 있는지를
Located.is_sane() 이 확인하고, 벗어나면 보정을 포기한다 — 이상한 좌표로 아무 데나
누르는 것보다 못 찾았다고 말하는 편이 낫다.

### 규약을 섞어 내는 모델 — `coords="norm1000"`

Qwen3.5 는 0~1 을 달라는 프롬프트에도 한 화면 안에서 0~1 과 0~1000 을 섞어 냈다
(2026-09-28). 위 규칙은 그 0~1000 값을 픽셀로 보고 1280 으로 나눠 365 -> 0.285
(정답 0.367)를 만들고, 그 값이 화면 안이라 is_sane() 도 통과한다 — **엉뚱한 곳을
조용히 누른다.** 그런 모델에는 학습된 규약(0~1000 정수)을 프롬프트로 명시하고,
받은 값은 추측 없이 전부 1000 으로 나눈다. 규약을 정했으면 섞어 읽지 않는다.
"""

from __future__ import annotations

import base64
import json
import re

import httpx

from prova.llm.vllm_backend import DEFAULT_BASE_URL, DEFAULT_MODEL

from prova.vlm.base import Located, VLMError

_COORD_RULES = {
    "pixel": "좌표는 **이미지 왼쪽 위를 (0, 0), 오른쪽 아래를 (1, 1) 로 두는 상대값**입니다.\n"
             "픽셀 값을 쓰지 마세요.",
    "norm1000": "좌표는 **이미지 왼쪽 위를 (0, 0), 오른쪽 아래를 (1000, 1000) 으로 두는 "
                "0~1000 정수**입니다.\n픽셀 값이나 0~1 소수를 쓰지 마세요.",
}

_SYSTEM = """\
당신은 웹 화면 스크린샷에서 UI 요소의 위치를 찾는 도구입니다.
찾은 요소를 감싸는 사각형을 JSON 으로만 답하세요.

{{"bbox": [x1, y1, x2, y2], "confidence": 0.0~1.0}}

{coord_rule}

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
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 120.0,
        coords: str = "norm1000",
    ) -> None:
        if coords not in _COORD_RULES:
            raise ValueError(f"좌표 규약은 {sorted(_COORD_RULES)} 중 하나: {coords!r}")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.coords = coords
        self.system_prompt = _SYSTEM.format(coord_rule=_COORD_RULES[coords])

    def health(self, timeout: float = 4.0) -> None:
        """서버가 살아 있고 **이 모델 이름을 서빙하는지** 확인한다.

        서버 연결만 보면 부족하다. vLLM 은 `--served-model-name` 으로 임의의 이름을
        쓸 수 있고, 이름이 다르면 /models 는 200 을 주는데 모든 chat/completions
        요청이 실패한다. 그러면 locate() 마다 VLMError 가 나고, 호출부는 그것을
        탐지 실패로 되돌리므로 **리포트는 "요소를 못 찾았다" 로만 보인다.**

        실제로 겪었다. `--served-model-name qwen-vl` 로 띄운 서버에 기본 모델
        이름으로 요청해서 2차 경로가 통째로 죽었는데, 실행 로그에는 '2차 경로:
        vllm-vl @ ...' 이 찍혀 있었다. 켰다고 믿는 실행이 실제로는 1차 경로였다.

        이름 불일치는 기동 시점에 알 수 있는 사실이므로 여기서 끊는다.
        """
        try:
            r = httpx.get(f"{self.base_url}/models", timeout=timeout)
            r.raise_for_status()
            served = [m["id"] for m in r.json().get("data", [])]
        except Exception as exc:
            raise VLMError(f"VLM 서버에 연결할 수 없습니다 ({self.base_url}): {exc}")

        if self.model not in served:
            raise VLMError(
                f"VLM 서버가 '{self.model}' 을 서빙하지 않습니다. "
                f"서빙 중: {served or '(없음)'} — --vlm-model 로 이름을 맞추세요."
            )

    def locate(self, *, image_png: bytes, target: str, hint: str = "") -> Located:
        what = f"{target} ({hint})" if hint else target
        data_uri = "data:image/png;base64," + base64.b64encode(image_png).decode()

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
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
            # LLM 쪽(vllm_backend)과 같은 이유 — 좌표 하나 내는 데 추론이 필요 없다.
            "chat_template_kwargs": {"enable_thinking": False},
        }

        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=payload,
                           timeout=self.timeout)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            raise VLMError(f"VLM 호출 실패: {exc}")

        return _parse(content, image_png, coords=self.coords)


def _parse(content: str, image_png: bytes, coords: str = "pixel") -> Located:
    """응답에서 bbox 를 뽑고 0~1 상대값으로 맞춘다."""
    if coords not in _COORD_RULES:
        raise VLMError(f"모르는 좌표 규약: {coords!r}")
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
    if coords == "norm1000":
        values = [v / 1000.0 for v in values]
    elif any(v > 1.0 for v in values):
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
