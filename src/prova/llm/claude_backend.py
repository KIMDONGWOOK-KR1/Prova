"""Claude API 백엔드 — 로컬 모델과 같은 프롬프트·스키마로 외부 API 를 부른다.

## 왜 있는가

운영 계획서의 성과 지표 6 '로컬 모델 vs 외부 API' 를 재기 위해서다(2026-11-10). 제품의
기본 경로는 여전히 로컬(vLLM)이다 — 기업은 계정·보안 자료를 외부 생성형 AI 에 올리지
못한다. 이 백엔드는 **공개 자료로 비교 측정할 때만** 쓴다. 실물 기획서를 여기로 보내지
않는다.

## 정형 출력

`output_config.format`(json_schema)으로 건다. vLLM 의 response_format 과 같은 일을 한다 —
스키마를 벗어난 출력이 생성 단계에서 막힌다. 다만 Claude 는 스키마 문법을 더 좁게 받는다
(모든 객체에 additionalProperties: false, 길이·범위 제약 미지원). SDK 의
`transform_schema` 가 그 차이를 메운다: 못 받는 제약은 설명 글로 옮기고 형태는 유지한다.
옮겨진 제약은 강제되지 않으므로 pydantic 검증(호출자)이 마지막 관문이다.

**자유 형태 객체는 JSON 문자열로 주고받는다.** 키를 미리 정하지 않은 객체(S1 의
`constraints`, `given`, 씨앗 표의 행)는 Claude 의 정형 출력이 표현하지 못한다 —
`transform_schema` 가 '속성 없는 닫힌 객체' 로 바꿔 **항상 빈 객체가 돌아온다**. 오류 없이
규칙이 통째로 사라지는 무성 실패다(2026-11-10 첫 측정에서 검증 규칙이 전부 `{}` 로 나와
잡았다). 그래서 그 자리를 문자열로 바꿔 보내고, 받은 뒤 다시 객체로 푼다.

## 로컬 백엔드와 다른 점 두 가지

- **temperature 를 보내지 않는다.** 최신 Claude 모델은 표본 추출 파라미터를 거절한다(400).
  재현성은 로컬의 temperature 0 만큼 보장되지 않는다 — 비교 문서에 적는다.
- **max_tokens 에 여유를 더한다.** 이 모델들은 생각(thinking)이 항상 켜져 있고 생각
  토큰이 max_tokens 에 포함된다. 로컬용 한도(수천)를 그대로 쓰면 JSON 이 나오기 전에
  잘린다. 호출자가 준 한도는 '출력 JSON 의 크기' 로 읽고, 그 위에 생각 몫을 얹는다.

거절(refusal) 때 다른 모델로 넘기는 서버 쪽 fallback 은 켜지 않는다. 이 백엔드는 '어느
모델이 무엇을 냈는지' 를 재는 데 쓰므로, 조용히 다른 모델의 답이 섞이면 측정이 거짓이 된다.
"""

from __future__ import annotations

import json

from prova.llm.base import LLMError, OutputTruncated

DEFAULT_MODEL = "claude-opus-5-5"
#: 생각 토큰 몫. 호출자의 max_tokens(출력 JSON 크기) 위에 얹는다.
THINKING_HEADROOM = 12000


_FREE_FORM_NOTE = (
    "JSON 객체를 **문자열 하나로** 적는다 (예: {\"min_length\": 8}). 해당 없으면 {} ."
)


def _is_free_form(node: dict) -> bool:
    """키를 미리 정하지 않은 객체인가 — 속성 목록이 없고 임의 키를 받는다."""
    return (
        node.get("type") == "object"
        and not node.get("properties")
        and node.get("additionalProperties", True) is not False
    )


def _stringify_free_form(node):
    """자유 형태 객체 자리를 JSON 문자열 자리로 바꾼 스키마 사본을 만든다."""
    if isinstance(node, list):
        return [_stringify_free_form(item) for item in node]
    if not isinstance(node, dict):
        return node
    if _is_free_form(node):
        described = " ".join(filter(None, [node.get("description"), _FREE_FORM_NOTE]))
        value_schema = node.get("additionalProperties")
        if isinstance(value_schema, dict) and value_schema.get("type"):
            described += f" 값은 모두 {value_schema['type']} 이다."
        return {"type": "string", "description": described}
    return {key: _stringify_free_form(value) for key, value in node.items()}


