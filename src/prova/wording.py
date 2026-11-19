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

import re

from typing import Iterable, Optional

from prova.models import Expectation

# 스텝 표의 동작. 코드 이름(fill·click)은 코드를 아는 사람만 읽는다.
ACTION_LABELS = {
    "navigate": "이동", "fill": "입력", "click": "클릭", "select": "선택",
    "check": "체크", "uncheck": "체크 해제", "wait": "대기", "assert": "확인",
}


def _q(text) -> str:
    return f"'{text}'"


def josa(word: str, with_final: str, without_final: str) -> str:
    """word 뒤에 붙일 조사 — 받침이 있으면 with_final('을'), 없으면 without_final('를').

    한글로 끝나지 않으면(영문·숫자) 받침을 알 수 없어 둘 다 적는다.
    """
    last = (word or " ")[-1]
    if not "가" <= last <= "힣":
        return f"{with_final}({without_final})"
    return with_final if (ord(last) - 0xAC00) % 28 else without_final


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


def reproduction_lines(steps: Iterable, setup_steps: Iterable = (), pending: Iterable = ()) -> list[str]:
    """재현 절차. 스텝(TestStep·StepResult 어느 쪽이든)을 번호 붙인 줄로 만든다.

    전제(로그인 등)를 세우는 스텝은 '준비' 로 구분한다 — 번호가 둘 다 1부터 시작한다.
    멈춘 스텝에는 '← 여기서 멈춤' 을 달고, 멈춘 뒤 실행하지 못한 스텝(Verdict.pending_steps)을
    '(실행하지 못함)' 으로 잇는다 — 리포트 카드의 재현 절차와 같은 내용이다 (2026-11-19).
    """
    pending = list(pending)
    lines = []
    for prefix, phase, group in (("준비 ", "setup", setup_steps), ("", "test", steps)):
        last = 0
        for step in group:
            last = step.seq
            stop = " ← 여기서 멈춤" if getattr(step, "status", "ok") == "error" else ""
            lines.append(f"{prefix}{step.seq}. "
                         f"{step_sentence(step.action, step.target, getattr(step, 'value', None))}{stop}")
        for s in (s for s in pending if (s.get("phase") or "test") == phase):
            last += 1
            lines.append(f"{prefix}{last}. "
                         f"{step_sentence(s.get('action', ''), s.get('target', ''), s.get('value'))} (실행하지 못함)")
    return lines


def source_sentence(source) -> str:
    """기획서 근거 한 곳 — '2쪽 표 — …'.

    표 행은 원문이 `nickname | 입력 | 닉네임 | 필수 | - | …` 처럼 온다. 칸 구분자와 빈 칸('-'),
    첫 칸의 식별자(PDF 에서 'password_con firm' 처럼 깨져 오기도 한다)는 기획자가 읽을
    말이 아니어서 빼고 ' · ' 로 잇는다.
    """
    quote = source.quote
    if source.table and "|" in quote:
        quote = " · ".join(source_cells(source))
    return f"{source.page}쪽 {'표' if source.table else '본문'}: {quote}"


def source_cells(source) -> list[str]:
    """표 행 근거를 읽을 칸만 남겨 나눈다. 표 행이 아니면 빈 목록 — 리포트가 표 모양으로 옮길 때 쓴다."""
    if not (source.table and "|" in source.quote):
        return []
    cells = [c.strip() for c in source.quote.split("|")]
    if cells and re.fullmatch(r"[A-Za-z0-9_\- ]+", cells[0]):
        cells = cells[1:]
    return [c for c in cells if c and c not in ("-", "—")]


def rule_subject(target_label: Optional[str], target_element: Optional[str]) -> str:
    """규칙이 걸린 요소를 가리키는 말 — 기획서의 이름을 먼저, 없으면 식별자."""
    return target_label or target_element or ""


# '…하면 막힌다' 를 '…해도 막히지 않습니다' 로 — 결함 케이스에서 실제로 일어난 일.
_NOT_BLOCKED = [
    ("입력하면 막힌다", "입력해도 막히지 않습니다"),
    ("비워 두면 막힌다", "비워 둬도 막히지 않습니다"),
    ("않으면 막힌다", "않아도 막히지 않습니다"),
]


