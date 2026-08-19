"""전제(로그인)를 세우는 스텝을 만든다 — 순수 함수, LLM 없음 (스펙 §3-2).

라벨은 로그인 화면 ScreenSpec 에서 가져온다. 흐름이 값을 라벨로 잇는 것과
같은 원리다 — 탐지는 라벨로 한다는 규칙을 여기서도 지킨다.
"""
from __future__ import annotations
import re
from typing import Optional
from prova.models import (Expectation, Precondition, ScreenSpec,
                          SpecDocument, TestCase, TestStep)

# 로그인 화면의 성공 조건 문장에서 이동 경로를 뽑는다. generator.py 의
# _PATH_RE 와 같은 패턴이다 — 여기서 다시 import 하지 않는 이유는 generator.py
# 가 이 모듈(precondition)을 불러 쓰므로(순환 import), 같은 3줄짜리 패턴을
# 다시 만드는 편이 의존을 꼬는 것보다 싸다.
#
# '/' 다음을 영문자로 제한하는 이유는 generator._PATH_RE 와 같다 — "24/7"
# 같은 숫자 표현의 "/7" 을 경로로 오인하지 않는다.
_PATH_RE = re.compile(r"(/[a-zA-Z][a-zA-Z0-9_\-/]*)")


def _find_label(screen: ScreenSpec, element_id: str) -> Optional[str]:
    for el in screen.elements:
        if el.element_id == element_id:
            return el.label
    return None


def _login_success_path(login: ScreenSpec) -> Optional[str]:
    """로그인 성공 조건 문장에서 이동 경로를 뽑는다. 없으면 None.

    ## 왜 필요한가 — 전제 스텝 네 개만으로는 '로그인됐다' 를 확인하지 못한다

    click 스텝은 제출 버튼을 누르는 데 성공했는지만 본다. 비밀번호가 틀려도
    버튼은 눌린다 — Playwright 관점에서 그 클릭은 실패가 아니다. 그러면 틀린
    계정으로도 setup_steps 전체가 '성공' 으로 기록되고, 뒤이은 본 스텝이 아직
    로그인 화면에 남아 있는 채로 실행돼 엉뚱한 요소를 찾다 실패한다(phase='test').
    그 실패는 precondition_failed 가 아니라 element_not_found 로 분류되어,
    "전제가 깨졌다" 는 진짜 원인이 리포트에서 사라진다.

    그래서 로그인 화면이 성공 시 이동한다고 적은 경로에 실제로 도착했는지를
    다섯 번째 스텝(assert)으로 확인한다. 실패하면 phase='setup' 인 채로 남아
    verify() 가 precondition_failed 로 분류한다(assertion_engine.verify 참고).
    """
    text = login.success_condition or ""
    paths = [p for p in _PATH_RE.findall(text) if p != login.url_path]
    return paths[0] if paths else None


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
    steps = [
        TestStep(seq=1, action="navigate", target=login.url_path),
        TestStep(seq=2, action="fill", target=email, value=pre.account_email),
        TestStep(seq=3, action="fill", target=password, value=pre.account_password),
        TestStep(seq=4, action="click", target=submit),
    ]
    success_path = _login_success_path(login)
    if success_path:
        steps.append(TestStep(
            seq=5, action="assert", target="로그인 성공",
            expected=Expectation(type="redirect", url_contains=success_path),
        ))
    return steps, []


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