def _restore_free_form(value, node: dict, defs: dict):
    """원래 스키마를 따라 내려가며, 문자열로 받은 자유 형태 객체를 객체로 되돌린다."""
    if not isinstance(node, dict):
        return value
    if "$ref" in node:
        return _restore_free_form(value, defs.get(node["$ref"].rsplit("/", 1)[-1], {}), defs)
    if _is_free_form(node):
        if not isinstance(value, str):
            return value
        try:
            parsed = json.loads(value) if value.strip() else {}
        except json.JSONDecodeError as exc:
            raise LLMError(f"자유 형태 객체를 JSON 으로 읽을 수 없습니다: {value[:120]!r}") from exc
        if not isinstance(parsed, dict):
            raise LLMError(f"자유 형태 객체 자리에 객체가 아닌 값이 왔습니다: {value[:120]!r}")
        return parsed
    for key in ("anyOf", "oneOf", "allOf"):
        for option in node.get(key, ()):
            value = _restore_free_form(value, option, defs)
    if isinstance(value, dict):
        properties = node.get("properties", {})
        return {k: _restore_free_form(v, properties.get(k, {}), defs) for k, v in value.items()}
    if isinstance(value, list):
        return [_restore_free_form(item, node.get("items", {}), defs) for item in value]
    return value


class ClaudeClient:
    """Anthropic Messages API 로 스키마를 강제한 JSON 한 건을 받는다."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        effort: str = "medium",
        timeout: float = 300.0,
        max_retries: int = 2,
    ) -> None:
        import anthropic  # 지연 import — 로컬 백엔드만 쓸 때 부담을 주지 않는다

        self.name = f"claude:{model}"
        self.model = model
        self.effort = effort
        self.base_url = "https://api.anthropic.com"
        # 키는 환경 변수 ANTHROPIC_API_KEY 에서만 읽는다. 설정 파일·코드에 두지 않는다.
        self._client = anthropic.Anthropic(timeout=timeout, max_retries=max_retries)
        #: 마지막 호출의 토큰 사용량 — 비용 측정용 (llm/metered.py 가 읽는다).
        self.last_usage: dict[str, int] = {}

    def health(self, timeout: float = 15.0) -> str:
        """키가 유효하고 모델이 있는지 확인한다 (과금되지 않는 모델 조회)."""
        import anthropic

        try:
            self._client.with_options(timeout=timeout).models.retrieve(self.model)
        except anthropic.AuthenticationError as exc:
            raise LLMError(
                "Claude API 인증에 실패했습니다 — 환경 변수 ANTHROPIC_API_KEY 를 확인하세요."
            ) from exc
        except anthropic.NotFoundError as exc:
            raise LLMError(f"Claude API 에 모델 '{self.model}' 이 없습니다.") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"Claude API 에 연결할 수 없습니다: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Claude API 확인 실패({exc.status_code}): {exc.message}") from exc
        except Exception as exc:  # 키가 아예 없으면 SDK 가 요청 전에 일반 예외를 낸다
            raise LLMError(f"Claude API 를 준비할 수 없습니다: {exc}") from exc
        return self.model

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict,
        max_tokens: int = 2048,
        temperature: float = 0.0,  # 받기만 한다 — 위 모듈 설명 참고
    ) -> dict:
        import anthropic

        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens + THINKING_HEADROOM,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={
                    "effort": self.effort,
                    "format": {
                        "type": "json_schema",
                        "schema": anthropic.transform_schema(_stringify_free_form(schema)),
                    },
                },
            )
        except anthropic.RateLimitError as exc:
            raise LLMError(f"Claude API 호출 한도에 걸렸습니다: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Claude API 호출 실패({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"Claude API 에 연결할 수 없습니다: {exc}") from exc

        usage = resp.usage
        self.last_usage = {
            "input_tokens": int(usage.input_tokens or 0),
            "output_tokens": int(usage.output_tokens or 0),
        }
        if resp.stop_reason == "refusal":
            raise LLMError("Claude 가 이 요청을 거절했습니다(stop_reason=refusal).")
        text = next((b.text for b in resp.content if b.type == "text"), "").strip()
        if resp.stop_reason == "max_tokens":
            raise OutputTruncated(
                f"모델 출력이 max_tokens({max_tokens}+{THINKING_HEADROOM})에서 잘렸습니다 "
                f"(응답 {len(text)}자)."
            )
        if not text:
            raise LLMError("Claude 가 빈 응답을 반환했습니다.")
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(
                f"JSON 파싱 실패 — 정형 출력이 적용되지 않았을 수 있습니다.\n"
                f"  응답 앞부분: {text[:200]}\n  원인: {exc}"
            ) from exc
        return _restore_free_form(raw, schema, schema.get("$defs", {}))
