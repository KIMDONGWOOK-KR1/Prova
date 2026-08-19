"""전제(로그인)를 세우는 스텝을 만든다 — 순수 함수, LLM 없음 (스펙 §3-2).

라벨은 로그인 화면 ScreenSpec 에서 가져온다. 흐름이 값을 라벨로 잇는 것과
같은 원리다 — 탐지는 라벨로 한다는 규칙을 여기서도 지킨다.
"""
from __future__ import annotations
from typing import Optional
from prova.models import (Expectation, Precondition, ScreenSpec,
                          SpecDocument, TestCase, TestStep)


def _find_label(screen: ScreenSpec, element_id: str) -> Optional[str]:
    for el in screen.elements:
        if el.element_id == element_id:
            return el.label
    return None


def expand_precondition(
    pre: Precondition, doc: SpecDocument,
) -> tuple[list[TestStep], list[str]]:
    if not pre or not pre.requires_login:
        return [], []
    login = next((s for s in doc.screens
                  if s.screen_id == pre.login_screen_id), None)
    if login is None:
        return [], [f"전제가 가리키는 로그인 화면({pre.login_screen_id})이 "
                    f"문서에 없어 전제 스텝을 만들지 못했습니다."]
    email = _find_label(login, "email")
    password = _find_label(login, "password")
    submit = next((el.label for el in login.elements if el.type == "button"), None)
    if not (email and password and submit):
        return [], [f"로그인 화면({login.screen_id})에서 이메일/비밀번호/제출 "
                    f"요소를 찾지 못해 전제 스텝을 만들지 못했습니다."]
    return [
        TestStep(seq=1, action="navigate", target=login.url_path),
        TestStep(seq=2, action="fill", target=email, value=pre.account_email),
        TestStep(seq=3, action="fill", target=password, value=pre.account_password),
        TestStep(seq=4, action="click", target=submit),
    ], []


def guard_case(
    spec: ScreenSpec, pre: Precondition, doc: SpecDocument, seq: int,
) -> Optional[TestCase]:
    """'비로그인이면 로그인으로 이동' — 전제 절 자체의 검증 (스펙 §3-3)."""
    if not pre or not pre.requires_login:
        return None
    login = next((s for s in doc.screens
                  if s.screen_id == pre.login_screen_id), None)
    if login is None:
        return None
    return TestCase(
        case_id=f"{spec.screen_id}-precondition-guard-{seq:03d}",
        screen_id=spec.screen_id,
        title="비로그인 접근 시 로그인 화면으로 이동하는지 확인",
        type="negative",
        steps=[TestStep(seq=1, action="navigate", target=spec.url_path)],
        expected=Expectation(type="redirect", url_contains=login.url_path),
    )
