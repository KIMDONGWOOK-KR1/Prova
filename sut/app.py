"""테스트 대상 웹앱(SUT) — 미니 로그인 앱, 두 가지 버전.

## 이 앱의 목적

Prova가 증명해야 하는 명제는 "기획서에 적힌 검증 규칙이 구현에 빠져 있으면
Prova가 그것을 짚어낸다" 이다. 그걸 확인하려면 같은 기획서를 두고
'제대로 만든 구현'과 '규칙을 빠뜨린 구현'이 둘 다 있어야 한다.

    /good/login   fixtures/specs/login_spec.md 를 전부 지킨 구현 → 전 케이스 PASS 기대
    /bad/login    의도적으로 3가지를 빠뜨린 구현            → 3건 FAIL 기대

## 중요: 두 버전의 HTML 마크업은 완전히 동일하다

라벨·placeholder·버튼 텍스트·DOM 구조가 같아야 한다. 그래야 두 실행의 차이가
'검증 로직의 유무'에서만 나온다. 마크업이 다르면 selector 탐지 성공률이라는
변수가 끼어들어, FAIL이 불일치 때문인지 요소를 못 찾아서인지 구분할 수 없다.

## bad 버전에 심은 의도적 불일치 3종

    B1  비밀번호 복잡도(대문자·특수문자) 검증 미구현
        → "abcd1234"로도 통과됨. 기획서가 요구한 규칙이 구현에 없는 전형적 사례.
    B2  이메일 형식 검증 누락
        → "not-an-email"도 통과됨.
    B3  미등록 계정 에러 문구 불일치
        → 기획서 "이메일 또는 비밀번호가 올바르지 않습니다."
           구현   "로그인 정보를 확인해주세요."

B1·B2는 '규칙 누락'(에러가 떠야 하는데 안 뜬다), B3는 '문구 불일치'(에러는
뜨지만 문구가 다르다)다. 실패 유형이 둘 다 있어야 리포트의 원인 분류가
제대로 도는지 확인할 수 있다.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Prova SUT — 미니 로그인 앱")

# 기획서 §5 테스트 계정
REGISTERED = {"user@test.com": "Abcd123!"}

# 기획서에 정의된 에러 메시지 (good 버전이 사용)
MSG_REQUIRED = "필수 입력 항목입니다."
MSG_EMAIL_FORMAT = "올바른 이메일 형식을 입력하세요."
MSG_PASSWORD_RULE = "비밀번호는 8자 이상이며 대문자·특수문자를 각 1자 이상 포함해야 합니다."
MSG_NO_ACCOUNT = "이메일 또는 비밀번호가 올바르지 않습니다."

# bad 버전의 B3 — 기획서와 다른 문구
MSG_NO_ACCOUNT_WRONG = "로그인 정보를 확인해주세요."

SPECIAL_CHARS = r"""!@#$%^&*()_+-=[]{};':\"\|,.<>/?~`"""


def check_email_format(email: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email))


def check_password_rules(pw: str) -> bool:
    """기획서 §2-1 비밀번호 규칙: 8자 이상 + 대문자 1자 이상 + 특수문자 1자 이상."""
    return (
        len(pw) >= 8
        and any(c.isupper() for c in pw)
        and any(c in SPECIAL_CHARS for c in pw)
    )


def render_login(request: Request, variant: str, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"variant": variant, "error": error},
    )


def render_dashboard(request: Request, variant: str, email: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"variant": variant, "email": email},
    )


# ---------------------------------------------------------------------------
# good — 기획서를 전부 지킨 구현
# ---------------------------------------------------------------------------


@app.get("/good/login", response_class=HTMLResponse)
def good_login_form(request: Request):
    return render_login(request, "good")


@app.post("/good/login", response_class=HTMLResponse)
def good_login_submit(
    request: Request,
    email: str = Form(default=""),
    password: str = Form(default=""),
):
    if not email or not password:
        return render_login(request, "good", MSG_REQUIRED)
    if not check_email_format(email):
        return render_login(request, "good", MSG_EMAIL_FORMAT)
    if not check_password_rules(password):
        return render_login(request, "good", MSG_PASSWORD_RULE)
    if REGISTERED.get(email) != password:
        return render_login(request, "good", MSG_NO_ACCOUNT)
    # 성공: POST-Redirect-GET. URL이 실제로 /good/dashboard 로 전이돼야
    # 기획서의 "/dashboard 로 이동" 조건을 검증할 수 있다.
    return RedirectResponse("/good/dashboard", status_code=303)


@app.get("/good/dashboard", response_class=HTMLResponse)
def good_dashboard(request: Request):
    return render_dashboard(request, "good", "user@test.com")


# ---------------------------------------------------------------------------
# bad — 의도적으로 규칙을 빠뜨린 구현
# ---------------------------------------------------------------------------


@app.get("/bad/login", response_class=HTMLResponse)
def bad_login_form(request: Request):
    return render_login(request, "bad")


@app.post("/bad/login", response_class=HTMLResponse)
def bad_login_submit(
    request: Request,
    email: str = Form(default=""),
    password: str = Form(default=""),
):
    if not email or not password:
        return render_login(request, "bad", MSG_REQUIRED)

    # B2: 이메일 형식 검증이 없다 (check_email_format 호출 누락)
    # B1: 비밀번호 복잡도 검증이 없다 (check_password_rules 호출 누락)

    if REGISTERED.get(email) != password:
        # B3: 기획서와 다른 문구를 쓴다
        return render_login(request, "bad", MSG_NO_ACCOUNT_WRONG)
    return RedirectResponse("/bad/dashboard", status_code=303)


@app.get("/bad/dashboard", response_class=HTMLResponse)
def bad_dashboard(request: Request):
    return render_dashboard(request, "bad", "user@test.com")


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(
        "<h1>Prova SUT</h1>"
        "<ul>"
        "<li><a href='/good/login'>/good/login — 기획서 준수 구현</a></li>"
        "<li><a href='/bad/login'>/bad/login — 의도적 불일치 구현</a></li>"
        "</ul>"
    )
