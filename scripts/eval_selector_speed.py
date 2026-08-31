"""같은 시험지를 1차 경로(selector)로 채점한다 — 명세서 §9 의 비교 측정.

    uv run python scripts/eval_selector_speed.py
    uv run python scripts/eval_selector_speed.py --sut http://localhost:8100 --md

## 무엇을 재는가

명세서 §9 는 "selector 방식 vs VLM 방식의 **탐지 성공률·처리 속도**를 별도 비교
측정(하이브리드 근거)" 을 요구한다. VLM 쪽은 2026-08-22 에 쟀고 결과가
`fixtures/iou/…json` 에 좌표·신뢰도·호출 시간까지 저장돼 있다. 남은 절반이 이것이다.

    탐지 성공률   있는 요소를 찾은 비율
    오탐률        없는 요소를 '찾았다' 고 한 비율
    호출 시간     한 요소를 찾는 데 걸린 시간

## 왜 같은 시험지여야 하는가

다른 화면·다른 목록으로 잰 두 숫자를 나란히 놓으면 비교가 아니라 착시다. 시험지
50개는 화면·목표 라벨·정답 상자가 굳어 있고 VLM 이 이미 그 위에서 채점됐다. 같은
항목을 라이브 화면에서 1차 경로로 재면 사과 대 사과가 된다.

## 상태마다 페이지를 한 번만 연다

페이지 로드는 탐지가 아니다. 같은 `state_id` 의 항목들은 한 번 연 페이지 위에서
연달아 재고, 로드 시간은 탐지 시간에 섞지 않는다. 섞으면 1차 경로가 실제보다
느리게 나오고, 그 방향으로 틀린 숫자는 하이브리드 근거를 뒤집는다.

## 채점과 브라우저를 나눈 이유

`evaluate_selector` 는 `locate` 를 받아서 부르기만 한다. 브라우저가 없어도 집계를
테스트할 수 있고, 특히 **일부러 틀리는 가짜**로 오탐 집계가 실제로 올라가는지
확인할 수 있다(`tests/test_iou_dataset.py`). 좋은 소식만 낼 수 있는 지표는 없는
것보다 나쁘다 — 1차 경로는 오탐이 0 으로 나오기 쉬운 쪽이라 더 그렇다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Callable, Optional

# 로그인 절차를 `build_iou_dataset` 에서 가져온다 — 파일 위치로 불려도 찾도록.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_iou_dataset as builder  # noqa: E402 — 위 sys.path 뒤여야 한다
from build_iou_dataset import check_same_dataset  # noqa: E402,F401

DATASET = Path("fixtures/iou/dataset.json")

#: 2차 경로가 좌표로 **조작하는** 종류. 정체 대조 재생(2026-08-25)이 쓴 범위다.
#:
#: IoU 채점(2026-08-22)은 이 제외 없이 50개 전부를 쟀다. 두 범위를 헷갈려
#: 1차 경로만 43개로 재고 VLM 의 50개 숫자와 나란히 놓을 뻔했다(2026-08-27).
#: 그래서 기본값은 '전부' 이고, 좁히려면 --actionable-only 로 명시해야 하며,
#: 어느 쪽이든 VLM 요약을 같은 항목으로 다시 센다.
ACTIONABLE_KINDS = ("input", "button", "link", "checkbox")


def evaluate_selector(
    items: list[dict],
    locate: Callable[[dict], tuple[bool, Optional[str]]],
) -> list[dict]:
    """항목마다 `locate` 를 시간을 재며 부른다.

    `locate` 는 (찾았는가, 전략이름) 을 돌려준다. 예외는 삼키지 않고 행에
    남긴다 — '못 찾았다' 와 '재는 중에 터졌다' 를 섞으면 도구가 고장 난 것을
    탐지 실패로 보고하게 된다.
    """
    rows: list[dict] = []
    for item in items:
        started = time.perf_counter()
        found, strategy, error = False, None, ""
        try:
            found, strategy = locate(item)
        except Exception as exc:  # noqa: BLE001 — 무엇이 터졌든 행에 남긴다
            error = f"{type(exc).__name__}: {exc}"
        rows.append({
            "id": item.get("id"),
            "state_id": item.get("state_id"),
            "target": item.get("target"),
            "kind": item.get("kind"),
            "present": bool(item.get("present")),
            "found": bool(found) and not error,
            "strategy": strategy,
            "error": error,
            "elapsed_ms": (time.perf_counter() - started) * 1000,
        })
    return rows


def summarize_selector(rows: list[dict]) -> dict:
    """VLM 쪽 summarize 와 같은 이름의 칸을 쓴다 — 표에서 나란히 놓기 위해서다."""
    present = [r for r in rows if r["present"]]
    absent = [r for r in rows if not r["present"]]
    times = [r["elapsed_ms"] for r in rows]
    return {
        "present": len(present),
        "absent": len(absent),
        "found": sum(1 for r in present if r["found"]),
        "false_positive": sum(1 for r in absent if r["found"]),
        "call_failed": sum(1 for r in rows if r["error"]),
        "mean_ms": sum(times) / len(times) if times else 0.0,
        "max_ms": max(times) if times else 0.0,
    }


def rate(n: int, total: int) -> str:
    return f"{n}/{total} = {100 * n / total:.1f}%" if total else "0/0"


def is_actionable(item: dict) -> bool:
    return item.get("kind") in ACTIONABLE_KINDS


def check_same_population(rows_a: list[dict], rows_b: list[dict]) -> None:
    """두 채점 결과가 같은 항목을 잰 것인지 확인한다.

    모집단이 다른 두 수치를 나란히 놓으면 비교가 아니라 착시이고, 그 어긋남은
    표에서 보이지 않는다. 여기서 멈춘다 — 조용히 넘어가면 보고서에 실린다.
    """
    a, b = {r["id"] for r in rows_a}, {r["id"] for r in rows_b}
    if a != b:
        raise ValueError(
            f"두 측정의 모집단이 다릅니다 — 한쪽에만 있는 항목 "
            f"{sorted(a ^ b)} (1차 {len(a)}개 · 2차 {len(b)}개)"
        )


def summarize_vlm(rows: list[dict], keep_ids: set | None = None) -> dict:
    """저장된 VLM 채점 행을 1차 경로와 같은 칸으로 다시 센다.

    저장 문서의 요약을 그대로 옮겨 적지 않는 이유: 비교 대상이 부분집합이면
    그 숫자는 다른 모집단의 것이다. 항상 행에서 다시 센다.

    '찾았다' 의 정의는 **적중(hit) + 관문 통과(gate)** 다. IoU 가 아니라 적중을
    쓰는 이유는 1차 경로에 IoU 라는 개념이 없기 때문이다 — 두 경로가 함께
    답할 수 있는 질문은 '그 요소를 실제로 집었는가' 뿐이다.
    """
    kept = [r for r in rows if keep_ids is None or r["id"] in keep_ids]
    present = [r for r in kept if r["present"]]
    absent = [r for r in kept if not r["present"]]
    times = [r["elapsed_ms"] for r in kept]
    return {
        "present": len(present),
        "absent": len(absent),
        "found": sum(1 for r in present if r.get("hit") and r.get("gate")),
        "false_positive": sum(1 for r in absent if r.get("gate")),
        "call_failed": sum(1 for r in kept if r.get("error")),
        "mean_ms": sum(times) / len(times) if times else 0.0,
        "max_ms": max(times) if times else 0.0,
    }


# ---------------------------------------------------------------------------
# 라이브 화면에서 재기 — 여기부터는 브라우저가 필요하다
# ---------------------------------------------------------------------------


def make_page_locator(page, sut: str):
    """1차 경로를 그대로 부르는 locate 를 만든다.

    파이프라인이 쓰는 `ground()` 를 그대로 부른다 — 이 측정이 재려는 것은
    '측정용으로 다시 짠 탐지' 가 아니라 실제로 도는 그 경로다.
    """
    from prova.models import UIElement
    from prova.s3_grounder.dom_locator import GroundingError, ground

    current = {"path": None}

    def sign_in(path: str) -> None:
        """로그인 뒤 화면은 세션부터 만든다.

        안 하면 화면이 통째로 로그인으로 리다이렉트되고, 거기 있는 '비밀번호' 를
        '없는 요소를 찾았다'(오탐)로 집계한다 — **도구 결함이 탐지 실패로
        둔갑한다.** 실제로 겪었다(2026-08-27, 시험지를 넓힌 직후).

        절차와 계정은 `build_iou_dataset` 가 갖는다 — 여기 다시 적으면 시험지를
        만든 화면과 채점하는 화면이 갈라진다. `wait="load"` 로 부르는 이유는 그쪽
        docstring 에 있다(이 구간이 아직 타이머 안이다).
        """
        builder.sign_in(page, sut, path, wait="load")

    def locate(item: dict) -> tuple[bool, Optional[str]]:
        # 같은 화면의 항목이 이어지면 다시 열지 않는다 — 로드 시간을 탐지
        # 시간에 섞지 않기 위해서다.
        if current["path"] != item["path"]:
            if item.get("login"):
                sign_in(item["path"])
            page.goto(f"{sut}{item['path']}", wait_until="load")
            current["path"] = item["path"]
        hint = UIElement(element_id=f"probe-{item['id']}", type=item["kind"],
                         label=item["target"])
        try:
            location = ground(page, item["target"], hint)
        except GroundingError:
            return False, None
        return True, location.strategy

    return locate


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sut", default="http://localhost:8100")
    ap.add_argument("--dataset", default=str(DATASET))
    # 기본값은 **지금 시험지의** 채점 결과여야 한다. 옛 결과를 가리켜 두면
    # dataset_id 가드가 매번 비교를 거절하고, 거절이 일상이 되면 그 가드가
    # 실제로 어긋남을 잡은 날에도 읽히지 않는다 (2026-08-28 에 옮겼다).
    ap.add_argument("--vlm-result", default="docs/measurements/vlm-iou-qwen-vl-2026-08-31.json",
                    help="저장된 2차 경로 채점 결과 — 같은 항목으로 다시 세어 나란히 놓는다")
    ap.add_argument("--actionable-only", action="store_true",
                    help="좌표로 조작하는 종류(input·button·link·checkbox)만 — "
                         "정체 대조 재생(08-25)과 같은 범위")
    ap.add_argument("--md", action="store_true", help="측정 문서용 표를 낸다")
    args = ap.parse_args()

    data = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    items = [i for i in data["items"]
             if not args.actionable_only or is_actionable(i)]
    if not items:
        print("잴 항목이 없습니다.")
        return 1

    # 시험지가 지금 이 앱의 화면인지 먼저 본다. 브라우저를 연 뒤에 멈추면
    # 기다린 시간이 버려지고, 무엇보다 '연 김에 그냥 재자' 는 유혹이 생긴다.
    try:
        builder.require_matching_sut(data, lambda: builder.sut_stamp(args.sut))
    except ValueError as exc:
        print(f"\n{exc}")
        return 2

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=data["viewport"])
        rows = evaluate_selector(items, make_page_locator(page, args.sut))
        browser.close()

    for r in rows:
        mark = "찾음" if r["found"] else ("오류" if r["error"] else "못찾음")
        expect = "있음" if r["present"] else "없음"
        print(f"  [{expect}] {r['state_id']:<16} {r['target']:<10} "
              f"{mark:<5} {r['strategy'] or '-':<16} {r['elapsed_ms']:>6.1f}ms"
              + (f"  {r['error']}" if r["error"] else ""))

    s = summarize_selector(rows)
    print()
    print(f"  항목        있음 {s['present']} · 없음 {s['absent']}"
          + ("  (좌표 조작 종류만)" if args.actionable_only else "  (시험지 전체)"))
    print(f"  탐지 성공률 {rate(s['found'], s['present'])}")
    print(f"  오탐률      {rate(s['false_positive'], s['absent'])}")
    print(f"  호출 시간   평균 {s['mean_ms']:.1f}ms · 최대 {s['max_ms']:.1f}ms")
    if s["call_failed"]:
        print(f"  오류        {s['call_failed']}건 — 탐지 실패와 섞지 않았다")

    vlm_path = Path(args.vlm_result)
    if not vlm_path.exists():
        print(f"\n  2차 경로 결과가 없어 비교표를 만들지 않았습니다: {vlm_path}")
        return 0

    saved = json.loads(vlm_path.read_text(encoding="utf-8"))
    keep = {r["id"] for r in rows}
    try:
        # 같은 시험지의 점수인지 먼저 본다 — id 집합이 같아도 시험지가 다르면
        # 같은 id 가 다른 항목을 가리킨다.
        check_same_dataset(data["dataset_id"], saved.get("meta", {}))
        # 모집단이 어긋나도 멈춘다 — 조용히 넘어가면 보고서에 실린다.
        check_same_population(rows, [r for r in saved["rows"] if r["id"] in keep])
    except ValueError as exc:
        # 표를 못 만드는 것이 이 가드의 목적이다. 1차 경로 측정 자체는 끝났으므로
        # 실패가 아니라 '비교는 못 한다' 로 알린다.
        print()
        print(f"  비교표를 만들지 않았습니다 — {exc}")
        return 0
    v = summarize_vlm(saved["rows"], keep_ids=keep)

    print()
    print("| 지표 | selector (1차) | VLM (2차) |")
    print("|---|---|---|")
    print(f"| 탐지 성공률 | {rate(s['found'], s['present'])} "
          f"| {rate(v['found'], v['present'])} |")
    print(f"| 오탐 (없는 것을 찾았다고) | {rate(s['false_positive'], s['absent'])} "
          f"| {rate(v['false_positive'], v['absent'])} |")
    print(f"| 호출 시간 (평균) | {s['mean_ms']:.1f}ms | {v['mean_ms']:.0f}ms |")
    print(f"| 호출 시간 (최대) | {s['max_ms']:.1f}ms | {v['max_ms']:.0f}ms |")
    if v["mean_ms"] and s["mean_ms"]:
        print(f"| 평균 배수 | 1× | **{v['mean_ms'] / s['mean_ms']:.0f}×** |")
    if args.md:
        print(f"\n항목 {len(rows)}개 (있음 {s['present']} · 없음 {s['absent']}) · "
              f"2차 경로 채점 결과: {vlm_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
