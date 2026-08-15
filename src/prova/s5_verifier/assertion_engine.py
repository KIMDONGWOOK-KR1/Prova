"""S5 — 기대와 실제를 대조해 PASS/FAIL 을 판정한다.

## negative 케이스의 판정이 이 프로젝트의 핵심이다

positive 케이스는 직관적이다. 기대한 화면으로 갔으면 PASS.

negative 케이스는 뒤집혀 있다. **에러가 떠야 PASS 다.** 규칙을 위반한 값을
넣었으니 기획서대로면 에러가 노출돼야 한다. 에러가 안 뜨고 그냥 통과됐다면,
그건 구현이 기획서의 검증 규칙을 강제하지 않는다는 뜻이므로 FAIL 이다.

이 뒤집힘이 "기획과 구현의 불일치를 찾는다" 는 Prova 의 목적을 실현하는 지점이다.
직관과 반대라서 코드를 읽는 사람이 헷갈리기 쉬우므로, 판정 함수를 기대 유형별로
나눠 각각의 의미를 이름으로 드러낸다.

## 문구 비교는 정규형에서 한다

기획서 PDF 에서 뽑은 문구와 브라우저 화면에서 읽은 문구는 공백 배치가 다를 수
있다(PDF 는 렌더링 폭에 맞춰 줄을 바꾼다). 그래서 공백을 무시하고 비교한다.
자세한 배경은 text_utils 모듈 설명 참고. 다만 무시하는 것은 공백뿐이다 —
문구 자체가 다르면 반드시 FAIL 이어야 한다. 그게 잡아내야 하는 불일치다.

## 판정 근거를 남긴다

Verdict.evidence 에 기대·실제·URL·스크린샷을 담는다. FAIL 만이 아니라 PASS 에도
남긴다. "왜 PASS 인가" 를 확인할 수 없으면 그 PASS 를 신뢰할 근거가 없다.
"""

from __future__ import annotations

from dataclasses import dataclass

from prova.models import Expectation, StepResult, TestCase, Verdict
from prova.text_utils import contains_loose, normalize_ws


@dataclass
class PageState:
    """판정 시점의 화면 상태. 브라우저 객체 대신 값으로 다뤄 테스트를 쉽게 한다."""

    url: str
    text: str                      # 화면에 보이는 전체 텍스트
    error_texts: list[str]         # 에러 영역([role=alert] 등)의 텍스트만
    console_errors: list[str]      # JS 콘솔 오류
    http_status: int | None = None


def capture_page_state(page, console_errors: list[str] | None = None) -> PageState:
    """Playwright Page 에서 판정에 필요한 정보만 뽑는다.

    에러 영역을 따로 모으는 이유: '에러가 노출됐는가' 를 판정할 때 화면 전체
    텍스트에서 문구를 찾으면, 기획서 문구가 안내 문구나 도움말로 화면에 상시
    노출된 경우 에러가 없어도 찾아진다. 그러면 미탐이 된다.
    """
    error_texts: list[str] = []
    try:
        for locator in page.get_by_role("alert").all():
            text = normalize_ws(locator.inner_text())
            if text:
                error_texts.append(text)
    except Exception:
        pass

    try:
        body_text = page.inner_text("body")
    except Exception:
        body_text = ""

    return PageState(
        url=page.url,
        text=normalize_ws(body_text),
        error_texts=error_texts,
        console_errors=list(console_errors or []),
    )


# ---------------------------------------------------------------------------
# 기대 유형별 판정
# ---------------------------------------------------------------------------


def _error_shown(state: PageState) -> bool:
    """에러가 화면에 노출됐는가. 에러 영역이 비어 있지 않으면 그렇다."""
    return any(state.error_texts)


def _judge_error_message(expected: Expectation, state: PageState) -> tuple[bool, str]:
    """기획서가 지정한 에러 문구가 노출됐는가.

    에러 영역에서 먼저 찾고, 없으면 화면 전체에서 찾는다. 에러를 role=alert 로
    표시하지 않은 구현도 있으므로 폴백을 둔다. 다만 어디서 찾았는지를 사유에
    남겨, 리포트를 보는 사람이 판정 근거의 강도를 알 수 있게 한다.
    """
    joined_errors = " ".join(state.error_texts)
    if contains_loose(joined_errors, expected.value):
        return True, "에러 영역에서 기대 문구를 확인"
    if contains_loose(state.text, expected.value):
        return True, "화면 텍스트에서 기대 문구를 확인 (에러 영역 밖)"

    if not _error_shown(state):
        return False, "에러가 전혀 노출되지 않음 — 구현이 이 규칙을 강제하지 않는다"
    return False, f"다른 문구가 노출됨: {joined_errors!r}"


def _judge_error_shown(expected: Expectation, state: PageState) -> tuple[bool, str]:
    """문구는 특정하지 않고, 에러가 노출됐는지만 본다.

    기획서에 문구가 없어 억측하면 오탐이 되는 경우에 쓴다(generator 참고).
    """
    if _error_shown(state):
        return True, f"에러 노출 확인: {' '.join(state.error_texts)!r}"
    return False, "에러가 노출되지 않음 — 구현이 이 규칙을 강제하지 않는다"


def _judge_redirect(expected: Expectation, state: PageState) -> tuple[bool, str]:
    """기대한 경로로 이동했는가."""
    target = expected.url_contains or expected.value
    if target and target in state.url:
        return True, f"URL 이동 확인: {state.url}"
    return False, f"기대 경로 {target!r} 로 이동하지 않음 (현재 {state.url})"


