"""테스트 대상 웹앱(SUT) — 미니 로그인·회원가입 앱, 두 가지 버전.

## 이 앱의 목적

Prova가 증명해야 하는 명제는 "기획서에 적힌 검증 규칙이 구현에 빠져 있으면
Prova가 그것을 짚어낸다" 이다. 그걸 확인하려면 같은 기획서를 두고
'제대로 만든 구현'과 '규칙을 빠뜨린 구현'이 둘 다 있어야 한다.

    /good/login    fixtures/specs/login_spec.md 를 전부 지킨 구현   → 전 케이스 PASS 기대
    /bad/login     의도적으로 3가지를 빠뜨린 구현                   → 4건 FAIL 기대
    /good/signup   fixtures/specs/signup_spec.md 를 전부 지킨 구현  → 전 케이스 PASS 기대
    /bad/signup    의도적으로 3가지를 빠뜨린 구현                   → 3건 FAIL 기대

## 중요: 두 버전의 HTML 마크업은 완전히 동일하다

라벨·placeholder·버튼 텍스트·DOM 구조가 같아야 한다. 그래야 두 실행의 차이가
'검증 로직의 유무'에서만 나온다. 마크업이 다르면 selector 탐지 성공률이라는
변수가 끼어들어, FAIL이 불일치 때문인지 요소를 못 찾아서인지 구분할 수 없다.

## bad 로그인에 심은 의도적 불일치 3종

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

## bad 회원가입에 심은 의도적 불일치 3종

로그인 화면에서 확인할 수 없었던 종류를 고른다. 같은 결함을 한 번 더 심으면
화면을 늘린 만큼의 검증력을 얻지 못한다.

    C1  비밀번호 확인 일치 검증 미구현 (교차 필드 규칙)
        → 두 값이 달라도 가입이 완료된다. 값 하나만 봐서는 판단할 수 없는
           규칙이라, 로그인 화면에는 이 종류의 결함이 없었다.
    C2  약관 동의 필수 검증 미구현 (체크박스 필수)
        → 동의하지 않아도 가입이 완료된다. 입력이 아니라 '상태' 를 검증하는
           규칙이다.
    C3  닉네임 최대 길이 검증 누락 (하한만 구현)
        → 2자 미달은 막지만 10자 초과는 통과된다. 한 요소의 규칙 중 일부만
           구현된 사례 — 규칙당 케이스 하나로 전개해야 잡히는 결함이다.

C3 는 특히 '규칙 하나당 케이스 하나' 설계의 근거가 된다. min_length 와
max_length 를 한 케이스로 묶어 검증하면 min 쪽이 걸려 에러가 뜨고, 그러면
max 검증이 없다는 사실이 가려진다.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Prova SUT — 미니 로그인·회원가입 앱")

# 기획서 §5 테스트 계정
REGISTERED = {"user@test.com": "Abcd123!"}

# 로그인 기획서에 정의된 에러 메시지 (good 버전이 사용)
MSG_REQUIRED = "필수 입력 항목입니다."
MSG_EMAIL_FORMAT = "올바른 이메일 형식을 입력하세요."
MSG_PASSWORD_RULE = "비밀번호는 8자 이상이며 대문자·특수문자를 각 1자 이상 포함해야 합니다."
MSG_NO_ACCOUNT = "이메일 또는 비밀번호가 올바르지 않습니다."

# bad 로그인의 B3 — 기획서와 다른 문구
MSG_NO_ACCOUNT_WRONG = "로그인 정보를 확인해주세요."

# 회원가입 기획서에 정의된 에러 메시지
MSG_PASSWORD_MISMATCH = "비밀번호가 일치하지 않습니다."
MSG_NICKNAME_LENGTH = "닉네임은 2자 이상 10자 이하로 입력하세요."
MSG_PATH_REQUIRED = "가입 경로를 선택하세요."
MSG_AGREE_REQUIRED = "약관에 동의해야 합니다."

SIGNUP_PATHS = ("검색", "지인 추천", "광고")

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


def render_signup(request: Request, variant: str, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="signup.html",
        context={"variant": variant, "error": error},
    )


def render_welcome(request: Request, variant: str, nickname: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="welcome.html",
        context={"variant": variant, "nickname": nickname},
    )


# ---------------------------------------------------------------------------
# good/login — 기획서를 전부 지킨 구현
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
# bad/login — 의도적으로 규칙을 빠뜨린 구현
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


# ---------------------------------------------------------------------------
# good/signup — 기획서를 전부 지킨 구현
# ---------------------------------------------------------------------------


@app.get("/good/signup", response_class=HTMLResponse)
def good_signup_form(request: Request):
    return render_signup(request, "good")


@app.post("/good/signup", response_class=HTMLResponse)
def good_signup_submit(
    request: Request,
    email: str = Form(default=""),
    password: str = Form(default=""),
    password_confirm: str = Form(default=""),
    nickname: str = Form(default=""),
    signup_path: str = Form(default=""),
    # 체크되지 않은 체크박스는 전송되지 않는다. 그래서 기본값이 None 이고,
    # 그 None 자체가 '동의하지 않음' 을 뜻한다.
    agree_terms: str | None = Form(default=None),
):
    """기획서 §4 실패 조건을 위에서 아래 순서로 검사한다.

    순서가 판정에 영향을 준다. 필수 입력 검사를 먼저 하는 이유는, 비밀번호가
    비었을 때 '일치하지 않습니다' 가 아니라 '필수 입력 항목입니다' 가 나와야
    기획서와 맞기 때문이다.
    """
    if not email or not password or not password_confirm or not nickname:
        return render_signup(request, "good", MSG_REQUIRED)
    if not signup_path:
        return render_signup(request, "good", MSG_PATH_REQUIRED)
    if not agree_terms:
        return render_signup(request, "good", MSG_AGREE_REQUIRED)
    if not check_email_format(email):
        return render_signup(request, "good", MSG_EMAIL_FORMAT)
    if not check_password_rules(password):
        return render_signup(request, "good", MSG_PASSWORD_RULE)
    if password_confirm != password:
        return render_signup(request, "good", MSG_PASSWORD_MISMATCH)
    if not (2 <= len(nickname) <= 10):
        return render_signup(request, "good", MSG_NICKNAME_LENGTH)
    return RedirectResponse("/good/welcome", status_code=303)


@app.get("/good/welcome", response_class=HTMLResponse)
def good_welcome(request: Request):
    return render_welcome(request, "good", "테스터")


# ---------------------------------------------------------------------------
# bad/signup — 의도적으로 규칙을 빠뜨린 구현
# ---------------------------------------------------------------------------


@app.get("/bad/signup", response_class=HTMLResponse)
def bad_signup_form(request: Request):
    return render_signup(request, "bad")


@app.post("/bad/signup", response_class=HTMLResponse)
def bad_signup_submit(
    request: Request,
    email: str = Form(default=""),
    password: str = Form(default=""),
    password_confirm: str = Form(default=""),
    nickname: str = Form(default=""),
    signup_path: str = Form(default=""),
    agree_terms: str | None = Form(default=None),
):
    if not email or not password or not password_confirm or not nickname:
        return render_signup(request, "bad", MSG_REQUIRED)
    if not signup_path:
        return render_signup(request, "bad", MSG_PATH_REQUIRED)

    # C2: 약관 동의 검증이 없다 (agree_terms 를 아예 보지 않는다)

    if not check_email_format(email):
        return render_signup(request, "bad", MSG_EMAIL_FORMAT)
    if not check_password_rules(password):
        return render_signup(request, "bad", MSG_PASSWORD_RULE)

    # C1: 비밀번호 확인 일치 검증이 없다 (password_confirm 은 비었는지만 본다)

    # C3: 최대 길이 검증이 없다 — 하한만 확인한다
    if len(nickname) < 2:
        return render_signup(request, "bad", MSG_NICKNAME_LENGTH)

    return RedirectResponse("/bad/welcome", status_code=303)


@app.get("/bad/welcome", response_class=HTMLResponse)
def bad_welcome(request: Request):
    return render_welcome(request, "bad", "테스터")


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(
        "<h1>Prova SUT</h1>"
        "<ul>"
        "<li><a href='/good/login'>/good/login — 기획서 준수 구현</a></li>"
        "<li><a href='/bad/login'>/bad/login — 의도적 불일치 구현</a></li>"
        "<li><a href='/good/signup'>/good/signup — 기획서 준수 구현</a></li>"
        "<li><a href='/bad/signup'>/bad/signup — 의도적 불일치 구현</a></li>"
        "</ul>"
    )
