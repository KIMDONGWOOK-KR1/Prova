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

from prova.models import ElementLocation, Expectation, ScreenSpec, StepResult, TestStep
from prova.s3_grounder.dom_locator import (
    GroundingError,
    SpecTypeMismatch,
    ground,
    resolve_locator,
)
from prova.text_utils import contains_loose


@dataclass
class ExecutionContext:
    """한 케이스를 실행하는 동안 유지되는 설정과 상태."""

    page: Page
    base_url: str
    # 이 케이스가 밟는 화면들. **첫 항목이 이 케이스의 화면**이고, 흐름 케이스에서는
    # 뒤따라 밟을 화면들이 이어진다.
    #
    # 왜 목록인가: 흐름 케이스는 한 케이스가 여러 화면을 밟으므로, 라벨 힌트를
    # 화면 하나에서만 찾으면 뒤 화면의 요소에 힌트가 붙지 않는다. 힌트가 없으면
    # S3 가 role 을 버튼으로 가정해 탐지가 흔들린다.
    #
    # 순서가 중요한 이유: 라벨이 두 화면에 같이 있으면(로그인과 회원가입의 '이메일')
    # 이 케이스의 화면 것을 먼저 쓴다. 뒤 화면 것을 집으면 타입이 달라 role 추정이
    # 틀릴 수 있다.
    specs: list[ScreenSpec]
    run_dir: Path
    case_id: str
    step_timeout_ms: int = 10000
    screenshot_every_step: bool = True
    console_errors: list[str] = field(default_factory=list)

    @property
    def spec(self) -> ScreenSpec:
        """이 케이스의 화면. 스크린샷 경로·진행 메시지 등에서 쓴다."""
        return self.specs[0]

    @property
    def case_dir(self) -> Path:
        d = self.run_dir / self.case_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def hint_for(self, label: str):
        """라벨로 UIElement 를 찾는다. 탐지 전략을 좁히는 데 쓴다."""
        for spec in self.specs:
            found = next((e for e in spec.elements if e.label == label), None)
            if found is not None:
                return found
        return None


def arrival_check(page, expected: Expectation) -> tuple[bool, str]:
    """흐름의 중간 단계에서 '여기까지 제대로 왔는가' 만 본다.

    ## 왜 S5 의 판정 함수를 부르지 않는가

    이건 판정이 아니라 **선행 조건 확인**이다. 목적은 다음 화면으로 넘어가도 되는지,
    넘어가지 못했으면 어느 화면에서 끊겼는지를 남기는 것뿐이다. navigate 스텝이
    4xx 를 실패로 확정하는 것과 같은 성질의 확인이고, 그래서 실행 단계에 있다.

    S5 의 판정보다 **일부러 좁다.** 에러 영역과 화면 텍스트를 구분하지 않고, 실패
    분류도 하지 않는다. 여기서 필요한 사실은 '도착했는가' 하나이고, 그 이상을 이
    자리에서 판단하면 판정 책임이 두 단계로 흩어진다.

    Returns:
        (도착했는가, 사유). 사유는 실패 시 리포트에 그대로 들어간다.
    """
    reasons: list[str] = []
    ok = True

    if expected.url_contains:
        arrived = expected.url_contains in page.url
        ok = ok and arrived
        reasons.append(
            f"경로 {expected.url_contains!r} "
            + ("이동 확인" if arrived else f"미이동 (현재 {page.url})")
        )
    if expected.value:
        try:
            text = page.inner_text("body")
        except Exception:
            text = ""
        shown = contains_loose(text, expected.value)
        ok = ok and shown
        reasons.append(f"문구 {expected.value!r} " + ("노출 확인" if shown else "미노출"))

    if not reasons:
        # 성공 조건을 기획서에서 못 뽑은 경우. 확인할 것이 없으면 통과로 본다 —
        # 여기서 실패로 만들면 기획서가 성공 조건을 안 적은 화면의 흐름이 전부
        # 끊겨, 흐름 자체를 검증할 수 없게 된다. 그 누락은 S1 이 경고로 알린다.
        return True, "확인할 성공 조건이 기획서에 없어 통과로 봄"
    return ok, "; ".join(reasons)


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

        elif step.action in ("fill", "click", "select", "check", "uncheck"):
            hint = ctx.hint_for(step.target)
            location = ground(ctx.page, step.target, hint)
            locator = resolve_locator(ctx.page, location, hint)

            if step.action == "fill":
                # 빈 값도 명시적으로 채운다. required 위반 케이스는 '비워 두는
                # 것' 자체가 검증 대상이므로 건너뛰면 안 된다.
                locator.fill(step.value or "", timeout=ctx.step_timeout_ms)
            elif step.action == "click":
                locator.click(timeout=ctx.step_timeout_ms)
            elif step.action == "check":
                locator.check(timeout=ctx.step_timeout_ms)
            elif step.action == "uncheck":
                # 이미 해제된 상태면 아무 일도 하지 않는다. 그래도 스텝으로
                # 남기는 이유는 '체크하지 않았다' 는 사실이 리포트에서 검증
                # 조건으로 읽혀야 하기 때문이다 — 스텝이 없으면 그 케이스가
                # 무엇을 확인했는지 나중에 알 수 없다.
                locator.uncheck(timeout=ctx.step_timeout_ms)
            else:
                locator.select_option(step.value or "", timeout=ctx.step_timeout_ms)

        elif step.action == "assert":
            # 흐름의 중간 도착 확인. 여기서 끊기면 그 화면이 지목되고, 마지막
            # 화면이 애먼 소리를 듣지 않는다 (arrival_check 설명 참고).
            if step.expected is not None:
                arrived, reason = arrival_check(ctx.page, step.expected)
                if not arrived:
                    status, error_code = "error", "assertion_mismatch"
                    error_detail = reason

        else:
            raise ValueError(f"알 수 없는 action: {step.action}")

    except SpecTypeMismatch as exc:
        # 탐지 실패가 아니라 기획-구현 불일치다. element_not_found 로 묶으면
        # 개발자가 라벨을 고치려 든다 — 고쳐야 할 것은 요소의 종류다.
        status, error_code, error_detail = "error", "assertion_mismatch", exc.reason
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
