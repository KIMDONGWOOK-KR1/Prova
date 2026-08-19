"""실행 작업 관리 — 워커 스레드 하나, 동시 실행 하나.

## 왜 스레드가 필수인가

`sync_playwright` 는 asyncio 이벤트 루프 안에서 호출할 수 없다. FastAPI 는
이벤트 루프 위에서 돌므로, 파이프라인을 요청 핸들러에서 그대로 부르면
Playwright 가 거부한다. 그래서 작업은 반드시 별도 스레드에서 돈다.

## 왜 동시 실행을 막는가

브라우저와 GPU 를 두 작업이 함께 쓰면 서로를 느리게 만들고, 더 나쁘게는
타이밍에 의존하는 판정(대기 상한)이 흔들린다. 느린 것은 참을 수 있지만
판정이 흔들리는 것은 참을 수 없다 — 이 도구가 계속 지켜 온 교환이다.

## 진행 메시지를 인덱스로 읽는 이유

큐로 만들면 화면을 새로고침한 사람은 그 전 메시지를 영영 못 본다. 목록에
쌓아 두고 "몇 번째부터" 로 읽으면 늦게 붙은 화면도 처음부터 따라올 수 있다.
"""

from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class Job:
    job_id: str
    kind: str  # "plan" | "run"
    status: str = "running"  # running | done | error
    messages: list[str] = field(default_factory=list)
    result: Any = None
    error: str = ""

    def public(self, since: int = 0) -> dict:
        """화면에 보낼 형태. since 이후의 메시지만 싣는다."""
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "status": self.status,
            "messages": self.messages[since:],
            "next": len(self.messages),
            "result": self.result,
            "error": self.error,
        }


class JobRunner:
    """한 번에 하나만 도는 작업 실행기."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._active: Optional[str] = None
        self._seq = 0

    # -- 조회 ---------------------------------------------------------------

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._active is not None

    # -- 실행 ---------------------------------------------------------------

    def submit(self, kind: str, work: Callable[[Callable[[str], None]], Any]) -> Job:
        """work 를 워커 스레드에서 실행한다.

        Args:
            work: 진행 보고 함수 하나를 받아 결과를 돌려주는 콜러블.
                `run_pipeline(..., on_progress=report)` 를 감싸는 데 쓴다.

        Raises:
            RuntimeError: 이미 다른 작업이 도는 중일 때. 조용히 큐에 쌓지 않는다 —
                사용자는 자기가 누른 실행이 지금 도는 줄 알게 된다.
        """
        with self._lock:
            if self._active is not None:
                raise RuntimeError(
                    "이미 실행 중인 작업이 있습니다. 브라우저와 GPU 를 함께 쓰면 "
                    "판정 타이밍이 흔들리므로 한 번에 하나만 실행합니다."
                )
            self._seq += 1
            job = Job(job_id=f"job-{self._seq}", kind=kind)
            self._jobs[job.job_id] = job
            self._active = job.job_id

        def report(message: str) -> None:
            job.messages.append(message)

        def target() -> None:
            try:
                job.result = work(report)
                job.status = "done"
            except Exception as exc:  # noqa: BLE001 - 화면에 그대로 전달한다
                job.status = "error"
                job.error = str(exc) or exc.__class__.__name__
                job.messages.append(f"실패: {job.error}")
                traceback.print_exc()
            finally:
                with self._lock:
                    self._active = None

        threading.Thread(target=target, daemon=True, name=f"prova-{job.job_id}").start()
        return job