def _judge_toast_or_redirect(expected: Expectation, state: PageState) -> tuple[bool, str]:
    """정상 처리 확인 — 경로 이동과 문구 노출을 둘 다 검사한다.

    기획서가 둘 다 명시했으면 둘 다 만족해야 PASS 다. 하나만 통과하고 넘기면
    'URL 은 바뀌었는데 화면이 비어 있는' 상태를 정상으로 판정하게 된다.
    """
    checks: list[tuple[bool, str]] = []
    if expected.url_contains:
        ok = expected.url_contains in state.url
        checks.append((ok, f"경로 {expected.url_contains!r} " + ("이동 확인" if ok
                                                                 else f"미이동 (현재 {state.url})")))
    if expected.value:
        ok = contains_loose(state.text, expected.value)
        checks.append((ok, f"문구 {expected.value!r} " + ("노출 확인" if ok else "미노출")))

    if not checks:
        # 기획서에서 성공 조건을 못 뽑은 경우. 에러가 없으면 통과로 본다.
        if _error_shown(state):
            return False, f"에러가 노출됨: {' '.join(state.error_texts)!r}"
        return True, "성공 조건이 명시되지 않아 '에러 없음' 으로 확인"

    passed = all(ok for ok, _ in checks)
    return passed, "; ".join(reason for _, reason in checks)


def _judge_text_visible(expected: Expectation, state: PageState) -> tuple[bool, str]:
    if contains_loose(state.text, expected.value):
        return True, f"문구 {expected.value!r} 노출 확인"
    return False, f"문구 {expected.value!r} 미노출"


_JUDGES = {
    "error_message": _judge_error_message,
    "error_shown": _judge_error_shown,
    "redirect": _judge_redirect,
    "toast_or_redirect": _judge_toast_or_redirect,
    "text_visible": _judge_text_visible,
}


# ---------------------------------------------------------------------------
# 케이스 판정
# ---------------------------------------------------------------------------


def verify(case: TestCase, step_results: list[StepResult], state: PageState) -> Verdict:
    """케이스 하나를 판정한다.

    스텝이 중간에 끊겼으면 기대와 대조할 수 없다. 그때는 그 스텝의 실패를
    그대로 케이스의 실패로 삼는다 — 화면이 기대 상태에 도달할 기회가 없었으므로
    기대 대조 결과는 의미가 없다.
    """
    elapsed = sum(r.elapsed_ms for r in step_results)
    base = dict(
        case_id=case.case_id, title=case.title, type=case.type,
        violates=case.violates, elapsed_ms=elapsed, step_results=step_results,
        healed=any(r.location.healed for r in step_results if r.location),
    )

    failed_step = next((r for r in step_results if r.status == "error"), None)
    if failed_step is not None:
        return Verdict(
            **base,
            verdict="FAIL",
            failure_category=failed_step.error_code or "unknown",
            failure_detail=(
                f"스텝 {failed_step.seq}({failed_step.action} {failed_step.target!r}) "
                f"실패: {failed_step.error_detail}"
            ),
            evidence={
                "expected": _expected_summary(case.expected),
                "actual": f"스텝 {failed_step.seq} 에서 중단",
                "url": state.url,
                "screenshot": failed_step.screenshot,
                "step_error": failed_step.error_detail,
            },
        )

    judge = _JUDGES.get(case.expected.type)
    if judge is None:
        return Verdict(
            **base, verdict="FAIL", failure_category="unknown",
            failure_detail=f"판정할 수 없는 기대 유형: {case.expected.type}",
            evidence={"expected": _expected_summary(case.expected), "url": state.url},
        )

    passed, reason = judge(case.expected, state)
    last_shot = next((r.screenshot for r in reversed(step_results) if r.screenshot), None)

    evidence = {
        "expected": _expected_summary(case.expected),
        "actual": reason,
        "url": state.url,
        "screenshot": last_shot,
        "error_texts": state.error_texts,
    }

    if passed:
        return Verdict(**base, verdict="PASS", evidence=evidence)

    return Verdict(
        **base, verdict="FAIL",
        failure_category=_classify(case, state),
        failure_detail=_failure_detail(case, reason),
        evidence=evidence,
    )


def _expected_summary(expected: Expectation) -> str:
    parts = [f"type={expected.type}"]
    if expected.value:
        parts.append(f"문구={expected.value!r}")
    if expected.url_contains:
        parts.append(f"경로={expected.url_contains!r}")
    return " ".join(parts)


def _classify(case: TestCase, state: PageState) -> str:
    """실패 원인을 명세서 §6 의 카테고리로 분류한다 (규칙 기반).

    1차에서는 LLM 을 쓰지 않는다. 실행이 끝까지 진행된 뒤의 불일치는 대부분
    assertion_mismatch 이고, 그 판단에 추론이 필요하지 않다. LLM 보조 분류는
    2차에서 unknown 으로 남는 사례를 모아 본 뒤 도입한다.
    """
    if state.console_errors:
        return "page_error"
    return "assertion_mismatch"


def _failure_detail(case: TestCase, reason: str) -> str:
    """개발자가 읽고 바로 조치할 수 있는 설명.

    negative 케이스에서는 '어느 규칙의 검증이 확인되지 않았는지' 를 앞세운다.
    그게 개발자가 추가해야 하는 코드를 직접 가리키기 때문이다.
    """
    if case.type == "negative" and case.violates:
        return (
            f"기획서의 '{case.violates}' 검증 규칙이 구현에서 확인되지 않았습니다. "
            f"({reason})"
        )
    return reason