def not_blocked_sentence(plain: str) -> Optional[str]:
    """막혀야 하는 입력이 막히지 않았을 때의 한 문장. 그런 모양의 문장이 아니면 None."""
    for done, happened in _NOT_BLOCKED:
        if plain.endswith(done):
            return plain[: -len(done)] + happened
    return None


def copy_text(verdict, headline: str, target_url: str = "") -> str:
    """'재현 절차 복사' 로 클립보드에 담는 글 — 개발자에게 그대로 붙여 넣는다."""
    ev = verdict.evidence or {}
    lines = [headline]
    if target_url:
        lines.append(f"주소: {target_url}")
    setup = [r for r in verdict.step_results if r.phase == "setup"]
    steps = [r for r in verdict.step_results if r.phase != "setup"]
    lines += reproduction_lines(steps, setup, getattr(verdict, "pending_steps", ()))
    if ev.get("expected"):
        lines.append(f"기대: {ev['expected']}")
    actual = ev.get("actual")
    if any(getattr(r, "status", "ok") == "error" for r in verdict.step_results):
        actual = stop_reason(verdict)[1] or actual  # '스텝 7 에서 중단' 보다 무엇을 하려다 멈췄는지
    if actual:
        lines.append(f"실제: {actual}")
    lines += [f"기획서: {source_sentence(s)}" for s in verdict.spec_sources]
    return "\n".join(lines)



# ── 멈춘 이유와 이름 대조 — 여러 건을 한 번에 읽게 한다 (2026-11-19) ─────────────
#
# 실물 기획서 실행(43건)에서 판정하지 못한 19건 중 10건이 같은 자리에서 멈췄고, 기획서와 다른
# 14건은 전부 이름 대조였다. 한 건씩 늘어놓으면 '같은 이유 열 번' 과 '이름 여덟 개' 를 읽는
# 사람이 직접 세어야 한다.

def _stop_sentence(action: str, target: str) -> str:
    """멈춘 스텝 — '무엇을 하려다' 멈췄는지. 조사는 뒤 낱말(칸·버튼·목록)에 붙여 맞춘다."""
    t = _q(target)
    return {
        "fill": f"{t} 칸에 입력하려다 멈췄습니다",
        "click": f"{t} 버튼을 누르려다 멈췄습니다",
        "select": f"{t} 목록에서 고르려다 멈췄습니다",
        "check": f"{t} 체크 상자를 누르려다 멈췄습니다",
        "uncheck": f"{t} 체크 상자를 풀려다 멈췄습니다",
        "navigate": f"{t} 주소로 이동하려다 멈췄습니다",
    }.get(action, f"{t} 단계에서 멈췄습니다")


def _why_sentence(detail: str) -> str:
    detail = detail or ""
    if "보이지 않" in detail:
        return "화면 구조에는 있지만 화면에 보이지 않았습니다."
    if "일치하는 요소가 없" in detail or "찾지 못" in detail:
        return "화면에서 그 이름을 찾지 못했습니다."
    if "시간" in detail or "초과" in detail or "timeout" in detail.lower():
        return "정해진 시간 안에 화면이 준비되지 않았습니다."
    return detail.rstrip(".") + "." if detail else ""


def stop_reason(verdict) -> tuple[str, str]:
    """판정하지 못한 케이스가 어디서, 왜 멈췄는지 — (멈춘 대상 이름, 문장).

    문장이 같으면 같은 이유로 멈춘 것이다 — 리포트가 그것으로 묶는다.
    """
    stopped = next((r for r in verdict.step_results if r.status == "error"), None)
    if stopped is not None:
        why = _why_sentence(stopped.error_detail or verdict.failure_detail or "")
        return stopped.target, f"{_stop_sentence(stopped.action, stopped.target)}. {why}".strip()
    detail = verdict.failure_detail or ""
    names = re.findall(r"'([^']+)'", detail)
    if names and "찾지 못" in detail:
        return names[0], f"화면에서 {', '.join(_q(n) for n in names)} 항목을 찾지 못해 확인하지 못했습니다."
    return "", (detail or "도중에 멈췄습니다.").strip()


def missing_names(verdict) -> tuple[list[str], list[str]]:
    """이름 대조 케이스라면 (화면에 없던 이름, 있던 이름). 아니면 빈 목록 둘."""
    findable = (getattr(verdict, "evidence", None) or {}).get("findable") or {}
    return ([name for name, err in findable.items() if err],
            [name for name, err in findable.items() if not err])
