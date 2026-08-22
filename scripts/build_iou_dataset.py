"""탐지 정확도를 재기 위한 데이터셋을 만든다 (VLM 없이 돈다).

## 왜 측정과 데이터셋 만들기를 나누는가

(지금은 지운) `scripts/probe_vlm.py` 는 요소 4개를 실행 중에 재고 끝났다. 그 숫자로는 명세서 §9 의
'탐지 성공률 ≥90%' 를 말할 수 없다 — 4개 중 하나만 틀려도 75% 이고, 4개를 골라 놓은
사람이 우리다. 표본이 작을 뿐 아니라 **매번 화면이 다시 그려지므로 같은 조건에서 두 모델을
비교할 수 없다.**

그래서 두 단계로 나눈다.

    build_iou_dataset.py   화면을 열고 정답 상자를 재서 PNG + JSON 으로 굳힌다 (GPU 불필요)
    eval_vlm_iou.py        굳은 데이터셋을 모델에 물어보고 채점한다 (GPU 필요)

굳혀 두면 모델을 바꿔도 **같은 그림, 같은 정답**으로 비교된다. 데이터셋이 매번 바뀌면
두 모델의 점수 차이가 모델 차이인지 화면 차이인지 알 수 없다.

## 정답 상자를 손으로 쓴 selector 로 재는 이유 ← 이게 가장 중요하다

정답을 `dom_locator` 로 찾으면 **도구가 이미 찾을 수 있는 요소만 데이터셋에 들어간다.**
그러면 재려는 대상(탐지 능력)으로 시험지를 만드는 셈이고, 아이콘 버튼처럼 접근성 경로가
막힌 요소는 데이터셋에서 조용히 빠진다. 2차 경로가 필요한 곳이 정확히 그런 요소들이므로,
그건 시험에서 어려운 문제만 빼는 것과 같다.

그래서 정답 selector 는 아래 표에 손으로 적는다. 이 표는 구현을 보고 쓴 것이고
`prova` 코드를 한 줄도 쓰지 않는다.

## 없는 요소도 넣는다

'물어본 것이 화면에 없을 때 없다고 말하는가' 는 이 도구의 신뢰와 직결된다. 모델은 못
찾았을 때도 그럴듯한 좌표를 낸다(`Located` docstring). 그 좌표를 누르면 엉뚱한 곳을
누르고 케이스는 진행되며, 그 FAIL 이 구현 결함으로 보고된다 — 오탐이다.

그래서 화면에 없는 요소를 묻는 항목을 함께 굳힌다. `absent` 항목은 selector 가 0개로
풀리는 것을 **확인한 뒤** 데이터셋에 넣는다. 없다고 가정하고 넣으면, 실은 있는데
없다고 적어 둔 채로 채점하게 된다.

## 상태를 여러 개 만드는 이유

같은 화면이라도 에러 문구가 뜨면 아래 요소가 전부 밀린다. 2차 경로가 실제로 호출되는
시점은 케이스 도중이므로 화면에는 이미 내용이 있다. 첫 진입 화면만 재면 가장 쉬운
조건만 재는 것이다.

    빈 화면 · 값이 채워진 화면 · 에러가 뜬 화면 · 결과 목록이 있는 화면 · 결과 0건 화면

## 산출물

    fixtures/iou/dataset.json   항목 목록 + dataset_id(내용 해시)
    fixtures/iou/*.png          화면 이미지

`runs/` 가 아니라 `fixtures/` 에 두는 이유: `runs/` 는 gitignore 라 다른 사람이 **같은
시험지로** 채점할 수 없다. 굳혀 둔 뜻이 사라진다. 220KB 이므로 저장소에 두어도 된다.

`dataset_id` 는 항목 내용의 해시다. 채점 결과에 이 값을 함께 적어 두면, 나중에 숫자만
남았을 때 그것이 어느 시험지의 점수인지 확인할 수 있다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

VIEWPORT = {"width": 1280, "height": 800}

#: 요소 종류 -> 모델에게 줄 힌트. 파이프라인이 쓰는 것과 같은 표를 쓴다
#: (s3_grounder.dom_locator.VLM_HINTS). 여기서 다른 말을 쓰면 측정 조건이 실행 조건과
#: 달라지고, 점수가 실제 동작을 대표하지 않는다.
from prova.s3_grounder.dom_locator import VLM_HINTS  # noqa: E402


@dataclass(frozen=True)
class Target:
    """한 화면에서 물어볼 것 하나.

    Attributes:
        name: 기획서에 적힌 라벨. 모델에게 이 말로 묻는다.
        kind: 요소 종류 (VLM_HINTS 의 키).
        selector: **정답을 재는 손으로 쓴 selector.** present=True 면 1개로,
            False 면 0개로 풀려야 한다.
        present: 화면에 있는가. False 면 '없다고 말하는지' 를 재는 항목이다.
    """

    name: str
    kind: str
    selector: str
    present: bool = True


@dataclass(frozen=True)
class State:
    """한 장의 화면과 그 화면에서 물어볼 것들.

    Attributes:
        state_id: 데이터셋 안의 이름. 파일 이름에도 쓴다.
        path: SUT 경로 (쿼리스트링 포함 가능).
        note: 사람이 읽는 설명. 보고서 표에 그대로 들어간다.
        fill: 스크린샷 전에 채울 (selector, 값). 값이 든 화면을 만든다.
        click: 채운 뒤 누를 selector. 에러·완료 화면을 만든다.
        targets: 물어볼 것들.
    """

    state_id: str
    path: str
    note: str
    targets: tuple[Target, ...]
    fill: tuple[tuple[str, str], ...] = ()
    click: str | None = None
    warnings: list[str] = field(default_factory=list, compare=False)


# ---------------------------------------------------------------------------
# 정답표 — 구현을 보고 손으로 적었다
# ---------------------------------------------------------------------------
#
# 변형 선택 기준: **모델은 픽셀만 본다.** hashed(id 가 해시)·native(required 속성)·
# spa(라우팅) 는 화면이 good 과 똑같이 그려지므로 넣어도 같은 그림이 한 장 더 생길
# 뿐이다. 그림이 실제로 다른 것만 넣는다 — nolabel(아이콘 버튼)과 화면 상태들.

LOGIN = (
    Target("이메일", "input", "input[name=email]"),
    Target("비밀번호", "input", "input[name=password]"),
    Target("로그인", "button", "button[type=submit]"),
)

SIGNUP = (
    Target("이메일", "input", "input#email"),
    Target("비밀번호", "input", "input#password"),
    Target("비밀번호 확인", "input", "input#password_confirm"),
    Target("닉네임", "input", "input#nickname"),
    Target("가입 경로", "select", "select#signup_path"),
    Target("약관 동의", "checkbox", "input#agree_terms"),
    Target("가입하기", "button", "button[type=submit]"),
)

# 기획서 §2 는 '로그인하러 가기' 를 회원가입 화면의 요소로 적었지만, 구현에서 그것은
# 가입 완료 화면에 있다(제출 뒤에만 나타난다). 정답표를 기획서가 아니라 **구현**에 맞춘다
# — 데이터셋이 재는 것은 '화면에 그려진 것을 찾는가' 이고, 기획서와 구현의 차이는
# 파이프라인이 판정할 몫이다. 그래서 회원가입 화면에서는 '없는 것' 으로 넣는다.
WELCOME_LINK = (Target("로그인하러 가기", "link", "a.go"),)
NO_LOGIN_LINK = (Target("로그인하러 가기", "link", "a.go", present=False),)
NO_SIGNUP_BUTTON = (Target("가입하기", "button", "button[type=submit]", present=False),)

SEARCH_FORM = (
    Target("검색어", "input", "input[name=query]"),
    Target("검색", "button", "button[type=submit]"),
)

RESULT_LIST = (Target("검색 결과 목록", "list", "ul.results"),)

FIND_ACCOUNT = (
    Target("이메일", "input", "input#email"),
    Target("재설정 메일 받기", "button", "button[type=submit]"),
)

#: 화면에 없는 것을 묻는 항목. selector 가 0개로 풀리는지 확인한 뒤 넣는다.
NO_LIST = (Target("검색 결과 목록", "list", "ul.results", present=False),)
NO_PASSWORD = (Target("비밀번호", "input", "input[name=password]", present=False),)
NO_QUERY = (Target("검색어", "input", "input[name=query]", present=False),)
NO_AGREE = (Target("약관 동의", "checkbox", "input#agree_terms", present=False),)

# 범위: login·signup·search·find_account 의 4화면이다. product·orders(2026-08-20
# 추가)는 시험지를 굳힌 08-18 이후에 생겨 없다 — 다시 채점할 때 더한다. 더하면
# dataset_id 가 바뀌므로 이전 점수와 비교하지 않는다(README 참고).
STATES: tuple[State, ...] = (
    State("login-empty", "/good/login", "로그인 · 첫 진입",
          LOGIN + NO_QUERY + NO_AGREE),
    State("login-filled", "/good/login", "로그인 · 값이 채워진 상태",
          LOGIN,
          fill=(("input[name=email]", "user@test.com"),
                ("input[name=password]", "Aa1!aaaa"))),
    State("login-error", "/good/login", "로그인 · 에러 문구가 떠서 아래가 밀린 상태",
          LOGIN,
          fill=(("input[name=email]", "wrong"),
                ("input[name=password]", "Aa1!aaaa")),
          click="button[type=submit]"),
    State("signup-empty", "/good/signup", "회원가입 · 첫 진입",
          SIGNUP + NO_LOGIN_LINK),
    State("signup-error", "/good/signup", "회원가입 · 필수 입력 에러 상태",
          SIGNUP, click="button[type=submit]"),
    State("signup-welcome", "/good/welcome", "가입 완료 · 링크 하나만 있는 화면",
          WELCOME_LINK + NO_SIGNUP_BUTTON + NO_PASSWORD),
    State("search-empty", "/good/search", "검색 · 첫 진입",
          SEARCH_FORM + NO_LIST + NO_PASSWORD),
    State("search-results", "/good/search?query=Notebook", "검색 · 결과 3건",
          SEARCH_FORM + RESULT_LIST),
    State("search-none", "/good/search?query=없는상품", "검색 · 결과 0건 안내",
          SEARCH_FORM + NO_LIST),
    State("nolabel-empty", "/nolabel/search", "검색 · 아이콘만 있는 버튼 (첫 진입)",
          SEARCH_FORM + NO_LIST),
    State("nolabel-results", "/nolabel/search?query=Notebook",
          "검색 · 아이콘 버튼 + 결과 3건", SEARCH_FORM + RESULT_LIST),
    State("find-empty", "/good/find-account", "비밀번호 찾기 · 첫 진입",
          FIND_ACCOUNT + NO_PASSWORD),
    State("find-sent", "/good/find-account", "비밀번호 찾기 · 전송 완료 안내",
          FIND_ACCOUNT,
          fill=(("input#email", "user@test.com"),),
          click="button[type=submit]"),
)


def normalize(box: dict, size: dict) -> tuple[float, float, float, float]:
    """Playwright 의 픽셀 상자를 0~1 상대값으로. Located.bbox 와 같은 규약이다."""
    w, h = size["width"], size["height"]
    return (box["x"] / w, box["y"] / h,
            (box["x"] + box["width"]) / w, (box["y"] + box["height"]) / h)


def capture(page, state: State, sut: str, out_dir: Path) -> list[dict]:
    """한 화면을 만들고 정답 상자를 재서 항목들을 돌려준다.

    정답을 못 재면 예외를 던진다. 조용히 건너뛰면 데이터셋이 작아진 사실이 보이지
    않고, 어려운 항목만 빠진 시험지가 만들어진다.
    """
    page.goto(f"{sut}{state.path}")
    page.wait_for_load_state("networkidle")
    for selector, value in state.fill:
        page.fill(selector, value)
    if state.click:
        page.click(state.click)
        page.wait_for_load_state("networkidle")

    image = out_dir / f"{state.state_id}.png"
    image.write_bytes(page.screenshot())

    rows = []
    for t in state.targets:
        found = page.locator(t.selector)
        count = found.count()
        if not t.present:
            if count:
                raise AssertionError(
                    f"[{state.state_id}] '{t.name}' 은 없어야 하는데 {count}개 있습니다 "
                    f"({t.selector}). 정답표가 구현과 맞지 않습니다.")
            rows.append({"state_id": state.state_id, "note": state.note,
                         "path": state.path, "image": image.name,
                         "target": t.name, "kind": t.kind,
                         "hint": VLM_HINTS.get(t.kind, ""),
                         "present": False, "truth": None, "selector": t.selector})
            continue

        if count != 1:
            raise AssertionError(
                f"[{state.state_id}] '{t.name}' selector 가 {count}개로 풀립니다 "
                f"({t.selector}). 정답이 하나로 정해지지 않으면 채점할 수 없습니다.")
        box = found.bounding_box()
        if not box or box["width"] <= 0 or box["height"] <= 0:
            raise AssertionError(
                f"[{state.state_id}] '{t.name}' 의 상자를 잴 수 없습니다 "
                f"({t.selector}) — 화면에 보이지 않는 요소입니다.")
        rows.append({"state_id": state.state_id, "note": state.note,
                     "path": state.path, "image": image.name,
                     "target": t.name, "kind": t.kind,
                     "hint": VLM_HINTS.get(t.kind, ""),
                     "present": True,
                     "truth": list(normalize(box, VIEWPORT)),
                     "truth_px": [box["x"], box["y"], box["width"], box["height"]],
                     "selector": t.selector})
    return rows


def dataset_id(rows: list[dict]) -> str:
    """항목 내용의 해시. 점수가 어느 시험지의 것인지 나중에 확인할 수 있게 한다.

    이미지는 해시에 넣지 않는다 — PNG 는 브라우저 버전에 따라 바이트가 달라지는데
    정답 좌표가 같으면 같은 시험지로 봐도 된다. 좌표까지 달라지면 해시가 바뀐다.
    """
    payload = [(r["state_id"], r["target"], r["present"], r["truth"]) for r in rows]
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sut", default="http://localhost:8100")
    ap.add_argument("--out", default="fixtures/iou")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    rows: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT)
        try:
            for state in STATES:
                got = capture(page, state, args.sut, out_dir)
                present = sum(1 for r in got if r["present"])
                print(f"  {state.state_id:<18} {state.note:<34} "
                      f"있음 {present}개 · 없음 {len(got) - present}개")
                rows.extend(got)
        finally:
            browser.close()

    for i, r in enumerate(rows):
        r["id"] = i

    payload = {"dataset_id": dataset_id(rows), "viewport": VIEWPORT,
               "count": len(rows),
               "present": sum(1 for r in rows if r["present"]),
               "absent": sum(1 for r in rows if not r["present"]),
               "items": rows}
    path = out_dir / "dataset.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8")

    print()
    print(f"화면 {len(STATES)}장 · 항목 {payload['count']}개 "
          f"(있음 {payload['present']} · 없음 {payload['absent']})")
    print(f"dataset_id={payload['dataset_id']}  ->  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
