"""vLLM 백엔드 — CHEETAH GPU 서버의 로컬 모델을 호출한다.

## 접속 구조

    [CHEETAH A100 MIG 1g.10gb]              [로컬 개발 머신]
     vLLM (Qwen2.5-7B-Instruct-AWQ)  <--SSH 터널-->  Prova
     OpenAI 호환 :8000                                Playwright

로컬에서 다음 명령으로 터널을 열어두면, 코드 입장에서 GPU 모델은 그냥
http://localhost:8000/v1 이다.

    ssh -N -L 8000:localhost:8000 <user>@<cheetah-host>

GPU 서버에 브라우저를 설치할 필요가 없고, Playwright 는 로컬에서 돌아간다.

## 정형 출력은 response_format(json_schema) 으로 건다

OpenAI 표준인 response_format={"type":"json_schema", ...} 를 쓴다. 스키마를 벗어난
토큰이 생성 단계에서 차단되므로 7B 급 모델도 JSON 을 깨뜨리지 않는다. 이게 없으면
재프롬프트 루프 구현과 디버깅에 개발 시간을 다 쓰게 된다.

vLLM 확장인 guided_json 을 쓰지 않는 이유: vLLM 0.24 에서 제거됐다. 실제로
extra_body={"guided_json": ...} 로 보내면 **오류 없이 조용히 무시된다** — 요청한
필드명(screen_name)이 아니라 모델이 지어낸 이름(screenName)이 돌아오고 응답이
마크다운 코드펜스로 감싸진다. QA 도구에서 이런 무성 실패는 위험하다. 스키마가
강제되지 않으면 S1 이 constraints 키를 흔들고, 그러면 rule_expander 가 규칙을
인식하지 못해 검증이 조용히 무력해진다.

response_format 은 OpenAI 표준이라 vLLM 버전이 올라가도 유지될 가능성이 높고,
Claude API 백엔드를 붙일 때도 같은 개념을 쓴다.

## VRAM 10GiB 에서의 서빙 명령

    vllm serve Qwen/Qwen2.5-7B-Instruct-AWQ \
      --quantization awq_marlin \
      --max-model-len 8192 \
      --gpu-memory-utilization 0.90 \
      --port 8000

가중치 약 5.6GB + 오버헤드 약 1GB 를 빼면 KV 캐시로 약 2.4GB 가 남는다.
Qwen2.5-7B 는 GQA(KV head 4개, 28 layer)라 토큰당 KV 가 약 56KB 이므로
대략 43K 토큰 분량이다. 8K 컨텍스트 요청 5개를 동시에 처리할 수 있다.
"""

from __future__ import annotations

import json

from prova.llm.base import LLMError

DEFAULT_BASE_URL = "http://localhost:8000/v1"
DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct-AWQ"


class VLLMClient:
    """OpenAI 호환 엔드포인트로 로컬 모델을 호출한다."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        api_key: str = "not-needed",
        timeout: float = 180.0,
        max_retries: int = 1,
    ) -> None:
        from openai import OpenAI  # 지연 import — mock 만 쓸 때 부담을 주지 않는다

        self.name = f"vllm:{model}"
        self.model = model
        self.base_url = base_url
        # max_retries 를 기본 2 에서 1 로 줄인다. 서버가 아예 없을 때(터널이
        # 닫힘, vllm serve 미실행) 재시도는 실패를 늦게 알리는 것 말고 하는 일이
        # 없다. 실패를 빨리 알리는 편이 낫다.
        self._client = OpenAI(
            base_url=base_url, api_key=api_key, timeout=timeout, max_retries=max_retries
        )

    def health(self, timeout: float = 10.0) -> str:
        """서버가 살아 있는지, 어떤 모델이 올라와 있는지 확인한다.

        파이프라인을 돌리기 전에 이걸 먼저 호출한다. 실행 도중 연결 실패로
        죽으면 어디까지 진행됐는지 파악하기 어렵기 때문이다.

        추론용 타임아웃(기본 180초)과 따로 짧은 값을 쓴다. 살아 있는 서버는
        모델 목록을 즉시 돌려주므로, 오래 기다리는 것은 '서버가 없다' 를 늦게
        아는 것에 불과하다.
        """
        try:
            models = self._client.with_options(timeout=timeout).models.list()
        except Exception as exc:
            raise LLMError(
                f"vLLM 서버에 연결할 수 없습니다: {self.base_url}\n"
                f"  - SSH 터널이 열려 있는지 확인: ssh -N -L 8000:localhost:8000 <user>@<host>\n"
                f"  - CHEETAH 에서 vllm serve 가 실행 중인지 확인\n"
                f"  원인: {exc}"
            ) from exc
        available = [m.id for m in models.data]
        if self.model not in available:
            raise LLMError(
                f"요청한 모델 '{self.model}' 이 서버에 없습니다. 사용 가능: {available}"
            )
        return self.model

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> dict:
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        # 이름은 서버 로그와 디버깅에만 쓰인다. pydantic 스키마의
                        # title(모델 클래스명)을 그대로 넘겨 어느 단계의 호출인지
                        # 알 수 있게 한다.
                        "name": schema.get("title") or "Output",
                        "schema": schema,
                    },
                },
            )
        except Exception as exc:
            raise LLMError(f"vLLM 호출 실패: {exc}") from exc

        content = (resp.choices[0].message.content or "").strip()
        if not content:
            raise LLMError(
                "vLLM 이 빈 응답을 반환했습니다. max_tokens 가 너무 작아 생성이 "
                f"중간에 끊겼을 수 있습니다 (현재 {max_tokens})."
            )
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            # guided_json 이 걸려 있으면 이 경로는 거의 오지 않는다. 왔다면
            # 스키마가 서버에서 무시된 것이므로 설정 문제를 의심해야 한다.
            raise LLMError(
                f"JSON 파싱 실패 — guided_json 이 적용되지 않았을 수 있습니다.\n"
                f"  응답 앞부분: {content[:200]}\n  원인: {exc}"
            ) from exc
