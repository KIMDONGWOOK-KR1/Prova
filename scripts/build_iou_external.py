"""우리가 안 만든 웹앱 화면으로 탐지 정확도 시험지를 굳힌다 (VLM 없이 돈다).

    uv run python scripts/build_iou_external.py                      -> runs/iou-external/
    uv run python scripts/eval_vlm_iou.py --dataset runs/iou-external/dataset.json \\
        --out runs/iou-external/result-qwen3.5-4b-awq

## 왜 따로 재는가

`fixtures/iou` 시험지(18장 · 77항목)는 전부 **우리 SUT 화면**이다. 우리가 만든 마크업이라
깔끔하고 모양이 비슷하다. 실물 사이트에는 광고, 아이콘만 있는 버튼, 촘촘한 폼, 영어
라벨이 있다. 모델 교체(2026-09-28)의 이득 — 성공률 57→81%, 없는 것을 있다고 한 비율
71→7% — 이 거기서도 유지되는지는 SUT 시험지로는 알 수 없다.

화면은 스파이크 1~3 에서 도구를 돌려 본 7곳이다(`docs/measurements/external-sites-*.md`).

## 굳히는 방법은 build_iou_dataset 과 같다

정답은 손으로 적은 selector 로 잰다(도구가 찾을 수 있는 것만 시험지에 들어가지 않게).
없는 요소는 selector 가 0개로 풀리는 것을 확인한 뒤에 넣는다. 정답이 하나로 정해지지
않으면 멈춘다 — 사이트가 바뀐 것이고, 조용히 건너뛰면 어려운 문제만 빠진 시험지가 된다.
형식이 같아서 채점은 `eval_vlm_iou.py --dataset` 이 그대로 한다.

## 다른 점 셋

1. **보이는 화면 밖의 요소는 채점하지 않고 따로 센다.** 파이프라인의 2차 경로는 보이는
   화면만 찍어 모델에 준다(`dom_locator.heal_with_vlm` 의 `page.screenshot()`). 화면 밖
   요소는 모델이 볼 수 없으니 IoU 를 물을 수 없다 — 대신 그 수가 '2차 경로가 닿지 못하는
   요소' 라는 사실 자체로 보고된다(`outside_viewport`).
2. **저장소에 넣지 않는다(`runs/`).** 남의 사이트 그림이다 — 스파이크 때 기획서·리포트를
   넣지 않은 것과 같다. 정답표(이 파일)가 저장소에 있으니 누구나 다시 굳힐 수 있다. 대신
   점수는 **그날의 화면**에 대한 것이라 `captured_at` 과 `dataset_id` 를 함께 적는다.
3. **앱 도장(sut_build)이 없다.** 남의 사이트는 도장을 내지 않는다. 이 시험지는 저장된
   그림만 채점하므로(`eval_vlm_iou`) 도장 없이도 성립한다 — 라이브 화면에 좌표를 재생하는
   채점(관문 재생 등)에는 쓰지 않는다.

## 라벨은 사이트가 보여 주는 말 그대로 묻는다

실물 기획서는 그 화면의 말로 적힌다. 'Username' 을 '아이디' 로 바꿔 물으면 모델의 번역
능력까지 섞여 재진다.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_iou_dataset import VIEWPORT, Target, build_payload, normalize  # noqa: E402
from prova.s3_grounder.dom_locator import VLM_HINTS  # noqa: E402


@dataclass(frozen=True)
class State:
    """한 장의 외부 화면.

    Attributes:
        url: 처음 여는 주소.
        steps: 연 뒤에 할 일 ("fill", selector, 값) / ("click", selector, "").
            로그인 뒤 화면·에러 화면을 만든다.
    """

    state_id: str
    url: str
    note: str
    targets: tuple[Target, ...]
    steps: tuple[tuple[str, str, str], ...] = ()


def T(name, kind, selector):
    return Target(name, kind, selector)


def NO(name, kind, selector):
    return Target(name, kind, selector, present=False)


PTA = "https://practicetestautomation.com/practice-test-login/"
PTA_LOGIN = (T("Username", "input", "#username"),
             T("Password", "input", "#password"),
             T("Submit", "button", "#submit"))

HEROKU = "https://the-internet.herokuapp.com"
HEROKU_LOGIN = (T("Username", "input", "#username"),
                T("Password", "input", "#password"),
                T("Login", "button", "button[type=submit]"))

SAUCE = "https://www.saucedemo.com/"
SAUCE_LOGIN = (T("Username", "input", "#user-name"),
               T("Password", "input", "#password"),
               T("Login", "button", "#login-button"))
SAUCE_SIGN_IN = (("fill", "#user-name", "standard_user"),
                 ("fill", "#password", "secret_sauce"),
                 ("click", "#login-button", ""))

STATES: tuple[State, ...] = (
    State("pta-empty", PTA, "practicetestautomation 로그인 · 첫 진입",
          PTA_LOGIN + (NO("Search", "input", "input[type=search]"),
                       NO("Remember me", "checkbox", "input[type=checkbox]"))),
    # 틀린 아이디 제출 뒤 화면은 넣지 않는다 — 에러 문구가 보이는 화면 아래(y≈812)에
    # 떠서 찍히는 그림이 첫 진입과 같다. 같은 그림을 한 장 더 넣으면 점수만 부풀린다.
    State("heroku-login", f"{HEROKU}/login", "the-internet 로그인 · 첫 진입",
          HEROKU_LOGIN + (NO("Remember me", "checkbox", "input[type=checkbox]"),
                          NO("Country", "select", "select"))),
    State("heroku-login-error", f"{HEROKU}/login", "the-internet 로그인 · 에러 문구가 위에 뜬 상태",
          HEROKU_LOGIN + (T("Your username is invalid!", "text", "#flash"),
                          NO("Country", "select", "select")),
          steps=(("fill", "#username", "wrong"), ("fill", "#password", "x"),
                 ("click", "button[type=submit]", ""))),
    State("heroku-tables", f"{HEROKU}/tables", "the-internet 표 · 이름 없는 표 두 개",
          (T("Example 1", "list", "table#table1"),
           T("Example 2", "list", "table#table2"),
           NO("Search", "input", "input"),
           # 'Delete' 는 없는 것으로 묻지 않는다 — 표 안에 delete 링크가 보인다.
           # selector(button) 가 0개여도 그림에는 그 말이 있다(2026-09-29 첫 채점에서
           # 모델이 그 링크를 가리켰고, 틀린 것은 정답표였다).
           NO("Submit", "button", "button"))),
    State("sauce-login", SAUCE, "saucedemo 로그인 · 첫 진입",
          SAUCE_LOGIN + (NO("Cart", "link", ".shopping_cart_link"),
                         NO("Sort", "select", "select"))),
    State("sauce-login-error", SAUCE, "saucedemo 로그인 · 빈 칸 제출 에러",
          SAUCE_LOGIN + (T("Epic sadface: Username is required", "text",
                           "h3[data-test=error]"),
                         NO("Cart", "link", ".shopping_cart_link")),
          steps=(("click", "#login-button", ""),)),
    State("sauce-inventory", SAUCE, "saucedemo 상품 목록 · 아이콘 장바구니·메뉴, 카드 목록",
          (T("Cart", "link", ".shopping_cart_link"),
           T("Open Menu", "button", "#react-burger-menu-btn"),
           T("Sort", "select", "select.product_sort_container"),
           T("Products", "list", ".inventory_list"),
           NO("Password", "input", "input[type=password]"),
           NO("Login", "button", "#login-button")),
          steps=SAUCE_SIGN_IN),
    State("ae-products", "https://automationexercise.com/products",
          "automationexercise 상품 · 아이콘 검색 버튼, 광고",
          (T("Search Product", "input", "#search_product"),
           T("Search", "button", "#submit_search"),
           T("Signup / Login", "link", "a[href='/login']"),
           NO("Password", "input", "input[type=password]"),
           NO("Sort", "select", "select"))),
    State("demoqa-webtables", "https://demoqa.com/webtables",
          "demoqa 웹 표 · 즉시 거르는 검색, 광고",
          (T("Type to search", "input", "#searchBox"),
           T("Add", "button", "#addNewRecordButton"),
           T("Web Tables", "list", "table"),
           T("Show", "select", "select"),
           NO("Password", "input", "input[type=password]"),
           NO("Remember me", "checkbox", "input[type=checkbox]"))),
    State("expand-register", "https://practice.expandtesting.com/register",
          "expandtesting 회원가입 · 폼이 화면 아래에 있다",
          (T("Username", "input", "#username"),
           T("Password", "input", "#password"),
           T("Confirm Password", "input", "#confirmPassword"),
           T("Register", "button", "button[type=submit]"),
           NO("Search", "input", "input[type=search]"),
           NO("Country", "select", "select"))),
    State("parabank-register", "https://parabank.parasoft.com/parabank/register.htm",
          "parabank 회원가입 · 촘촘한 폼",
          (T("First Name", "input", "input[id='customer.firstName']"),
           T("Last Name", "input", "input[id='customer.lastName']"),
           T("SSN", "input", "input[id='customer.ssn']"),
           T("Username", "input", "input[id='customer.username']"),
           T("Password", "input", "input[id='customer.password']"),
           T("Confirm", "input", "#repeatedPassword"),
           T("Register", "button", "input[value=Register]"),
           NO("Country", "select", "select"),
           NO("Remember me", "checkbox", "input[type=checkbox]"))),
)


def inside_viewport(box: dict, viewport: dict) -> bool:
    """상자가 보이는 화면 안에 통째로 들어오는가. 2차 경로가 보는 것은 이 영역뿐이다."""
    return (box["x"] >= 0 and box["y"] >= 0
            and box["x"] + box["width"] <= viewport["width"]
            and box["y"] + box["height"] <= viewport["height"])


def clip_to_viewport(box: dict, viewport: dict) -> dict | None:
    """상자에서 보이는 화면 안의 부분만. 겹치지 않으면 None."""
    x1, y1 = max(box["x"], 0), max(box["y"], 0)
    x2 = min(box["x"] + box["width"], viewport["width"])
    y2 = min(box["y"] + box["height"], viewport["height"])
    if x2 <= x1 or y2 <= y1:
        return None
    return {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}


def open_state(page, state: State) -> None:
    # networkidle 은 광고가 끝없이 요청하는 사이트에서 오지 않는다. load 뒤 잠깐 기다린다.
    # 남의 서버라 연결이 한 번씩 끊긴다(ERR_CONNECTION_RESET). 한 번만 다시 연다.
    try:
        page.goto(state.url, wait_until="load", timeout=60000)
    except Exception:
        page.wait_for_timeout(3000)
        page.goto(state.url, wait_until="load", timeout=60000)
    page.wait_for_timeout(1500)
    for action, selector, value in state.steps:
        if action == "fill":
            page.fill(selector, value)
        else:
            page.click(selector)
            page.wait_for_load_state("load")
            page.wait_for_timeout(1500)


def capture(page, state: State, out_dir: Path) -> tuple[list[dict], list[dict]]:
    """(채점할 항목, 화면 밖이라 채점하지 않는 항목)."""
    open_state(page, state)
    image = out_dir / f"{state.state_id}.png"
    image.write_bytes(page.screenshot())

    rows, outside = [], []
    for t in state.targets:
        base = {"state_id": state.state_id, "note": state.note, "path": state.url,
                "login": False, "image": image.name, "target": t.name,
                "kind": t.kind, "hint": VLM_HINTS.get(t.kind, ""),
                "selector": t.selector}
        found = page.locator(t.selector)
        count = found.count()
        if not t.present:
            if count:
                raise AssertionError(
                    f"[{state.state_id}] '{t.name}' 은 없어야 하는데 {count}개 있습니다 "
                    f"({t.selector}). 사이트가 바뀌었습니다 — 정답표를 고치세요.")
            rows.append({**base, "present": False, "truth": None})
            continue
        if count != 1:
            raise AssertionError(
                f"[{state.state_id}] '{t.name}' selector 가 {count}개로 풀립니다 "
                f"({t.selector}). 정답이 하나로 정해지지 않으면 채점할 수 없습니다.")
        box = found.bounding_box()
        if not box or box["width"] <= 0 or box["height"] <= 0:
            raise AssertionError(
                f"[{state.state_id}] '{t.name}' 의 상자를 잴 수 없습니다 ({t.selector}).")
        px = [box["x"], box["y"], box["width"], box["height"]]
        clipped = False
        if not inside_viewport(box, VIEWPORT):
            # 목록은 아래로 길어 화면을 넘는 것이 정상이다 — 보이는 부분이 모델이 가리킬
            # 수 있는 전부이므로 정답도 그만큼으로 자른다. 입력란·버튼은 반만 보이면
            # 누를 자리가 정해지지 않으므로 자르지 않고 화면 밖으로 센다.
            visible = clip_to_viewport(box, VIEWPORT) if t.kind == "list" else None
            if visible is None:
                outside.append({**base, "present": True, "truth_px": px})
                continue
            box, clipped = visible, True
        rows.append({**base, "present": True, "clipped": clipped,
                     "truth": list(normalize(box, VIEWPORT)), "truth_px": px})
    return rows, outside


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="runs/iou-external")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    rows: list[dict] = []
    outside: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for state in STATES:
                # 화면마다 새 컨텍스트 — 앞 화면의 로그인 쿠키가 뒤 화면을 바꾸지 않게.
                ctx = browser.new_context(viewport=VIEWPORT)
                page = ctx.new_page()
                try:
                    got, out = capture(page, state, out_dir)
                finally:
                    ctx.close()
                present = sum(1 for r in got if r["present"])
                print(f"  {state.state_id:<20} 있음 {present}개 · 없음 "
                      f"{len(got) - present}개 · 화면 밖 {len(out)}개")
                rows.extend(got)
                outside.extend(out)
        finally:
            browser.close()

    for i, r in enumerate(rows):
        r["id"] = i

    payload = build_payload(rows, "")
    payload["captured_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    payload["outside_viewport"] = outside
    path = out_dir / "dataset.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(f"화면 {len(STATES)}장 · 항목 {payload['count']}개 "
          f"(있음 {payload['present']} · 없음 {payload['absent']}) · "
          f"화면 밖이라 채점 제외 {len(outside)}개")
    print(f"dataset_id={payload['dataset_id']}  ->  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
