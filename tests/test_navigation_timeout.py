"""페이지 열기는 요소 조작보다 긴 제한을 쓴다 (2026-09-28, 스파이크 3 발견 B).

the-internet `/tables` 가 `navigate` 에서 10초 제한에 걸렸다. 처음에는 load 이벤트를
기다리는 탓으로 보았지만 goto 는 이미 domcontentloaded 까지만 기다린다 — 재 보니
dcl 과 load 가 같은 시점이고, 느린 것은 **첫 접속**이었다(8초, 이후 2.7초. Heroku 가
잠든 서버를 깨우는 시간). 실물 사이트의 페이지 로드는 버튼 누르기보다 원래 느리다.
분류는 이미 정직했다('시간 초과' — 실행 문제). 줄이는 것은 불필요한 실행 문제다.
"""

from __future__ import annotations

from prova.models import ScreenSpec, TestStep
from prova.pipeline import execution_options
from prova.s4_executor.playwright_driver import ExecutionContext, execute_step


class _FakePage:
    def __init__(self):
        self.goto_timeout = None

    def goto(self, url, timeout, wait_until):
        self.goto_timeout = timeout
        return None


def _ctx(page, tmp_path, **kw) -> ExecutionContext:
    return ExecutionContext(page=page, base_url="http://x.test",
                            specs=[ScreenSpec(screen_id="s", screen_name="s", url_path="/s")],
                            run_dir=tmp_path, case_id="c", screenshot_every_step=False, **kw)


def test_navigate_는_페이지_열기_제한을_쓴다(tmp_path):
    page = _FakePage()
    execute_step(_ctx(page, tmp_path, step_timeout_ms=10000, navigation_timeout_ms=30000),
                 TestStep(seq=1, action="navigate", target="/tables"))
    assert page.goto_timeout == 30000


def test_기본값은_30초다(tmp_path):
    page = _FakePage()
    execute_step(_ctx(page, tmp_path), TestStep(seq=1, action="navigate", target="/t"))
    assert page.goto_timeout == 30000


def test_설정에서_읽는다():
    assert execution_options({})["navigation_timeout_ms"] == 30000
    cfg = {"execution": {"navigation_timeout_ms": "45000"}}
    assert execution_options(cfg)["navigation_timeout_ms"] == 45000
