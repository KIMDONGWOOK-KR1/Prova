"""사람이 읽는 문장 — 기대 결과와 재현 절차를 기획서의 말로 적는다.

## 왜 있는가

리포트를 읽는 사람은 기획자와 테스트 담당자다. 그런데 실패 카드는
`type=error_message 문구='…'` 와 `'password_confirm' 의 'same_as'` 를 보여 줬고, 단계 표에는
**무슨 값을 넣었는지가 없었다**(2026-11-10 화면을 직접 보고 확인). 그러면

- 기획자는 기획서에 쓴 이름('비밀번호 확인')을 리포트에서 찾지 못하고,
- 테스트 담당자는 실패를 개발자에게 넘길 때 값을 다시 찾아야 하며,
- 계획을 승인하는 사람은 제목만 보고 승인한다.

문장을 만드는 곳을 한 곳에 둔다. 리포트·엑셀·계획 화면·판정 사유가 같은 낱말을 쓴다 —
두 벌로 갈라지면 한쪽이 뒤처진다.

**판정에는 관여하지 않는다.** 여기 함수는 이미 정해진 기대·스텝을 글로 옮길 뿐이다.
"""

from __future__ import annotations

from typing import Iterable, Optional

from prova.models import Expectation

# 스텝 표의 동작. 코드 이름(fill·click)은 코드를 아는 사람만 읽는다.
ACTION_LABELS = {
    "navigate": "이동", "fill": "입력", "click": "클릭", "select": "선택",
    "check": "체크", "uncheck": "체크 해제", "wait": "대기", "assert": "확인",
}


def _q(text) -> str:
    return f"'{text}'"


def expectation_sentence(expected: Expectation) -> str:
    """기대 결과를 한 문장으로 — '무엇이 보여야(또는 보이지 않아야) 하는가'."""
    kind = expected.type
    if kind == "error_message":
        return f"오류 문구 {_q(expected.value)} 가 화면에 나타난다"
    if kind == "error_shown":
        return "오류 안내가 나타나고 다음 화면으로 넘어가지 않는다"
    if kind == "text_visible":
        return f"문구 {_q(expected.value)} 가 화면에 보인다"
    if kind == "text_absent":
        return f"문구 {_q(expected.value)} 가 화면에 나타나지 않는다"
    if kind == "redirect":
        return f"{_q(expected.url_contains)} 경로로 이동한다"
    if kind == "toast_or_redirect":
        parts = []
        if expected.value:
            parts.append(f"문구 {_q(expected.value)} 가 보인다")
        if expected.url_contains:
            parts.append(f"{_q(expected.url_contains)} 경로로 이동한다")
        return " 또는 ".join(parts) or "성공 안내가 보이거나 다음 화면으로 이동한다"
    if kind == "result_count":
        return f"{_q(expected.count_target)} 목록에 {expected.count}건이 보인다"
    if kind == "options_present":
        items = ", ".join(_q(o) for o in expected.options)
        return f"{_q(expected.option_target)} 선택 목록에 {items} 항목이 모두 있다"
    if kind == "placeholders_match":
        items = ", ".join(f"{label}: {_q(text)}" for label, text in expected.placeholders.items())
        return f"입력 안내 문구가 기획서와 같다 ({items})"
    if kind == "labels_findable":
        items = ", ".join(_q(label) for label in expected.labels)
        return f"기획서의 이름으로 화면에서 요소를 찾을 수 있다 ({items})"
    if kind == "sorted_desc":
        return f"목록이 {_q(expected.order_target)} 기준 내림차순으로 정렬돼 있다"
    if kind == "sum_matches":
        return (f"{_q(expected.sum_row_target)} 의 합이 화면의 "
                f"{_q(expected.sum_total_target)} 와 같다")
    return str(kind)


def step_sentence(action: str, target: str = "", value: Optional[str] = None) -> str:
    """스텝 하나를 손으로 따라 할 수 있는 말로."""
    if action == "navigate":
        return f"{_q(target)} 주소로 이동"
    if action == "fill":
        if value is None or value == "":
            return f"{_q(target)} 칸을 비워 둔다"
        return f"{_q(target)} 칸에 {_q(value)} 입력"
    if action == "select":
        return f"{_q(target)} 에서 {_q(value)} 선택" if value else f"{_q(target)} 선택"
    if action == "click":
        return f"{_q(target)} 클릭"
    if action == "check":
        return f"{_q(target)} 체크"
    if action == "uncheck":
        return f"{_q(target)} 체크 해제"
    if action == "wait":
        return "잠시 대기"
    if action == "assert":
        return "결과 확인"
    return f"{ACTION_LABELS.get(action, action)} {target}".strip()


def reproduction_lines(steps: Iterable, setup_steps: Iterable = ()) -> list[str]:
    """재현 절차. 스텝(TestStep·StepResult 어느 쪽이든)을 번호 붙인 줄로 만든다.

    전제(로그인 등)를 세우는 스텝은 '준비' 로 구분한다 — 번호가 둘 다 1부터 시작한다.
    """
    lines = []
    for prefix, group in (("준비 ", setup_steps), ("", steps)):
        for step in group:
            lines.append(f"{prefix}{step.seq}. "
                         f"{step_sentence(step.action, step.target, getattr(step, 'value', None))}")
    return lines


def rule_subject(target_label: Optional[str], target_element: Optional[str]) -> str:
    """규칙이 걸린 요소를 가리키는 말 — 기획서의 이름을 먼저, 없으면 식별자."""
    return target_label or target_element or ""
