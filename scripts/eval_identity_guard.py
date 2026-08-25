"""정체 대조 관문의 효과 측정 — 저장된 VL 답안을 라이브 화면에 재생한다.

2026-08-22 실측(docs/measurements/vlm-iou-qwen-vl-2026-08-22.json)에서 VL 이
낸 좌표·신뢰도가 전부 저장돼 있다. 모델을 다시 부르지 않고 그 좌표를 같은
화면(시험지 상태를 그대로 재현)에 재생해, 2026-08-25 에 넣은 정체 대조
(`_require_actionable`)가 무엇을 걸러내는지 잰다.

재는 것 둘:
    1. 오탐(없는 요소를 찾았다고 한 7건) 중 관문이 막는 수  ← 커야 한다
    2. 정상 보정(있는 요소, 관문 통과) 중 잘못 막는 수      ← 0 이어야 한다
       (관문이 새 오탐을 만들면 안 된다)

사용법:
    uv run uvicorn sut.app:app --port 8100   # 별 터미널
    uv run python scripts/eval_identity_guard.py http://localhost:8100

원본 답안을 재생하므로 VL 서버가 필요 없다. 요약 표만 저장소에 남기고
(docs/measurements/), 원본 출력은 스크래치패드 원칙을 따른다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_iou_dataset import STATES, VIEWPORT  # noqa: E402
from prova.models import ScreenSpec, TestStep  # noqa: E402
from prova.s3_grounder.dom_locator import ElementLocation, GroundingError  # noqa: E402
from prova.s4_executor.playwright_driver import (  # noqa: E402
    ExecutionContext,
    _require_actionable,
)

MEASUREMENT = Path("docs/measurements/vlm-iou-qwen-vl-2026-08-22.json")

#: 시험지 화면 -> 그 화면의 골든 스펙. 정체 대조가 아는 라벨은 파이프라인과
#: 같게 '그 케이스의 화면' 것만 쓴다.
GOLDEN_BY_PREFIX = {
    "login": "fixtures/specs/login_spec.golden.json",
    "signup": "fixtures/specs/signup_spec.golden.json",
    "search": "fixtures/specs/search_spec.golden.json",
    "nolabel": "fixtures/specs/search_spec.golden.json",
    "find": "fixtures/specs/find_account_spec.golden.json",
}

#: 항목 종류 -> 그 요소를 조작할 때의 액션 (_ACTIONABLE 의 키와 맞춘다).
#: select 는 좌표로 조작할 수 없어 2차 경로가 지원하지 않고(playwright_driver
#: 의 vlm-unsupported), list 는 조작 대상이 아니라 세는 대상이다 — 둘 다
#: 재생에서 뺀다. 넣으면 파이프라인에서 일어나지 않는 조합을 잰 숫자가 된다.
ACTION_BY_KIND = {
    "input": "fill",
    "button": "click",
    "link": "click",
    "checkbox": "check",
}


def spec_for(state_id: str) -> ScreenSpec:
    prefix = state_id.split("-")[0]
    raw = json.loads(Path(GOLDEN_BY_PREFIX[prefix]).read_text(encoding="utf-8"))
    return ScreenSpec.model_validate(raw)


def replay(page, sut: str, tmp_dir: Path, rows: list[dict]) -> list[dict]:
    states = {s.state_id: s for s in STATES}
    out = []
    for row in rows:
        state = states[row["state_id"]]
        page.goto(f"{sut}{state.path}")
        page.wait_for_load_state("networkidle")
        for selector, value in state.fill:
            page.fill(selector, value)
        if state.click:
            page.click(state.click)
            page.wait_for_load_state("networkidle")

        x1, y1, x2, y2 = row["bbox"]
        x = (x1 + x2) / 2 * VIEWPORT["width"]
        y = (y1 + y2) / 2 * VIEWPORT["height"]
        ctx = ExecutionContext(page=page, base_url=sut,
                               specs=[spec_for(row["state_id"])],
                               run_dir=tmp_dir, case_id="replay")
        step = TestStep(seq=1, action=ACTION_BY_KIND[row["kind"]],
                        target=row["target"])
        location = ElementLocation(target=row["target"], method="vlm",
                                   selector=None, bbox=[0, 0, 1, 1],
                                   confidence=row["confidence"], healed=True,
                                   strategy="vlm")
        try:
            _require_actionable(ctx, location, step, x, y)
            blocked, reason = False, ""
        except GroundingError as exc:
            blocked, reason = True, str(exc.attempts[0].strategy)
        out.append({**row, "blocked": blocked, "block_reason": reason})
    return out


def main() -> None:
    sut = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8100"
    data = json.loads(MEASUREMENT.read_text(encoding="utf-8"))
    rows = data["rows"]

    replayable = [r for r in rows if r["kind"] in ACTION_BY_KIND]
    skipped = [r for r in rows if r["kind"] not in ACTION_BY_KIND]
    false_positives = [r for r in replayable if not r["present"] and r["gate"]]
    # 빗나간 좌표(hit=False)는 따로 센다 — 기존 관문(빈 곳 차단)이 막는 것이
    # 정상이고, 그것을 '오차단' 으로 세면 관문을 억울하게 고치게 된다.
    good_heals = [r for r in replayable
                  if r["present"] and r["gate"] and r.get("hit")]
    missed_coords = [r for r in replayable
                     if r["present"] and r["gate"] and not r.get("hit")]

    from playwright.sync_api import sync_playwright
    import tempfile

    with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT)
        fp = replay(page, sut, Path(tmp), false_positives)
        ok = replay(page, sut, Path(tmp), good_heals)
        missed = replay(page, sut, Path(tmp), missed_coords)
        browser.close()

    fp_blocked = sum(1 for r in fp if r["blocked"])
    ok_blocked = sum(1 for r in ok if r["blocked"])
    missed_blocked = sum(1 for r in missed if r["blocked"])

    print(f"# 정체 대조 재생 측정 (답안: {MEASUREMENT.name}, 재호출 없음)\n")
    print(f"오탐 {len(fp)}건 중 차단: {fp_blocked}  → 남은 오탐 {len(fp) - fp_blocked}")
    print(f"정상 보정(적중) {len(ok)}건 중 오차단: {ok_blocked}  (0 이어야 한다)")
    print(f"빗나간 좌표 {len(missed)}건 중 차단: {missed_blocked}  (기존 빈곳 관문의 몫)")
    print(f"재생 제외: {len(skipped)}건 (select·list — 2차 경로 조작 대상 아님)\n")
    print("| 화면 | 없는 요소 | 신뢰도 | 결과 |")
    print("|---|---|---|---|")
    for r in fp:
        verdict = f"차단 — {r['block_reason']}" if r["blocked"] else "통과 (오탐 잔존)"
        print(f"| {r['state_id']} | {r['target']} | {r['confidence']:.2f} | {verdict} |")
    if ok_blocked:
        print("\n## 오차단 (관문이 새로 만든 오탐 — 고쳐야 한다)")
        for r in ok:
            if r["blocked"]:
                print(f"- {r['state_id']} {r['target']}: {r['block_reason']}")


if __name__ == "__main__":
    main()
