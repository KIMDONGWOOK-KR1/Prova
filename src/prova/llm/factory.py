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

        # UI 는 어느 기획서를 고를지 모른 채 mock 을 만든다 — 화면이 여럿인
        # 문서(상품등록·주문조회처럼 전제 화면을 같이 담는 것)도 열릴 수 있다.
        # 화면 ID 정확 매칭이 있으므로(for_spec 참고) 골든 전부를 등록해도
        # 오염되지 않는다.
        return MockLLM.for_spec(pdf), [
            "mock 백엔드로 실행합니다 — 설계 문서 추출에 실제 모델을 쓰지 않습니다."
        ]

    if backend == "vllm":
        from prova.llm.base import LLMError
        from prova.llm.vllm_backend import DEFAULT_BASE_URL, DEFAULT_MODEL, VLLMClient

        client = VLLMClient(
            base_url=llm_cfg.get("base_url", DEFAULT_BASE_URL),
            model=llm_cfg.get("model", DEFAULT_MODEL),
            timeout=float(llm_cfg.get("timeout", 180)),
        )
        try:
            client.health()  # 실행 전에 연결을 확인한다
        except LLMError as exc:
            # docstring 의 약속(연결 실패 = BackendError)을 지킨다. CLI 와 서버가
            # 각자 다른 예외를 잡고 있으면 한쪽만 고쳐진다.
            raise BackendError(str(exc)) from exc
        return client, []

    raise BackendError(f"지원하지 않는 백엔드: {backend} (vllm | mock)")
