"""호출 수·시간·토큰을 세는 겉싸개 — 백엔드 비교 측정용.

어느 백엔드든 감쌀 수 있다. 시간은 벽시계로, 토큰은 안쪽 백엔드가 `last_usage` 를 내놓을
때만 센다(Claude). 로컬(vLLM)은 과금이 없어 토큰을 세지 않는다.
"""

from __future__ import annotations

import threading
import time


class MeteredLLM:
    def __init__(self, inner) -> None:
        self.inner = inner
        self.name = inner.name
        self.model = getattr(inner, "model", "")
        self.base_url = getattr(inner, "base_url", "")
        self.calls = 0
        self.failures = 0
        self.seconds = 0.0
        self.input_tokens = 0
        self.output_tokens = 0
        self._lock = threading.Lock()

    def complete_json(self, **request) -> dict:
        started = time.perf_counter()
        ok = False
        try:
            answer = self.inner.complete_json(**request)
            ok = True
            return answer
        finally:
            elapsed = time.perf_counter() - started
            usage = getattr(self.inner, "last_usage", None) or {}
            with self._lock:
                self.calls += 1
                self.failures += 0 if ok else 1
                self.seconds += elapsed
                self.input_tokens += usage.get("input_tokens", 0)
                self.output_tokens += usage.get("output_tokens", 0)

    def summary(self) -> dict:
        return {
            "backend": self.name,
            "calls": self.calls,
            "failures": self.failures,
            "seconds": round(self.seconds, 1),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }
