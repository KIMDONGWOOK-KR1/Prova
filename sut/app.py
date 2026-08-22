"""테스트 대상 웹앱(SUT) — 여섯 화면, 두 가지 버전(+ 도구의 한계를 재는 변형).

## 이 앱의 목적

Prova가 증명해야 하는 명제는 "기획서에 적힌 검증 규칙이 구현에 빠져 있으면
Prova가 그것을 짚어낸다" 이다. 그걸 확인하려면 같은 기획서를 두고
'제대로 만든 구현'과 '규칙을 빠뜨린 구현'이 둘 다 있어야 한다.
`/good/*` 은 기획서를 전부 지킨 구현이고, `/bad/*` 는 아래 결함을 **의도적으로**
심은 구현이다. 심은 결함의 전수는 이 표 하나다 — 코드 곳곳의 주석(B1…)은 이
표의 위치 표시다.

    화면        결함  내용                                            FAIL 기대
    login       B1    비밀번호 복잡도 검증 없음                        ┐
                B2    이메일 형식 검증 없음                            │ 4건 (B3 가
                B3    기획서와 다른 에러 문구                          ┘  두 경로에 잡힘)
    signup      C1    비밀번호 확인 일치 검증 없음
                C2    약관 동의 검증 없음
                C3    닉네임 최대 길이 검증 없음
                C4    가입 경로 선택 목록에서 한 항목 누락
                E1    계정을 등록하지 않음 (가입 후 로그인 흐름이 깨진다)
                E2    환영 화면의 '로그인하러 가기' 링크가 엉뚱한 경로(/search)
    search      D1    대소문자를 구분함 (기획서는 구분하지 않음)        ┐ 4건 (D1 이
                D2    결과 없음 안내 문구 미노출                       │  문구·건수 두
                D3    최소 길이 검증 없음                              ┘  경로에 잡힘)
    find-account F1   계정 존재 여부를 문구로 노출 (금지 문구)
    product     P1    가격 숫자 검증 없음
                P2    로그인 가드 없음
    orders      O1    주문 목록이 오름차순 (기획서는 최신순)
                O2    합계가 마지막 표시 행을 뺀 값 (O1 과 겹쳐 569,000)

`/slow`·`/spa`·`/hashed`·`/native`·`/nolabel`·`/slowleak` 은 검증 로직이 good 과
같고 **도구를 시험하는 변수 하나**만 다른 변형이다(아래 등록기 참고). 이 변형들은
login·signup·search 에만 있다 — product 에 넣지 않은 것은 범위 결정이다.
orders 에는 `/table`(good 과 같음)·`/badtable`(bad 와 같음)이 있다 — aria-label 이
하나도 없는 순수 `<table>` 마크업으로, 시험하는 변수는 '표 머리글 탐지' 하나다
(2026-08-22).

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

## 상품등록에 처음 생긴 세션

로그인이 성공하면 서버가 쿠키를 내려준다: `session_{variant}=ok`. 서명하지
않는다 — 이 쿠키는 보안 경계가 아니라 '로그인했다' 는 사실만 표시하는
테스트용 상태다. 상품등록 화면은 이 쿠키가 있어야 열린다.

## bad 상품등록에 심은 의도적 불일치 2종

    P1  가격이 숫자인지 검사하지 않는다 (재고수량 검사는 남아 있다)
        → "만원" 같은 값도 통과해 등록된다. 같은 화면 안에 있는 두 숫자
           필드 중 하나만 결함이 있다 — 필드마다 케이스를 나눠야 잡히는
           결함이다.
    P2  로그인 가드가 없다
        → 쿠키 없이 URL 을 직접 열어도 화면이 뜬다. E1 과 반대 방향의
           결함이다 — E1 은 화면 사이를 이어야 드러났고, P2 는 화면 하나
           만으로 드러난다(가드 자체가 그 화면의 책임이기 때문이다).

## 변형별로 상태를 나눠 두는 이유

REGISTERED 를 good/bad 가 공유하면 good 이 가입시킨 계정을 bad 의 로그인이
찾아내고, **E1 이 good 을 한 번 돌린 뒤에는 사라진다.** 실행 순서에 따라 결과가
달라지는 테스트는 결과를 신뢰할 수 없다.

## bad 주문조회에 심은 의도적 불일치 2종

로그인 가드는 상품등록과 동일하게 양쪽 변형에 다 있다 — 여기서 재는 변수는
정렬·합계 두 가지뿐이라, 가드까지 갈리면 세 번째 변수가 섞인다.

    O1  주문일 오름차순(과거 → 최근)으로 정렬한다 (기획서는 내림차순을 요구)
        → 목록 자체는 다섯 건이 다 나온다. '값이 틀렸다' 가 아니라 '순서가
           틀렸다' 는, 검색 화면의 D1(대소문자)과 같은 부류의 결함이다 —
           위반값이 아니라 정상 데이터로만 잡아낼 수 있다.
    O2  합계에서 화면에 마지막으로 "표시된" 행의 금액을 뺀다
        → O1 과 맞물려 값이 달라진다: bad 는 오름차순으로 보여주므로 마지막
           표시 행이 ORD-005(1,290,000)가 되어, 합계는 1,859,000 이 아니라
           569,000 으로 뜬다. 시드가 바뀌어도 결함이 정직하게 유지되도록
           하드코딩한 값이 아니라 "표시된 행의 합 - 마지막 행" 으로 계산한다.
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
    "good": {"user@test.com": "Abcd123!", "seller@test.com": "Seller1!"},
    "bad": {"user@test.com": "Abcd123!", "seller@test.com": "Seller1!"},
}
# seller@test.com — 판매자 계정. 상품등록 전제용(기획서 §5 전제 절과 일치해야
# 한다). 양쪽 변형에 같은 자격으로 넣어 둔다 — 위와 같은 이유로 공유하지 않는다.

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

#: 기획서 §2 의 '가입 경로' 선택 목록.
#
# 템플릿이 이 값을 받아 <option> 을 그린다. 예전에는 템플릿에 항목을 직접 적어
# 두고 이 상수는 쓰이지 않았다 — 진실이 두 곳에 있었고, 이 상수를 고친 사람은
# SUT 가 바뀐다고 믿게 된다.
SIGNUP_PATHS = ("검색", "지인 추천", "광고")

#: bad 에 심은 결함 C4 — 이 항목이 화면에 없다.
#
# 기획서에 적혀 있는데 도구가 확인하지 않던 항목이었다. 정상 케이스는 첫 항목을
# 골라 넣고 그것이 있으니 통과했다.
MISSING_SIGNUP_PATH = "지인 추천"

# 검색 기획서에 정의된 문구
MSG_QUERY_REQUIRED = "검색어를 입력하세요."
MSG_QUERY_LENGTH = "검색어는 2자 이상 50자 이하로 입력하세요."
MSG_NO_RESULTS = "검색 결과가 없습니다."

# 비밀번호 찾기 기획서에 정의된 문구
MSG_RESET_SENT = "재설정 메일을 보냈습니다."

# 상품등록 기획서에 정의된 문구. 필수 입력 문구는 MSG_REQUIRED 를 그대로 쓴다 —
# 기획서의 문구가 같은데 상수를 새로 만들면 진실이 두 곳에 생긴다.
MSG_PRODUCT_NAME_LENGTH = "상품명은 50자 이내로 입력해주세요."
MSG_PRODUCT_PRICE_NUMERIC = "가격은 숫자만 입력할 수 있습니다."
MSG_PRODUCT_STOCK_NUMERIC = "재고수량은 숫자만 입력할 수 있습니다."
MSG_PRODUCT_SUCCESS = "상품이 등록되었습니다."

# 주문조회 시드 데이터. 기획서 §1-2 '테스트 주문 데이터' 표 그대로 — 시드가
# 표와 어긋나면 검증이 성립하지 않는다. 주문일 내림차순으로 적어 두었지만
# 렌더 시점에는 항상 명시적으로 다시 정렬한다(good: 내림차순, bad: O1 로
# 오름차순) — 상수의 나열 순서에 기대면 그 사실이 코드에 보이지 않는다.
SEED_ORDERS = (
    {"주문번호": "ORD-005", "주문일": "2026-08-15", "상품명": "노트북",
     "금액": 1290000, "상태": "배송중"},
    {"주문번호": "ORD-004", "주문일": "2026-08-12", "상품명": "마우스",
     "금액": 39000, "상태": "배송완료"},
    {"주문번호": "ORD-003", "주문일": "2026-08-09", "상품명": "키보드",
     "금액": 89000, "상태": "배송완료"},
    {"주문번호": "ORD-002", "주문일": "2026-08-03", "상품명": "모니터",
     "금액": 429000, "상태": "취소"},
    {"주문번호": "ORD-001", "주문일": "2026-07-28", "상품명": "케이블",
     "금액": 12000, "상태": "배송완료"},
)


def _format_amount(amount: int) -> str:
    """'1290000' -> '1,290,000원'. 판정 쪽 정규식(^[\\d,]+원?$)과 짝이다."""
    return f"{amount:,}원"


# F1: bad 가 노출하는, 노출하면 안 되는 문구.
#
# 기획서 §5 는 "계정 존재 여부를 알려주지 않는다" 를 보안 요구사항으로 적었다.
# 등록 여부에 따라 다른 문구를 노출하면 공격자가 이 화면으로 어떤 이메일이
# 가입되어 있는지 확인할 수 있다(account enumeration). 실제 취약점이다.
#
# 이 결함은 **지금까지의 어떤 결함과도 방향이 다르다** — 있어야 할 문구가 없는
# 것이 아니라, 없어야 할 문구가 있는 것이다.
MSG_NOT_REGISTERED = "등록되지 않은 이메일입니다."

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
    # 선택 목록을 서버가 넘긴다. bad 는 C4 로 한 항목을 뺀다 — 그 결함이 템플릿
    # 조건문이 아니라 여기 한 줄로 드러나야, 무엇이 실험의 변수인지 보인다.
    paths = [p for p in SIGNUP_PATHS
             if variant == "good" or p != MISSING_SIGNUP_PATH]
    return templates.TemplateResponse(
        request=request,
        name="signup.html",
        context={"variant": variant, "error": error, "signup_paths": paths},
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


def render_find_account(
    request: Request,
    variant: str,
    error: str | None = None,
    sent: str | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="find_account.html",
        context={"variant": variant, "error": error, "sent": sent,
                 "slow_delay_ms": SLOW_DELAY_MS},
    )


def render_welcome(request: Request, variant: str, nickname: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="welcome.html",
        context={"variant": variant, "nickname": nickname},
    )


def render_product(
    request: Request,
    variant: str,
    error: str | None = None,
    success: str | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="product.html",
        context={"variant": variant, "error": error, "success": success},
    )


def render_orders(
    request: Request,
    variant: str,
    orders: tuple[dict, ...],
    total: int,
    markup: str = "list",
) -> HTMLResponse:
    rows = [
        {"주문번호": o["주문번호"], "주문일": o["주문일"],
         "금액_표시": _format_amount(o["금액"])}
        for o in orders
    ]
    return templates.TemplateResponse(
        request=request,
        name="orders.html",
        context={"variant": variant, "orders": rows,
                 "total_text": _format_amount(total), "markup": markup},
    )


# ---------------------------------------------------------------------------
# 기획서를 지킨 검증 — 사본은 이 두 함수뿐이다
# ---------------------------------------------------------------------------
#
# 변형(good · slow · spa · hashed · native · nolabel)은 **검증 로직이 완전히
# 같아야 한다.** 그게 각 변형이 재려는 것의 전제다 — 렌더 시점만 다르게, 마크업만
# 다르게, 라우팅만 다르게 두고 판정이 어떻게 달라지는지 보는 실험이다.
#
# 그런데 변형마다 검증을 복사해 두면 그 전제가 **코드로 보장되지 않는다.** 한쪽만
# 고치면 그 변형이 재는 변수가 둘이 되고, 그 사실이 조용히 숨는다. 실제로 로그인
# 핸들러가 다섯 벌 있었고 한 글자씩 다른지 눈으로 대조해야 했다.
#
# 그래서 검증은 여기 한 번만 쓴다. 변형은 '다른 점' 만 선언한다.
#
# bad 는 공유하지 않는다 — bad 의 차이는 **검증 로직 자체**이고 그게 실험의 변수다.
# 그걸 여기 섞으면 이 함수가 '기획서를 지킨 검증' 이 아니게 된다.


def login_error(email: str, password: str) -> str | None:
    """로그인 검증. 통과하면 None, 아니면 화면에 노출할 문구.

    기획서 §2(입력 검증 규칙) · §4(실패 조건) · §5(테스트 계정) 그대로다.
    """
    if not email or not password:
        return MSG_REQUIRED
    if not check_email_format(email):
        return MSG_EMAIL_FORMAT
    if not check_password_rules(password):
        return MSG_PASSWORD_RULE
    if REGISTERED["good"].get(email) != password:
        return MSG_NO_ACCOUNT
    return None


def search_render_args(query: str | None) -> dict:
    """검색 결과. render_search 에 그대로 넘길 인자를 돌려준다.

    `query is None`(첫 진입)과 `query == ""`(빈 값으로 제출)을 구분하는 것이
    중요하다 — 첫 진입에도 필수 입력 에러를 띄우면 아무 조작도 하지 않은 화면에
    에러가 떠 있게 된다.
    """
    if query is None:
        return {}
    if not query:
        return {"query": query, "error": MSG_QUERY_REQUIRED}
    if not (2 <= len(query) <= 50):
        return {"query": query, "error": MSG_QUERY_LENGTH}
    found = find_products(query, case_sensitive=False)
    if not found:
        return {"query": query, "count": 0, "empty_message": MSG_NO_RESULTS}
    return {"query": query, "results": found, "count": len(found)}


# ---------------------------------------------------------------------------
# 변형 등록 — 각 변형이 다른 점은 이 표에만 있다
# ---------------------------------------------------------------------------
#
#   good     기준. 기획서를 그대로 지킨 구현
#   slow     결과를 SLOW_DELAY_MS 뒤에 DOM 에 넣는다 (템플릿)
#              실물 웹앱은 제출하면 fetch 를 보내고 응답이 오면 화면을 갈아 끼운다.
#              그 사이 화면에는 아무것도 없다. 도구가 클릭 직후 DOM 을 읽으면 그
#              빈 상태를 보고 '기획서가 지정한 에러가 안 뜬다' 로 판정한다 — 오탐.
#   hashed   id 가 CSS-in-JS 해시다 (템플릿)
#              기획서의 element_id 로 만드는 CSS selector 가 무력화된다. label for
#              는 살아 있으므로 탐지 전략 네 개 중 마지막 하나만 막힌다.
#   native   novalidate 를 떼고 required 를 붙였다 (템플릿)
#              브라우저가 제출을 막고 자기 툴팁을 띄운다. 앱의 에러 문구가 화면에
#              없으므로 도구가 '구현이 규칙을 강제하지 않는다' 고 단정했다 —
#              사실과 반대다. 검사 방법이 기획서와 다른 것이다.
#   spa      성공해도 URL 이 바뀌지 않는다 (아래 dashboard_inline)
#              기획서가 /dashboard 를 명시했으므로 FAIL 이 맞다. 확인하는 것은
#              사유가 '경로 미이동 + 문구 노출 확인' 으로 나오는가다.
#   nolabel  제출 버튼이 아이콘만 있다 (템플릿, 검색 화면)
#              접근성 이름이 없어 탐지 전략 네 개가 모두 막힌다. 2차 경로 시험용.
#
# 변형을 더할 때 검증 로직을 복사하지 않는다. 이 표에 한 줄을 더한다.

#: 로그인 화면을 가진 변형. dashboard_inline=True 면 리다이렉트하지 않는다.
LOGIN_VARIANTS = {
    "good": False,
    "slow": False,
    "hashed": False,
    "native": False,
    "spa": True,
    # 주문조회의 순수 <table> 변형 — 로그인 가드가 session_{variant} 를 보므로
    # 로그인 화면도 함께 있어야 한다.
    "table": False,
    "badtable": False,
}

#: 검색 화면을 가진 변형 (bad 는 결함이 있어 따로 둔다).
SEARCH_VARIANTS = ("good", "nolabel", "slow")


def _register_login(variant: str, dashboard_inline: bool) -> None:
    """한 변형의 로그인 화면 세 라우트를 등록한다.

    함수 이름을 변형별로 바꾸는 이유: FastAPI 가 엔드포인트 이름으로 operation_id
    를 만들므로, 같은 이름이 여럿이면 경고가 나고 문서에서 구분이 안 된다.
    """

    @app.get(f"/{variant}/login", response_class=HTMLResponse)
    def show_form(request: Request):
        return render_login(request, variant)

    @app.post(f"/{variant}/login", response_class=HTMLResponse)
    def submit(
        request: Request,
        email: str = Form(default=""),
        password: str = Form(default=""),
    ):
        error = login_error(email, password)
        if error:
            return render_login(request, variant, error)
        if dashboard_inline:
            # spa: URL 은 /{variant}/login 그대로이고 화면 내용만 대시보드다.
            return render_dashboard(request, variant, email)
        resp = RedirectResponse(f"/{variant}/dashboard", status_code=303)
        # 세션 쿠키 — 서명하지 않는다. 테스트 대상일 뿐 보안 대상이 아니기
        # 때문이다. 상품등록·주문조회의 로그인 가드가 이 쿠키 유무만 본다.
        # 변형마다 이름이 다르다(`session_{variant}`) — 모든 변형이 심는다.
        # good 에만 심으면 slow/hashed 변형에 전제 화면을 추가하는 순간 가드가
        # 깨진 것처럼 보이는데 원인은 여기 세 줄이다 (2026-08-22 정리).
        resp.set_cookie(f"session_{variant}", "ok")
        return resp

    @app.get(f"/{variant}/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request):
        return render_dashboard(request, variant, "user@test.com")

    for fn, suffix in ((show_form, "form"), (submit, "submit"),
                       (dashboard, "dashboard")):
        fn.__name__ = f"{variant}_login_{suffix}"


def _register_search(variant: str) -> None:
    @app.get(f"/{variant}/search", response_class=HTMLResponse)
    def search(request: Request, query: str | None = None):
        return render_search(request, variant, **search_render_args(query))

    search.__name__ = f"{variant}_search"


for _variant, _inline in LOGIN_VARIANTS.items():
    _register_login(_variant, _inline)

for _variant in SEARCH_VARIANTS:
    _register_search(_variant)


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
    resp = RedirectResponse("/bad/dashboard", status_code=303)
    # 세션 쿠키 — 서명하지 않는다. 테스트 대상일 뿐 보안 대상이 아니기 때문이다.
    resp.set_cookie("session_bad", "ok")
    return resp


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
# good/product — 기획서를 전부 지킨 구현
# ---------------------------------------------------------------------------


@app.get("/good/product", response_class=HTMLResponse)
def good_product_form(request: Request):
    if "session_good" not in request.cookies:
        return RedirectResponse("/good/login", status_code=303)
    return render_product(request, "good")


@app.post("/good/product", response_class=HTMLResponse)
def good_product_submit(
    request: Request,
    name: str = Form(default=""),
    price: str = Form(default=""),
    stock: str = Form(default=""),
):
    if "session_good" not in request.cookies:
        return RedirectResponse("/good/login", status_code=303)
    if not name or not price or not stock:
        return render_product(request, "good", error=MSG_REQUIRED)
    if len(name) > 50:
        return render_product(request, "good", error=MSG_PRODUCT_NAME_LENGTH)
    if not price.isdigit():
        return render_product(request, "good", error=MSG_PRODUCT_PRICE_NUMERIC)
    if not stock.isdigit():
        return render_product(request, "good", error=MSG_PRODUCT_STOCK_NUMERIC)
    return render_product(request, "good", success=MSG_PRODUCT_SUCCESS)


# ---------------------------------------------------------------------------
# good/orders — 기획서를 전부 지킨 구현
# ---------------------------------------------------------------------------


def _good_orders_data() -> tuple[list[dict], int]:
    rows = sorted(SEED_ORDERS, key=lambda o: o["주문일"], reverse=True)
    return rows, sum(o["금액"] for o in rows)


@app.get("/good/orders", response_class=HTMLResponse)
def good_orders(request: Request):
    if "session_good" not in request.cookies:
        return RedirectResponse("/good/login", status_code=303)
    rows, total = _good_orders_data()
    return render_orders(request, "good", rows, total)


# table — good 과 데이터가 같고 마크업만 aria-label 없는 순수 <table> 이다.
@app.get("/table/orders", response_class=HTMLResponse)
def table_orders(request: Request):
    if "session_table" not in request.cookies:
        return RedirectResponse("/table/login", status_code=303)
    rows, total = _good_orders_data()
    return render_orders(request, "table", rows, total, markup="table")


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
# bad/product — 의도적으로 규칙을 빠뜨린 구현
# ---------------------------------------------------------------------------


@app.get("/bad/product", response_class=HTMLResponse)
def bad_product_form(request: Request):
    # P2: 로그인 가드가 없다 — 쿠키 유무를 확인하지 않는다
    return render_product(request, "bad")


@app.post("/bad/product", response_class=HTMLResponse)
def bad_product_submit(
    request: Request,
    name: str = Form(default=""),
    price: str = Form(default=""),
    stock: str = Form(default=""),
):
    # P2: 로그인 가드가 없다 — 쿠키 유무를 확인하지 않는다
    if not name or not price or not stock:
        return render_product(request, "bad", error=MSG_REQUIRED)
    if len(name) > 50:
        return render_product(request, "bad", error=MSG_PRODUCT_NAME_LENGTH)

    # P1: 가격이 숫자인지 검사하지 않는다 (price.isdigit() 호출 누락)

    if not stock.isdigit():
        return render_product(request, "bad", error=MSG_PRODUCT_STOCK_NUMERIC)
    return render_product(request, "bad", success=MSG_PRODUCT_SUCCESS)


# ---------------------------------------------------------------------------
# bad/orders — 의도적으로 심은 결함 O1(정렬)·O2(합계)
# ---------------------------------------------------------------------------
#
# 로그인 가드는 good 과 동일하다(P2 와 반대) — 여기서 재는 변수는 O1·O2 뿐이라
# 가드까지 다르게 두면 세 번째 변수가 섞인다.


@app.get("/bad/orders", response_class=HTMLResponse)
def bad_orders(request: Request):
    if "session_bad" not in request.cookies:
        return RedirectResponse("/bad/login", status_code=303)
    # O1: 오름차순(과거 → 최근)으로 정렬한다. 기획서는 내림차순을 요구한다.
    rows, total = _bad_orders_data()
    return render_orders(request, "bad", rows, total)


def _bad_orders_data() -> tuple[list[dict], int]:
    # O1: 오름차순(과거 → 최근)으로 정렬한다. 기획서는 내림차순을 요구한다.
    rows = sorted(SEED_ORDERS, key=lambda o: o["주문일"])
    # O2: 합계에서 화면에 마지막으로 "표시된" 행의 금액을 뺀다. O1 때문에
    # bad 는 오름차순으로 보여주므로 마지막 표시 행은 ORD-005(1,290,000)다 —
    # 합계 = 1,859,000 - 1,290,000 = 569,000. 하드코딩하지 않고 "표시된 행의
    # 합 - 마지막 행" 으로 계산해, 시드가 바뀌어도 결함이 정직하게 유지되게
    # 한다.
    return rows, sum(o["금액"] for o in rows) - rows[-1]["금액"]


# badtable — bad 와 결함(O1·O2)이 같고 마크업만 순수 <table> 이다.
@app.get("/badtable/orders", response_class=HTMLResponse)
def badtable_orders(request: Request):
    if "session_badtable" not in request.cookies:
        return RedirectResponse("/badtable/login", status_code=303)
    rows, total = _bad_orders_data()
    return render_orders(request, "badtable", rows, total, markup="table")


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
# find-account — 비밀번호 찾기 (1차 범위의 네 번째 화면)
# ---------------------------------------------------------------------------
#
# 이 화면이 앞의 셋과 다른 점: **없어야 할 것이 없는지**를 확인해야 한다.
#
# 기획서 §5 가 "계정 존재 여부를 알려주지 않는다" 를 요구한다. good 은 등록
# 여부와 무관하게 같은 문구를 노출하고, bad 는 미등록 이메일에 다른 문구를
# 노출한다(F1). bad 의 결함은 '검증이 빠진 것' 이 아니라 **정보를 더 준 것**이다.
#
# 검증 규칙(필수·형식)은 good/bad 가 동일하다. 변수를 하나로 두기 위해서다 —
# 규칙 검증까지 빼면 이 화면이 확인하려는 F1 이 다른 FAIL 에 섞인다.


# slowleak — bad 와 같은 결함인데 누출 문구가 늦게 나타난다.
#
# 대기 로직이 '금지 문구가 없다' 를 첫 판정에서 확정하면 이 노출을 못 본다.
# 그건 대기를 넣으면서 새로 생기는 미탐이므로 회귀로 못 박아야 한다
# (nodes._verify_when_ready 의 watching_for_leak 참고).


def _find_account_error(variant: str, email: str) -> str | None:
    """비밀번호 찾기 검증. 통과하면 None, 아니면 노출할 문구.

    F1(계정 존재 여부 노출)만 변형에 따라 갈린다 — 그게 실험의 변수다.
    입력 검증(필수·형식)은 어느 변형에서도 같다.
    """
    if not email:
        return MSG_REQUIRED
    if not check_email_format(email):
        return MSG_EMAIL_FORMAT
    # F1: bad 계열은 등록 여부에 따라 다른 문구를 노출한다. 기획서 §5 위반이고
    # 실제 취약점이다(account enumeration).
    if variant != "good" and email not in REGISTERED["bad"]:
        return MSG_NOT_REGISTERED
    return None


for _variant in ("good", "bad", "slowleak"):
    def _register_find_account(variant: str) -> None:
        @app.get(f"/{variant}/find-account", response_class=HTMLResponse)
        def show_form(request: Request):
            return render_find_account(request, variant)

        @app.post(f"/{variant}/find-account", response_class=HTMLResponse)
        def submit(request: Request, email: str = Form(default="")):
            error = _find_account_error(variant, email)
            if error:
                return render_find_account(request, variant, error=error)
            return render_find_account(request, variant, sent=MSG_RESET_SENT)

        show_form.__name__ = f"{variant}_find_account_form"
        submit.__name__ = f"{variant}_find_account_submit"

    _register_find_account(_variant)


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
        "<li><a href='/good/find-account'>/good/find-account — 기획서 준수 구현</a></li>"
        "<li><a href='/bad/find-account'>/bad/find-account — 계정 존재 여부를 노출</a></li>"
        "<li><a href='/good/product'>/good/product — 기획서 준수 구현 (로그인 필요)</a></li>"
        "<li><a href='/bad/product'>/bad/product — 로그인 가드·가격 숫자 검사 누락</a></li>"
        "<li><a href='/good/orders'>/good/orders — 기획서 준수 구현 (로그인 필요)</a></li>"
        "<li><a href='/bad/orders'>/bad/orders — 정렬(O1)·합계(O2) 결함</a></li>"
        "<li><a href='/table/orders'>/table/orders — good 과 같고 마크업만 순수 &lt;table&gt;</a></li>"
        "<li><a href='/badtable/orders'>/badtable/orders — bad 와 같고 마크업만 순수 &lt;table&gt;</a></li>"
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
