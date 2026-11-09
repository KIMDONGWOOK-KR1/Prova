"""기획서 개정판 비교 — 이전 판과 이번 판의 추출 결과가 어디서 다른가 (B-3, 2026-11-09).

## 왜 있는가

기획서는 납품 중에 여러 판으로 바뀐다(v0.2 → v0.3). QA 가 새 판을 받으면 묻는 것은 둘이다.
무엇이 바뀌었나, 그리고 바뀐 것이 사이트에 반영됐나. 앞의 것은 두 판을 읽어 비교하면 되고,
뒤의 것은 바뀐 요소를 건드리는 케이스를 돌리면 된다.

## 무엇을 비교하는가

`prova.spec_edits` 가 계획 화면에서 고칠 수 있게 한 칸(라벨·필수·안내 문구·오류 문구·빈 칸
문구·선택 항목, 화면의 경로·성공 조건·필수 공통 문구)에 입력 규칙(constraints)과 화면의
실패 조건을 더한다. 같은 칸을 같은 이름으로 보여 준다.

## 짝 맞추기

화면은 screen_id, 없으면 화면 이름으로 맞춘다. 요소는 element_id, 없으면 라벨로 맞춘다 —
라벨이 그대로인데 ID 만 다르게 읽힌 요소를 '뺐다·더했다' 로 보이면 바뀌지 않은 것을 바뀐
것으로 말하게 된다. ID 도 라벨도 다르면 뺀 것과 더한 것으로 보인다(라벨만 바뀐 요소는 ID 가
같을 때만 '라벨 변경' 으로 잡힌다).

## 판정과의 관계

이 차이는 **기획서끼리의 차이**다. 결함이 아니므로 판정 수에 넣지 않는다. 리포트는 별도
상자로 보이고, 바뀐 것을 건드리는 케이스에 표시만 단다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

from prova.models import ScreenSpec, SpecDocument, TestCase, UIElement
from prova.spec_edits import ELEMENT_FIELDS, SCREEN_FIELDS, _show

#: 화면 수준 칸 중 개정 비교에만 더 보는 것.
EXTRA_SCREEN_FIELDS = {"failure_conditions": "실패 조건"}


@dataclass(frozen=True)
class Change:
    """바뀐 것 하나. text 는 사람이 읽는 한 줄이다."""

    screen_id: str
    screen_name: str
    kind: str  # screen_added | screen_removed | screen_field | element_added | element_removed | element_field
    text: str
    element_id: Optional[str] = None
    labels: tuple[str, ...] = ()  # 이전·이번 라벨 (케이스가 이 요소를 건드리는지 볼 때 쓴다)
    field: str = ""  # element_field 일 때 바뀐 칸 (label·placeholder·constraints …)


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def _name(e: UIElement) -> str:
    return f"'{e.label}'" if e.label else e.element_id


def _pair_screens(old: SpecDocument, new: SpecDocument):
    by_id = {s.screen_id: s for s in old.screens}
    by_name = {_norm(s.screen_name): s for s in old.screens}
    used: set[str] = set()
    pairs: list[tuple[Optional[ScreenSpec], ScreenSpec]] = []
    for screen in new.screens:
        prev = by_id.get(screen.screen_id)
        if prev is None or prev.screen_id in used:
            prev = by_name.get(_norm(screen.screen_name))
        if prev is not None and prev.screen_id in used:
            prev = None
        if prev is not None:
            used.add(prev.screen_id)
        pairs.append((prev, screen))
    removed = [s for s in old.screens if s.screen_id not in used]
    return pairs, removed


def _pair_elements(old: list[UIElement], new: list[UIElement]):
    by_id = {e.element_id: e for e in old}
    by_label: dict[str, UIElement] = {}
    for e in old:
        by_label.setdefault(_norm(e.label), e)
    used: set[str] = set()
    pairs: list[tuple[Optional[UIElement], UIElement]] = []
    for e in new:
        prev = by_id.get(e.element_id)
        if prev is None or prev.element_id in used:
            prev = by_label.get(_norm(e.label)) if e.label else None
        if prev is not None and prev.element_id in used:
            prev = None
        if prev is not None:
            used.add(prev.element_id)
        pairs.append((prev, e))
    removed = [e for e in old if e.element_id not in used]
    return pairs, removed


#: 문장으로 적힌 칸. 모델이 같은 문장을 매번 조금씩 다르게 옮겨 적는다("문구를 노출한다" ↔
#: "문구 노출") — 문장 전체를 비교하면 바뀌지 않은 판에서도 차이가 난다.
_PROSE_FIELDS = {"success_condition", "failure_conditions"}
_QUOTED = re.compile(r'"([^"]+)"|“([^”]+)”|‘([^’]+)’|「([^」]+)」')
_PATH = re.compile(r"(?<![\w.])/[\w\-./]*")


def _key_terms(value) -> Optional[frozenset]:
    """문장 칸의 핵심 — 따옴표 안 문구와 경로. 둘 다 없으면 None (그때는 글자로 비교)."""
    text = " ".join(value) if isinstance(value, list) else (value or "")
    terms = {next(g for g in m.groups() if g) for m in _QUOTED.finditer(text)}
    terms |= {p.rstrip(".") for p in _PATH.findall(text)}
    return frozenset(terms) if terms else None


def _same_prose(a, b) -> bool:
    """문장 칸 두 값이 같은 것을 말하는가 (실험: 변이 32개 중 12개에서 바꾸지 않은 칸이 달라 보였다)."""
    ka, kb = _key_terms(a), _key_terms(b)
    if ka is not None or kb is not None:
        return ka == kb
    norm = lambda v: re.sub(r"[\s.,·]", "", " ".join(v) if isinstance(v, list) else (v or ""))
    return norm(a) == norm(b)


def _rules_text(rules: dict) -> str:
    return "{" + ", ".join(f"{k}={rules[k]}" for k in sorted(rules)) + "}" if rules else "''"


def diff_revisions(old: SpecDocument, new: SpecDocument) -> list[Change]:
    """이전 판(old)과 이번 판(new)의 추출 결과 차이. 같으면 빈 목록."""
    changes: list[Change] = []
    pairs, removed_screens = _pair_screens(old, new)
    for prev, screen in pairs:
        sid, sname = screen.screen_id, screen.screen_name
        where = f"[{sname}]"
        if prev is None:
            changes.append(Change(sid, sname, "screen_added", f"{where} 화면이 새로 생김"))
            continue
        for field, name in {**SCREEN_FIELDS, **EXTRA_SCREEN_FIELDS}.items():
            a, b = getattr(prev, field), getattr(screen, field)
            if field in _PROSE_FIELDS and _same_prose(a, b):
                continue
            if (a or None) != (b or None):
                changes.append(Change(sid, sname, "screen_field",
                                      f"{where} {name}: {_show(a)} → {_show(b)}"))
        el_pairs, removed = _pair_elements(prev.elements, screen.elements)
        for before, e in el_pairs:
            if before is None:
                changes.append(Change(sid, sname, "element_added",
                                      f"{where} 요소 {_name(e)} 이 새로 생김",
                                      element_id=e.element_id, labels=(e.label,)))
                continue
            labels = tuple(dict.fromkeys(x for x in (before.label, e.label) if x))
            for field, name in ELEMENT_FIELDS.items():
                a, b = getattr(before, field), getattr(e, field)
                if (a or None) != (b or None):
                    changes.append(Change(sid, sname, "element_field",
                                          f"{where} {_name(before)} {name}: {_show(a)} → {_show(b)}",
                                          element_id=e.element_id, labels=labels, field=field))
            if (before.constraints or {}) != (e.constraints or {}):
                changes.append(Change(
                    sid, sname, "element_field",
                    f"{where} {_name(before)} 입력 규칙: {_rules_text(before.constraints or {})}"
                    f" → {_rules_text(e.constraints or {})}",
                    element_id=e.element_id, labels=labels, field="constraints"))
        for e in removed:
            changes.append(Change(sid, sname, "element_removed",
                                  f"{where} 요소 {_name(e)} 이 없어짐",
                                  element_id=e.element_id, labels=(e.label,)))
    for s in removed_screens:
        changes.append(Change(s.screen_id, s.screen_name, "screen_removed",
                              f"[{s.screen_name}] 화면이 없어짐"))
    return changes


def _mentions(case: TestCase, change: Change) -> bool:
    body = json.dumps(case.model_dump(include={"setup_steps", "steps", "expected"}),
                      ensure_ascii=False)
    return any(label and label in body for label in change.labels)


def _expectation_types(case: TestCase) -> set[str]:
    types = {case.expected.type} if case.expected else set()
    types |= {s.expected.type for s in (*case.setup_steps, *case.steps) if s.expected}
    return types


#: 칸마다 그 칸을 확인하는 케이스의 기대 유형. 라벨처럼 모든 조작이 기대는 칸은 따로 본다.
_CHECKED_BY = {
    "placeholder": {"placeholders_match"},
    "options": {"options_present"},
}


def _touches(case: TestCase, change: Change) -> bool:
    """요소 변경이 이 케이스의 결과를 바꿀 수 있는가.

    라벨·새 요소는 그 이름으로 요소를 찾는 모든 케이스가 기댄다. 다른 칸은 그 칸을 확인하는
    케이스만 기댄다 — 안내 문구가 바뀌었다고 로그인 정상 케이스까지 '개정' 으로 표시하면
    표시가 아무것도 가르지 못한다.
    """
    targeted = bool(change.element_id) and case.target_element == change.element_id
    if change.kind in ("element_added", "element_removed") or change.field == "label":
        return targeted or _mentions(case, change)
    checks = _CHECKED_BY.get(change.field)
    if checks is not None:
        return targeted or (bool(checks & _expectation_types(case)) and _mentions(case, change))
    if change.field == "constraints":
        # 정상 케이스가 넣는 값도 새 규칙을 따라야 한다.
        return targeted or (case.type == "positive" and _mentions(case, change))
    return targeted  # 필수·오류 문구·빈 칸 문구 — 그 요소를 겨냥한 위반 케이스


def touched_cases(cases: list[TestCase], changes: list[Change]) -> dict[str, list[str]]:
    """바뀐 것을 건드리는 케이스 → 그 바뀐 것들(text).

    화면 수준 변경(새 화면·경로·성공 조건 등)은 그 화면의 케이스 전부를, 요소 변경은
    바뀐 칸에 따라 그 칸에 기대는 케이스를 건드린다 (_touches).
    없어진 화면·요소는 이번 판에서 만든 케이스가 다루지 않으므로 보통 아무것도 건드리지 않는다.
    """
    touched: dict[str, list[str]] = {}
    for case in cases:
        hits = []
        for ch in changes:
            if ch.kind in ("screen_added", "screen_field"):
                if case.screen_id == ch.screen_id:
                    hits.append(ch.text)
            elif ch.kind.startswith("element") and case.screen_id == ch.screen_id:
                if _touches(case, ch):
                    hits.append(ch.text)
        if hits:
            touched[case.case_id] = hits
    return touched


def revision_summary(since_source: str, changes: list[Change],
                     touched: dict[str, list[str]], changed_only: bool,
                     cases_available: int) -> dict:
    """리포트 summary["revision"] 에 넣을 값."""
    return {
        "since": since_source,
        "changes": [c.text for c in changes],
        "touched": touched,
        "changed_only": changed_only,
        "cases_available": cases_available,
    }
