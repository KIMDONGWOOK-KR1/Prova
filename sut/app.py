"""테스트 대상 웹앱(SUT) — 미니 로그인·회원가입·검색 앱, 두 가지 버전.

## 이 앱의 목적

Prova가 증명해야 하는 명제는 "기획서에 적힌 검증 규칙이 구현에 빠져 있으면
Prova가 그것을 짚어낸다" 이다. 그걸 확인하려면 같은 기획서를 두고
'제대로 만든 구현'과 '규칙을 빠뜨린 구현'이 둘 다 있어야 한다.

    /good/login    fixtures/specs/login_spec.md 를 전부 지킨 구현   → 전 케이스 PASS 기대
    /bad/login     의도적으로 3가지를 빠뜨린 구현                   → 4건 FAIL 기대
    /good/signup   fixtures/specs/signup_spec.md 를 전부 지킨 구현  → 전 케이스 PASS 기대
    /bad/signup    의도적으로 3가지를 빠뜨린 구현                   → 3건 FAIL 기대
    /good/search   fixtures/specs/search_spec.md 를 전부 지킨 구현  → 전 케이스 PASS 기대
    /bad/search    의도적으로 3가지를 빠뜨린 구현                   → 3건 FAIL 기대

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

## bad 검색에 심은 의도적 불일치 3종

검색 화면은 검증 축이 다르다. 지금까지는 '규칙을 어긴 값에 에러가 뜨는가' 였는데,
검색은 '정상 입력에 정해진 결과가 나오는가' 다. 그래서 규칙 위반으로 표현할 수 없는
결함을 심을 수 있다.

    D1  영문 대소문자를 구분한다 (기획서는 구분하지 않는다고 명시)
        → 'notebook' 으로 검색하면 0건. 값에 흠이 없는데 결과가 틀린 사례로,
           규칙 위반으로는 표현할 수 없다. 기획서 예시(scenarios)만이 잡아낸다.
    D2  결과가 0건일 때 안내 문구를 노출하지 않는다
        → 빈 화면이 된다. '틀린 것을 보여준다' 가 아니라 '보여줘야 할 것을 안
           보여준다' 는 누락이다.
    D3  검색어 최소 길이 검증 미구현 (최대 길이만 확인)
        → 회원가입 C3 와 같은 종류지만, 규칙 기반 경로가 이 화면에서도 도는지
           확인하는 역할을 한다.

D1 이 이 화면을 추가한 이유다. 로그인·회원가입의 결함은 모두 '값을 검사하지
않았다' 였고 위반값 생성으로 잡혔다. D1 은 검사 자체는 하는데 **검사 방법이
기획서와 다르다.** 그걸 잡으려면 기획서가 입력과 기대 결과를 짝으로 제시해야
한다 — models.Scenario 가 그 자리다.

## 결함 3개인데 FAIL 이 4건인 이유

D1 이 두 경로에 동시에 잡힌다. 'notebook' 의 건수 문구가 안 뜨고(문구 경로),
결과 목록도 렌더되지 않는다(건수 경로). 중복 보고가 아니라 두 경로가 서로를
대신하지 못한다는 뜻이다 — 구현이 문구는 올바르게 찍고 목록만 빠뜨리면 문구
경로는 통과하고 건수 경로만 잡는다.

D2 는 반대로 문구 경로에만 잡힌다. 0건일 때 목록이 없는 것은 정상이므로 건수
케이스는 PASS 다. 건수 경로가 D2 까지 잡겠다고 나서면 오탐이 된다.

## bad 에 심은 '화면 사이' 불일치 1종

    E1  회원가입이 계정을 실제로 등록하지 않는다
        → 가입은 완료되고 환영 화면까지 보여주는데, 그 계정으로 로그인이 안 된다.

**화면 하나만 보면 어느 쪽도 결함이 아니다.** 회원가입 화면은 입력을 검증하고
완료 화면을 띄우므로 회원가입 케이스 14건이 이 결함과 무관하게 통과한다. 로그인
화면도 등록된 계정(user@test.com)으로는 정상 동작하므로 로그인 케이스 7건이
통과한다. 결함은 두 화면 사이에 있고, 이어서 밟아야만 드러난다.

E1 이 흐름 검증(models.Flow)을 만든 이유다. 실무에서 troubles 로 이어지는
기획-구현 불일치가 대개 이 모양이다 — 화면 단위로는 다 맞는데 이어 붙이면
안 되는 것.

## 변형별로 상태를 나눠 두는 이유

REGISTERED 를 good/bad 가 공유하면 good 이 가입시킨 계정을 bad 의 로그인이
찾아내고, **E1 이 good 을 한 번 돌린 뒤에는 사라진다.** 실행 순서에 따라 결과가
달라지는 테스트는 결과를 신뢰할 수 없다.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Prova SUT — 미니 로그인·회원가입·검색 앱")

# 기획서 §5 테스트 계정.
#
# 변형별로 따로 둔다. 공유하면 good 이 가입시킨 계정을 bad 의 로그인이 찾아내,
# **bad 에 심은 결함이 good 을 한 번 돌린 뒤에는 사라진다.** 실행 순서에 따라
# 결과가 달라지는 테스트는 결과를 신뢰할 수 없다.
REGISTERED = {
    "good": {"user@test.com": "Abcd123!"},
    "bad": {"user@test.com": "Abcd123!"},
}

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

# 검색 기획서에 정의된 문구
MSG_QUERY_REQUIRED = "검색어를 입력하세요."
MSG_QUERY_LENGTH = "검색어는 2자 이상 50자 이하로 입력하세요."
MSG_NO_RESULTS = "검색 결과가 없습니다."

# 검색 대상 데이터.
#
# 읽기 전용이다 — 검색은 상태를 바꾸지 않으므로 테스트끼리 간섭하지 않고, SUT 를
# 세션당 한 번만 띄워도 된다(tests/conftest.py 의 픽스처 범위 근거).
#
# 'Notebook' 3건은 기획서 §6 예시("notebook -> 검색 결과 3건")를 성립시키는
# 데이터다. 대소문자를 구분하지 않아야 소문자 검색으로도 3건이 나온다.
PRODUCTS = (
    "Notebook Pro 15",
    "Notebook Air 13",
    "Notebook Slim 14",
    "무선 마우스",
    "기계식 키보드",
    "USB-C 허브",
)

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


# slow 변형이 결과를 DOM 에 넣기까지 기다리는 시간.
#
# 400ms 로 잡은 근거: 사람은 거의 눈치채지 못하고, 도구는 기다리지 않으면 확실히
# 놓치는 구간이다. 너무 길게 잡으면 '도구가 기다린다' 를 확인하는 것이 아니라
# '얼마나 오래 기다리나' 를 재는 시험이 된다.
SLOW_DELAY_MS = 400


def render_login(request: Request, variant: str, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"variant": variant, "error": error,
                 "slow_delay_ms": SLOW_DELAY_MS},
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


def render_search(
    request: Request,
    variant: str,
    query: str | None = None,
    error: str | None = None,
    results: list[str] | None = None,
    count: int | None = None,
    empty_message: str | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context={
            "variant": variant, "query": query, "error": error,
            "results": results or [], "count": count,
            "empty_message": empty_message,
            "slow_delay_ms": SLOW_DELAY_MS,
        },
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
    if REGISTERED["good"].get(email) != password:
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

    if REGISTERED["bad"].get(email) != password:
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
    # 계정을 실제로 등록한다. 기획서 §7 이 "가입한 계정으로 로그인할 수 있다" 고
    # 적어 둔 흐름이 성립하려면 이 한 줄이 있어야 한다.
    REGISTERED["good"][email] = password
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

    # E1: 계정을 등록하지 않는다.
    #
    # 화면 하나만 보면 결함이 아니다 — 입력 검증도 하고 완료 화면도 보여준다.
    # 회원가입 화면의 케이스는 이 줄이 없어도 전부 통과한다. 결함은 회원가입과
    # 로그인 '사이' 에 있고, 두 화면을 이어서 밟아야만 드러난다.
    return RedirectResponse("/bad/welcome", status_code=303)


@app.get("/bad/welcome", response_class=HTMLResponse)
def bad_welcome(request: Request):
    return render_welcome(request, "bad", "테스터")


# ---------------------------------------------------------------------------
# good/search — 기획서를 전부 지킨 구현
# ---------------------------------------------------------------------------


def find_products(term: str, *, case_sensitive: bool) -> list[str]:
    """상품명에 term 이 포함된 항목. 기획서 §2-2 는 대소문자를 구분하지 않는다.

    case_sensitive 를 인자로 둔 이유: bad 변형이 이 규칙을 어기는 것이 심어 둔
    결함(D1)이다. 두 변형이 같은 함수를 쓰되 이 한 가지만 다르게 해서, 결과 차이가
    '대소문자 처리' 에서만 나오도록 한다.
    """
    if case_sensitive:
        return [name for name in PRODUCTS if term in name]
    lowered = term.lower()
    return [name for name in PRODUCTS if lowered in name.lower()]


@app.get("/good/search", response_class=HTMLResponse)
def good_search(request: Request, query: str | None = None):
    """검색어가 오지 않았으면(첫 진입) 폼만 보여준다.

    'query 파라미터가 없다' 와 'query 가 빈 문자열이다' 를 구분하는 것이 중요하다.
    첫 진입에도 필수 입력 에러를 띄우면, 아무 조작도 하지 않은 화면에 에러가 떠
    있게 된다. 빈 검색어로 버튼을 누른 경우에만 에러가 맞다.
    """
    if query is None:
        return render_search(request, "good")

    if not query:
        return render_search(request, "good", query, error=MSG_QUERY_REQUIRED)
    if not (2 <= len(query) <= 50):
        return render_search(request, "good", query, error=MSG_QUERY_LENGTH)

    found = find_products(query, case_sensitive=False)
    if not found:
        return render_search(request, "good", query, empty_message=MSG_NO_RESULTS)
    return render_search(request, "good", query, results=found, count=len(found))


# ---------------------------------------------------------------------------
# bad/search — 의도적으로 규칙을 빠뜨린 구현
# ---------------------------------------------------------------------------


@app.get("/bad/search", response_class=HTMLResponse)
def bad_search(request: Request, query: str | None = None):
    if query is None:
        return render_search(request, "bad")

    if not query:
        return render_search(request, "bad", query, error=MSG_QUERY_REQUIRED)

    # D3: 최소 길이 검증이 없다 (최대 길이만 확인한다)
    if len(query) > 50:
        return render_search(request, "bad", query, error=MSG_QUERY_LENGTH)

    # D1: 대소문자를 구분한다 (기획서는 구분하지 않는다고 명시)
    found = find_products(query, case_sensitive=True)
    if not found:
        # D2: 결과가 없을 때 안내 문구를 노출하지 않는다 — 빈 화면이 된다
        return render_search(request, "bad", query)
    return render_search(request, "bad", query, results=found, count=len(found))


# ---------------------------------------------------------------------------
# nolabel/search — 접근성 이름이 없는 구현 (2차 경로 시험용)
# ---------------------------------------------------------------------------
#
# 검증 로직은 good 과 **완전히 같다.** 다른 것은 제출 버튼의 마크업 하나뿐이다 —
# '검색' 글자 대신 아이콘만 있어서 S3 의 네 전략이 모두 막힌다.
#
# 왜 good/bad 와 별도 변형인가: good/bad 는 '검증 로직의 유무' 하나만 다르게 두는
# 실험이다(모듈 설명 참고). 여기에 마크업 차이를 섞으면 그 실험의 변수가 둘이 된다.
#
# 이 변형이 드러내는 것은 결함의 종류가 다르다 — 검증은 다 하는데 **요소를 지목할
# 수 없다.** 기획서가 라벨을 적어 뒀는데 화면에 그 이름이 없으므로 기획-구현
# 불일치이고, 동시에 접근성 결함이다. 2차 경로는 그 화면에서도 케이스를 진행하게
# 해 주지만, 그 사실을 지우지는 않는다.


@app.get("/nolabel/search", response_class=HTMLResponse)
def nolabel_search(request: Request, query: str | None = None):
    if query is None:
        return render_search(request, "nolabel")
    if not query:
        return render_search(request, "nolabel", query, error=MSG_QUERY_REQUIRED)
    if not (2 <= len(query) <= 50):
        return render_search(request, "nolabel", query, error=MSG_QUERY_LENGTH)
    found = find_products(query, case_sensitive=False)
    if not found:
        return render_search(request, "nolabel", query, count=0,
                             empty_message=MSG_NO_RESULTS)
    return render_search(request, "nolabel", query, results=found, count=len(found))


# ---------------------------------------------------------------------------
# slow/* — 결과가 늦게 화면에 들어오는 구현 (실물 앱의 비동기 렌더링)
# ---------------------------------------------------------------------------
#
# 검증 로직은 good 과 **완전히 같다.** 다른 것은 하나뿐이다 — 서버가 보낸 에러
# 문구와 검색 결과를 브라우저가 SLOW_DELAY_MS 뒤에 DOM 에 넣는다.
#
# 왜 이 변형이 필요한가: 지금 SUT 는 동기식 폼 POST 라 응답 HTML 에 결과가 이미
# 들어 있다. 실물 웹앱은 대개 그렇지 않다 — 제출하면 fetch 를 보내고, 응답이 오면
# 화면을 갈아 끼운다. 그 사이 화면에는 아무것도 없다.
#
# Prova 가 클릭 직후 DOM 을 읽으면 그 '아무것도 없는' 상태를 보고 '기획서가 지정한
# 에러가 안 뜬다' 로 판정한다. **구현은 올바른데 FAIL 이 난다 — 오탐이다.**
# 이 변형은 그 오탐을 재현해서 도구가 기다리게 만들려고 있다.
#
# nolabel 과 같은 원칙으로 별도 변형이다: good/bad 는 '검증 로직의 유무' 하나만
# 다르게 두는 실험이고, 여기에 렌더 시점 차이를 섞으면 변수가 둘이 된다.


@app.get("/slow/login", response_class=HTMLResponse)
def slow_login_form(request: Request):
    return render_login(request, "slow")


@app.post("/slow/login", response_class=HTMLResponse)
def slow_login_submit(
    request: Request,
    email: str = Form(default=""),
    password: str = Form(default=""),
):
    # good 과 한 줄도 다르지 않다 — 렌더 시점만 템플릿이 늦춘다.
    if not email or not password:
        return render_login(request, "slow", MSG_REQUIRED)
    if not check_email_format(email):
        return render_login(request, "slow", MSG_EMAIL_FORMAT)
    if not check_password_rules(password):
        return render_login(request, "slow", MSG_PASSWORD_RULE)
    if REGISTERED["good"].get(email) != password:
        return render_login(request, "slow", MSG_NO_ACCOUNT)
    return RedirectResponse("/slow/dashboard", status_code=303)


@app.get("/slow/dashboard", response_class=HTMLResponse)
def slow_dashboard(request: Request):
    return render_dashboard(request, "slow", "user@test.com")


@app.get("/slow/search", response_class=HTMLResponse)
def slow_search(request: Request, query: str | None = None):
    if query is None:
        return render_search(request, "slow")
    if not query:
        return render_search(request, "slow", query, error=MSG_QUERY_REQUIRED)
    if not (2 <= len(query) <= 50):
        return render_search(request, "slow", query, error=MSG_QUERY_LENGTH)
    found = find_products(query, case_sensitive=False)
    if not found:
        return render_search(request, "slow", query, count=0,
                             empty_message=MSG_NO_RESULTS)
    return render_search(request, "slow", query, results=found, count=len(found))


# ---------------------------------------------------------------------------
# spa/login — 성공해도 URL 이 바뀌지 않는 구현 (클라이언트 라우팅)
# ---------------------------------------------------------------------------
#
# 검증 로직은 good 과 **완전히 같다.** 다른 것은 하나뿐이다 — 성공했을 때
# /dashboard 로 리다이렉트하지 않고 그 자리에 대시보드 내용을 렌더한다.
#
# 왜 이 변형이 필요한가: 기획서 §3 은 "/dashboard 로 이동하고 '환영합니다' 문구를
# 노출한다" 고 적었다. 지금 판정은 URL 에 '/dashboard' 가 들어 있는지를 본다.
# 클라이언트 라우팅으로 화면만 갈아 끼우는 앱에서는 그 조건이 성립하지 않는다.
#
# **이 변형의 FAIL 은 오탐이 아닐 수 있다.** 기획서가 경로를 명시했으므로 URL 이
# 그렇게 되지 않는 것은 기획-구현 불일치이고, 딥링크·새로고침·뒤로가기가 깨지는
# 실제 결함이기도 하다. 그래서 이 변형이 재는 것은 '판정이 맞는가' 가 아니라
# **'사유가 개발자에게 쓸모 있는가'** 다 — 내용은 도달했는데 경로만 다른 것과
# 아무것도 도달하지 않은 것은 고칠 곳이 다르다.


@app.get("/spa/login", response_class=HTMLResponse)
def spa_login_form(request: Request):
    return render_login(request, "spa")


@app.post("/spa/login", response_class=HTMLResponse)
def spa_login_submit(
    request: Request,
    email: str = Form(default=""),
    password: str = Form(default=""),
):
    # 검증은 good 과 한 줄도 다르지 않다.
    if not email or not password:
        return render_login(request, "spa", MSG_REQUIRED)
    if not check_email_format(email):
        return render_login(request, "spa", MSG_EMAIL_FORMAT)
    if not check_password_rules(password):
        return render_login(request, "spa", MSG_PASSWORD_RULE)
    if REGISTERED["good"].get(email) != password:
        return render_login(request, "spa", MSG_NO_ACCOUNT)
    # 여기만 다르다: 리다이렉트 없이 대시보드를 그 자리에 렌더한다.
    # URL 은 /spa/login 그대로이고 화면 내용은 대시보드다.
    return render_dashboard(request, "spa", email)


@app.get("/spa/dashboard", response_class=HTMLResponse)
def spa_dashboard(request: Request):
    return render_dashboard(request, "spa", "user@test.com")


# ---------------------------------------------------------------------------
# hashed/login · native/login — 실물 앱의 흔한 마크업 두 가지
# ---------------------------------------------------------------------------
#
# 둘 다 서버 검증 로직은 good 과 **완전히 같다.** 변수는 마크업 하나뿐이다.
#
# hashed: id 가 CSS-in-JS 해시다(id="e7f3a91b"). 기획서의 element_id 로 만드는
#         CSS selector 가 무력화된다. <label for> 는 그 해시를 가리키므로 라벨
#         연결은 살아 있다 — React/Vue 앱에서 아주 흔한 모양이다.
#         전략 네 개 중 마지막 하나만 막히면 앞의 것으로 찾아야 정상이다.
#
# native: novalidate 를 떼고 required 를 붙였다. 브라우저가 제출을 막고 자기
#         툴팁을 띄우므로 **기획서가 지정한 에러 문구가 화면에 나타나지 않는다.**
#         이 FAIL 은 오탐이 아니다 — 기획서는 그 문구를 노출한다고 적었고 구현은
#         노출하지 않는다. 재는 것은 '사유가 무엇을 말하는가' 다.


@app.get("/hashed/login", response_class=HTMLResponse)
def hashed_login_form(request: Request):
    return render_login(request, "hashed")


@app.post("/hashed/login", response_class=HTMLResponse)
def hashed_login_submit(
    request: Request,
    email: str = Form(default=""),
    password: str = Form(default=""),
):
    if not email or not password:
        return render_login(request, "hashed", MSG_REQUIRED)
    if not check_email_format(email):
        return render_login(request, "hashed", MSG_EMAIL_FORMAT)
    if not check_password_rules(password):
        return render_login(request, "hashed", MSG_PASSWORD_RULE)
    if REGISTERED["good"].get(email) != password:
        return render_login(request, "hashed", MSG_NO_ACCOUNT)
    return RedirectResponse("/hashed/dashboard", status_code=303)


@app.get("/hashed/dashboard", response_class=HTMLResponse)
def hashed_dashboard(request: Request):
    return render_dashboard(request, "hashed", "user@test.com")


@app.get("/native/login", response_class=HTMLResponse)
def native_login_form(request: Request):
    return render_login(request, "native")


@app.post("/native/login", response_class=HTMLResponse)
def native_login_submit(
    request: Request,
    email: str = Form(default=""),
    password: str = Form(default=""),
):
    if not email or not password:
        return render_login(request, "native", MSG_REQUIRED)
    if not check_email_format(email):
        return render_login(request, "native", MSG_EMAIL_FORMAT)
    if not check_password_rules(password):
        return render_login(request, "native", MSG_PASSWORD_RULE)
    if REGISTERED["good"].get(email) != password:
        return render_login(request, "native", MSG_NO_ACCOUNT)
    return RedirectResponse("/native/dashboard", status_code=303)


@app.get("/native/dashboard", response_class=HTMLResponse)
def native_dashboard(request: Request):
    return render_dashboard(request, "native", "user@test.com")


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(
        "<h1>Prova SUT</h1>"
        "<ul>"
        "<li><a href='/good/login'>/good/login — 기획서 준수 구현</a></li>"
        "<li><a href='/bad/login'>/bad/login — 의도적 불일치 구현</a></li>"
        "<li><a href='/good/signup'>/good/signup — 기획서 준수 구현</a></li>"
        "<li><a href='/bad/signup'>/bad/signup — 의도적 불일치 구현</a></li>"
        "<li><a href='/good/search'>/good/search — 기획서 준수 구현</a></li>"
        "<li><a href='/bad/search'>/bad/search — 의도적 불일치 구현</a></li>"
        "</ul>"
        "<p>도구의 한계를 재는 변형 — 검증 로직은 good 과 같고 변수 하나만 다르다:</p>"
        "<ul>"
        "<li><a href='/nolabel/search'>/nolabel/search — 아이콘 버튼 (접근성 이름 없음)</a></li>"
        "<li><a href='/slow/login'>/slow/login — 결과가 400ms 뒤에 나타난다</a></li>"
        "<li><a href='/slow/search'>/slow/search — 목록이 400ms 뒤에 나타난다</a></li>"
        "<li><a href='/spa/login'>/spa/login — 성공해도 URL 이 바뀌지 않는다</a></li>"
        "<li><a href='/hashed/login'>/hashed/login — id 가 CSS-in-JS 해시다</a></li>"
        "<li><a href='/native/login'>/native/login — 브라우저 기본 검증이 제출을 막는다</a></li>"
        "</ul>"
    )
