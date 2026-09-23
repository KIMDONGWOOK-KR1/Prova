"""오류 문구를 role=alert 밖에서도 찾는다 — 보이고 글자가 있는 것만 (2026-09-23).

외부 사이트 두 번째 스파이크에서 드러났다. parabank 는 `<span class="error">`,
expandtesting 은 `<div class="alert alert-danger">` 에 오류를 띄우고 role=alert 가 없다.
도구는 오류 영역을 role=alert 로만 찾았으므로

- 가입 실패 사유가 "경로 '/login' 미이동" 뿐이었다 — 화면의 "An error occurred during
  registration." 이 사유에 없어 개발자가 원인을 다시 찾아야 한다.
- 문구를 모르는 필수 케이스('에러가 떴는가' 만 보는 판정)는 화면에 오류가 떠 있어도
  **"에러가 전혀 노출되지 않음" 이라고 거짓으로** 말한다.

넓히되 오탐을 막는 조건 셋: 보이는 것만(숨은 오류 칸 — PTA), 글자가 있는 것만
(`input_error` 클래스가 붙은 빈 입력란 — saucedemo), 성공 알림(`alert-success`)은 제외.
"""

from __future__ import annotations

import pytest

from prova.s5_verifier.assertion_engine import capture_page_state


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        yield pg
        browser.close()


def errors_on(page, html: str) -> list[str]:
    page.set_content(html)
    return capture_page_state(page).error_texts


def test_role_alert_는_여전히_잡는다(page):
    assert errors_on(page, '<div role="alert">잘못된 값</div>') == ["잘못된 값"]


def test_클래스에_error_가_든_요소를_잡는다(page):
    """parabank: 표 칸 옆의 span.error"""
    got = errors_on(page, '<td><input></td><td><span class="error">First name is required.</span></td>')
    assert got == ["First name is required."]


def test_부트스트랩_alert_danger_를_잡는다(page):
    """expandtesting: 가입 실패"""
    got = errors_on(page, '<div class="alert alert-danger">An error occurred during registration.</div>')
    assert got == ["An error occurred during registration."]


def test_data_test_error_를_잡는다(page):
    """saucedemo"""
    got = errors_on(page, '<h3 data-test="error">Epic sadface: Username is required</h3>')
    assert got == ["Epic sadface: Username is required"]


def test_숨은_오류_칸은_세지_않는다(page):
    """PTA: 문구를 든 채 늘 DOM 에 있는 오류 칸"""
    assert errors_on(page, '<div id="error" style="display:none">Your username is invalid!</div>') == []


def test_빈_요소는_세지_않는다(page):
    """saucedemo: class 에 input_error 가 붙은 입력란"""
    assert errors_on(page, '<input class="input_error form_input"><div class="error-message-container"></div>') == []


def test_성공_알림은_오류가_아니다(page):
    """정상 케이스가 '에러가 노출됨' 으로 거짓 실패하지 않게"""
    assert errors_on(page, '<div class="alert alert-success">Successfully registered.</div>') == []


def test_겹친_요소는_한_번만(page):
    """바깥 컨테이너와 안쪽 문구가 둘 다 error 이름을 달고 있어도 같은 글자를 두 번 세지 않는다"""
    got = errors_on(page, '<div class="error-container"><span class="error">잘못된 값</span></div>')
    assert got == ["잘못된 값"]


def test_정상_케이스가_실패하면_화면_오류_문구가_사유에_실린다():
    """expandtesting 2회차: 계정 중복으로 가입이 거절됐는데 사유는 '/login 미이동' 뿐이었다."""
    from prova.models import Expectation, StepResult, TestCase, TestStep
    from prova.s5_verifier.assertion_engine import PageState, verify

    case = TestCase(case_id="c", screen_id="register", title="정상 가입", type="positive",
                    steps=[TestStep(seq=1, action="navigate", target="/register")],
                    expected=Expectation(type="toast_or_redirect", url_contains="/login"))
    state = PageState(url="https://x/register", text="...",
                      error_texts=["An error occurred during registration. Please try again."])
    v = verify(case, [StepResult(seq=1, action="click", target="Register", status="ok")], state)
    assert v.verdict == "FAIL"
    assert "An error occurred during registration" in v.failure_detail
