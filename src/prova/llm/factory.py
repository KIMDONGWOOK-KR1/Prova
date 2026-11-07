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


def make_llm(backend: str, cfg: dict, pdf: Path | str, cache: bool = False,
             cache_read: bool = True) -> tuple[object, list[str]]:
    """설정에 맞는 LLM 백엔드를 만든다.

    Args:
        backend: "vllm" | "mock"
        cfg: configs/default.yaml 를 읽은 dict
        pdf: 검증할 기획서 경로. mock 은 그 옆의 골든을 정답으로 쓴다.
        cache: 모델 응답 캐시(llm.cache_dir)를 쓴다. 기본은 끈다 — 측정 스크립트가 모르는
            새 옛 답을 재면 안 된다. 제품 입구(CLI·웹 UI)만 켠다 (llm/cache.py).
        cache_read: False 면 저장된 답을 읽지 않고 새로 묻는다 (--no-cache).

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
        mock = MockLLM.for_spec(pdf)
        # 제목 다듬기는 비워 돌려준다 — 규칙 기반 제목이 그대로 쓰인다. 등록하지
        # 않으면 매 실행 끝에 '설계 문서 경고' 가 떠서, 문제없는 기획서를 의심하게
        # 만든다. (테스트가 쓰는 맨 MockLLM 은 그대로 오류를 낸다 — 그 경로를 잰다.)
        mock.register("CaseTitles", {"titles": []})
        return mock, [
            "mock 백엔드로 실행합니다 — 설계 문서 추출에 실제 모델을 쓰지 않습니다."
        ]

    if backend == "replay":
        return _replay(llm_cfg), [
            "replay 백엔드로 실행합니다 — 모델 서버 없이, 전에 실모델이 낸 응답(캐시)을 다시 "
            "씁니다. 저장된 응답이 없는 기획서·프롬프트는 실패합니다."
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
        if cache and llm_cfg.get("cache_dir"):
            from prova.llm.cache import CachedLLM

            return CachedLLM(client, llm_cfg["cache_dir"], read=cache_read), []
        return client, []

    raise BackendError(f"지원하지 않는 백엔드: {backend} (vllm | mock | replay)")


class _NoServer:
    """replay 의 안쪽 — 모델 서버가 없다. 캐시에 없는 질문은 여기서 실패한다."""

    def __init__(self, model: str) -> None:
        self.model = model
        # 캐시 키가 이 이름을 쓴다(cache.py) — vllm 백엔드와 같아야 그 답을 찾는다.
        self.name = f"vllm:{model}"
        self.base_url = ""

    def complete_json(self, **request) -> dict:
        from prova.llm.base import LLMError

        raise LLMError(
            "저장된 모델 응답이 없습니다 — replay 는 모델 서버 없이 전에 받은 응답만 씁니다. "
            "이 기획서를 GPU 가 있을 때 vllm 백엔드로 한 번 돌려 두어야 합니다(기획서나 "
            "추출 프롬프트가 그 뒤 바뀌었어도 다시 돌려야 합니다)."
        )


def _replay(llm_cfg: dict):
    """모델 서버 없이 캐시만으로 도는 백엔드 — GPU 반납 뒤 시연·재현용 (2026-11-13).

    vllm 백엔드와 같은 키로 캐시를 찾으므로 그때 받은 답이 글자 그대로 쓰인다. 리포트의
    백엔드 이름은 'replay:' 로 시작해, 이번 실행이 모델을 부르지 않았다는 사실을 남긴다.
    """
    from prova.llm.cache import CachedLLM
    from prova.llm.vllm_backend import DEFAULT_MODEL

    if not llm_cfg.get("cache_dir"):
        raise BackendError("replay 는 llm.cache_dir 에 저장된 응답이 필요합니다 — 설정에 없습니다.")
    inner = _NoServer(llm_cfg.get("model", DEFAULT_MODEL))
    cached = CachedLLM(inner, llm_cfg["cache_dir"], read=True)
    cached.name = f"replay:{inner.name}"
    return cached
