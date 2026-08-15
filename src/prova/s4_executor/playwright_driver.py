"""S4 — TestStep 을 실제 브라우저에서 수행한다.

## 스텝마다 증거를 남긴다

각 스텝 후 스크린샷과 DOM 스냅샷을 파일로 남긴다. 이유는 명세서 §9 의 '리포트
완결성 100%' 목표 때문만이 아니다. QA 도구가 FAIL 을 보고했을 때 개발자가 가장
먼저 하는 일은 "정말 그런가" 를 확인하는 것이다. 그때 볼 것이 없으면 도구를
신뢰하지 않게 되고, 진짜 결함 보고도 무시되기 시작한다.

## 실패를 예외로 던지지 않는다

스텝이 실패해도 StepResult(status='error') 를 돌려주고 원인 코드를 붙인다.
예외로 파이프라인을 세우면 그 케이스 이후의 케이스들이 실행되지 않아, 한 번
돌려서 전체 상태를 파악할 수 없게 된다. 실패는 데이터로 다루고, 판정은 S5 가,
분류는 S6 가 한다.

예외는 프로그래밍 오류(알 수 없는 action 등)에만 쓴다.

## error_code 는 명세서 §6 의 FailureCategory 로 이어진다

    element_not_found  탐지 실패 (S3 의 GroundingError)
    timeout            대기 시간 초과
    page_error         네비게이션 실패, 4xx/5xx
    input_error        요소를 찾았으나 조작 불가 (가림·비활성)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from prova.models import ElementLocation, ScreenSpec, StepResult, TestStep
from prova.s3_grounder.dom_locator import GroundingError, ground, resolve_locator


@dataclass
class ExecutionContext:
    """한 케이스를 실행하는 동안 유지되는 설정과 상태."""

    page: Page
    base_url: str
    spec: ScreenSpec
    run_dir: Path
    case_id: str
    step_timeout_ms: int = 10000
    screenshot_every_step: bool = True
    console_errors: list[str] = field(default_factory=list)

    @property
    def case_dir(self) -> Path:
        d = self.run_dir / self.case_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def hint_for(self, label: str):
        """라벨로 UIElement 를 찾는다. 탐지 전략을 좁히는 데 쓴다."""
        return next((e for e in self.spec.elements if e.label == label), None)


def _capture(ctx: ExecutionContext, seq: int) -> tuple[str | None, str | None]:
    """스크린샷과 DOM 스냅샷을 저장하고 리포트 기준 상대 경로를 돌려준다.

    경로 기준은 run_dir 이다. report.html 이 run_dir 안에 놓이므로, 그 파일에서
    상대 링크로 바로 열려야 한다. Windows 의 역슬래시는 HTML 속성에서 경로
    구분자로 처리되지 않으므로 as_posix() 로 슬래시를 쓴다.

    캡처 실패가 스텝 실패로 번지지 않게 한다 — 증거가 없는 것보다 스텝 결과를
    잃는 것이 나쁘다.
    """
    if not ctx.screenshot_every_step:
        return None, None

    shot = ctx.case_dir / f"step{seq}.png"
    dom = ctx.case_dir / f"step{seq}.html"
    shot_path = dom_path = None
    try:
        ctx.page.screenshot(path=str(shot))
        shot_path = shot.relative_to(ctx.run_dir).as_posix()
    except Exception:
        pass
    try:
        dom.write_text(ctx.page.content(), encoding="utf-8")
        dom_path = dom.relative_to(ctx.run_dir).as_posix()
    except Exception:
        pass
    return shot_path, dom_path


def _resolve_url(ctx: ExecutionContext, target: str) -> str:
    """기획서의 url_path 를 실제 URL 로.

    base_url 이 'http://host:8100/good' 이고 target 이 '/login' 이면
    'http://host:8100/good/login' 이 되어야 한다. urljoin 은 절대 경로 target 을
    호스트 루트에 붙이므로(/good 이 사라진다) 직접 이어 붙인다. 이 처리가
    good/bad 두 변형을 같은 기획서로 검증할 수 있게 하는 지점이다.
    """
    if target.startswith(("http://", "https://")):
        return target
    return ctx.base_url.rstrip("/") + "/" + target.lstrip("/")


def execute_step(ctx: ExecutionContext, step: TestStep) -> StepResult:
    """스텝 하나를 실행한다. 실패해도 예외를 던지지 않고 결과로 표현한다."""
    started = time.monotonic()
    location: ElementLocation | None = None
    status = "ok"
    error_code = error_detail = None

    try:
        if step.action == "navigate":
            url = _resolve_url(ctx, step.target)
            response = ctx.page.goto(url, timeout=ctx.step_timeout_ms,
                                     wait_until="domcontentloaded")
            # 4xx/5xx 를 성공으로 넘기면 이후 스텝이 전부 요소 미탐지로 실패해
            # 원인이 흐려진다. 여기서 page_error 로 확정한다.
            if response is not None and response.status >= 400:
                status, error_code = "error", "page_error"
                error_detail = f"HTTP {response.status} — {url}"

        elif step.action == "wait":
            ctx.page.wait_for_timeout(int(step.value or 500))

        elif step.action in ("fill", "click", "select"):
            hint = ctx.hint_for(step.target)
            location = ground(ctx.page, step.target, hint)
            locator = resolve_locator(ctx.page, location, hint)

            if step.action == "fill":
                # 빈 값도 명시적으로 채운다. required 위반 케이스는 '비워 두는
                # 것' 자체가 검증 대상이므로 건너뛰면 안 된다.
                locator.fill(step.value or "", timeout=ctx.step_timeout_ms)
            elif step.action == "click":
                locator.click(timeout=ctx.step_timeout_ms)
            else:
                locator.select_option(step.value or "", timeout=ctx.step_timeout_ms)

        elif step.action == "assert":
            # 판정은 S5 의 일이다. 스텝 수준 assert 는 1차 범위에서 쓰지 않는다.
            pass

        else:
            raise ValueError(f"알 수 없는 action: {step.action}")

    except GroundingError as exc:
        status, error_code, error_detail = "error", "element_not_found", exc.reason
    except PlaywrightTimeout as exc:
        status, error_code = "error", "timeout"
        error_detail = f"{ctx.step_timeout_ms}ms 초과 — {str(exc).splitlines()[0]}"
    except PlaywrightError as exc:
        # 요소는 찾았지만 조작할 수 없는 경우(다른 요소에 가림, disabled 등)
        status, error_code = "error", "input_error"
        error_detail = str(exc).splitlines()[0]

    elapsed_ms = int((time.monotonic() - started) * 1000)
    shot, dom = _capture(ctx, step.seq)

    return StepResult(
        seq=step.seq, action=step.action, target=step.target,
        status=status, elapsed_ms=elapsed_ms,
        screenshot=shot, dom_snapshot=dom,
        error_code=error_code, error_detail=error_detail,
        location=location,
    )


def execute_case_steps(ctx: ExecutionContext, steps: list[TestStep]) -> list[StepResult]:
    """케이스의 스텝을 순서대로 실행한다.

    스텝이 실패하면 그 뒤 스텝을 건너뛴다. 로그인 폼을 못 채운 상태로 제출
    버튼을 누르면 그 결과가 무엇을 의미하는지 해석할 수 없기 때문이다. 건너뛴
    스텝은 결과 목록에 넣지 않고, S5 가 '스텝이 중단됐다' 는 사실로 판정한다.
    """
    results: list[StepResult] = []
    for step in steps:
        result = execute_step(ctx, step)
        results.append(result)
        if result.status == "error":
            break
    return results
