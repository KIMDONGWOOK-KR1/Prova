"""백엔드 생성 한 곳 — CLI 와 웹 UI 가 같은 규칙을 쓴다.

## 왜 떼어냈는가

CLI 와 서버가 각자 백엔드를 만들면 '조용히 폴백하지 않는다' 같은 규칙이 한쪽에만
남는다. 이 프로젝트가 반복해서 잡아 온 실패 모양이다 — 있는 것과 동작하는 것은
다르고, 두 벌로 갈라진 규칙은 한쪽이 반드시 뒤처진다.

## 경고를 출력하지 않고 돌려준다

여기서 print 하면 웹 UI 는 그 경고를 화면에 띄울 방법이 없다. 무엇을 알려야
하는지는 이 모듈이 알고, 어떻게 보여줄지는 부르는 쪽이 정한다.
"""

from __future__ import annotations

from pathlib import Path


class BackendError(RuntimeError):
    """백엔드를 준비할 수 없는 상태 (지원하지 않는 이름, 연결 실패 등)."""


def make_llm(backend: str, cfg: dict, pdf: Path | str) -> tuple[object, list[str]]:
    """설정에 맞는 LLM 백엔드를 만든다.

    Args:
        backend: "vllm" | "mock"
        cfg: configs/default.yaml 를 읽은 dict
        pdf: 검증할 기획서 경로. mock 은 그 옆의 골든을 정답으로 쓴다.

    Returns:
        (백엔드, 사용자에게 보여야 할 경고 목록)

    Raises:
        BackendError: 지원하지 않는 이름이거나 연결에 실패했을 때. **mock 으로
            조용히 넘어가지 않는다** — 아무 추론도 하지 않은 리포트가 정상 결과처럼
            보이는 것이 이 도구에서 가장 위험한 실패다.
    """
    llm_cfg = cfg.get("llm", {})

    if backend == "mock":
        from prova.llm.mock_backend import MockLLM

        return MockLLM.for_spec(pdf), [
            "mock 백엔드로 실행합니다 — 설계 문서 추출에 실제 모델을 쓰지 않습니다."
        ]

    if backend == "vllm":
        from prova.llm.vllm_backend import VLLMClient

        client = VLLMClient(
            base_url=llm_cfg.get("base_url", "http://localhost:8000/v1"),
            model=llm_cfg.get("model", "Qwen/Qwen2.5-7B-Instruct-AWQ"),
            timeout=float(llm_cfg.get("timeout", 180)),
        )
        client.health()  # 실행 전에 연결을 확인한다
        return client, []

    raise BackendError(f"지원하지 않는 백엔드: {backend} (vllm | mock)")
