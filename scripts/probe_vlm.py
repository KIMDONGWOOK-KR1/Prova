"""실물 VL 모델이 아이콘 버튼을 찾는지 측정한다.

## 왜 이 스크립트가 따로 필요한가

지금까지의 2차 경로 초록불은 MockVLM 이 낸 것이다. MockVLM 은 CSS selector 로 정답을
실측한다 — '완벽한 VLM' 시뮬레이션이다. 그래서 증명된 것은 **배관**이고 정확도는 아직
아무것도 측정되지 않았다.

파이프라인으로 재면 판정(PASS/FAIL)만 보이고 **좌표가 얼마나 어긋났는지**는 보이지 않는다.
그런데 그 값이 이 경로의 실용성을 정한다 — 중심이 버튼 안에 들어오기만 하면 되므로,
버튼 크기 대비 오차가 기준이다.

그래서 판정 없이 좌표만 비교한다.

    실측(Playwright bounding_box)  vs  모델이 낸 bbox

## 측정 항목

    적중       모델 bbox 의 중심이 실제 버튼 안에 들어오는가 (이것이 실제 성패)
    IoU        두 상자의 겹침 정도 (참고 — 낮아도 중심이 맞으면 클릭은 된다)
    중심 오차  버튼 크기 대비 몇 %인가
    신뢰도     MIN_CONFIDENCE(0.5) 관문을 통과하는가

## 대상

`/nolabel/search` 의 제출 버튼. 아이콘만 있고 aria-label 도 없어서 S3 의 네 전략이 모두
막히는 화면이다. 비교를 위해 `/good/search`(글자가 있는 버튼)도 함께 재서, 실패했을 때
'이 모델이 원래 못 한다' 와 '아이콘이라서 못 한다' 를 가른다.
"""

from __future__ import annotations

import argparse
import sys

VIEWPORT = {"width": 1280, "height": 800}

# (경로, selector, 기획서에 적힌 이름, 설명)
TARGETS = [
    ("/nolabel/search", "button[type=submit]", "검색", "아이콘만 있는 제출 버튼"),
    ("/good/search", "button[type=submit]", "검색", "글자가 있는 제출 버튼 (대조군)"),
    ("/good/login", "button[type=submit]", "로그인", "글자가 있는 버튼 (대조군)"),
    ("/good/login", "input#email", "이메일", "라벨이 있는 입력란 (대조군)"),
]


def iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / (area_a + area_b - inter)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sut", default="http://localhost:8100")
    ap.add_argument("--variant-base", default="", help="사용하지 않음 (경로에 포함)")
    ap.add_argument("--vlm", default="http://localhost:8001/v1")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    from prova.models import UIElement
    from prova.s3_grounder.dom_locator import MIN_CONFIDENCE, VLM_HINTS
    from prova.vlm.base import VLMError
    from prova.vlm.qwen_vl import QwenVLClient

    vlm = QwenVLClient(base_url=args.vlm, model="qwen-vl")
    # health() 는 실패 시 예외를 던진다 (반환값 없음). 조용히 넘어가면 '모델이 못 찾았다'
    # 와 '서버가 없다' 가 구분되지 않으므로 여기서 끊는다.
    try:
        vlm.health()
    except VLMError as exc:
        print(f"VL 서버에 닿지 않습니다: {exc}")
        return 2

    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT)
        w, h = VIEWPORT["width"], VIEWPORT["height"]

        for path, selector, name, note in TARGETS:
            page.goto(f"{args.sut}{path}")
            page.wait_for_load_state("networkidle")
            box = page.locator(selector).bounding_box()
            truth = (box["x"] / w, box["y"] / h,
                     (box["x"] + box["width"]) / w, (box["y"] + box["height"]) / h)

            hint = "input" if selector.startswith("input#") else "button"
            try:
                found = vlm.locate(image_png=page.screenshot(), target=name,
                                   hint=VLM_HINTS.get(hint, ""))
            except VLMError as exc:
                rows.append((path, name, note, None, None, str(exc)[:60]))
                continue

            cx, cy = found.center
            px, py = cx * w, cy * h
            inside = (box["x"] <= px <= box["x"] + box["width"]
                      and box["y"] <= py <= box["y"] + box["height"])
            # 중심 오차를 버튼 크기로 나눈다 — 절대 픽셀은 요소 크기에 따라 뜻이 달라진다
            tcx = box["x"] + box["width"] / 2
            tcy = box["y"] + box["height"] / 2
            err = max(abs(px - tcx) / box["width"], abs(py - tcy) / box["height"])
            rows.append((path, name, note, found, truth,
                         {"적중": inside, "IoU": iou(found.bbox, truth),
                          "중심오차": err, "정상": found.is_sane(),
                          "관문통과": found.confidence >= MIN_CONFIDENCE}))
        browser.close()

    print()
    print(f"{'화면':<18}{'요소':<8}{'적중':<6}{'IoU':<7}{'중심오차':<9}{'신뢰도':<7}관문")
    print("-" * 72)
    hits = total = 0
    for path, name, note, found, truth, m in rows:
        if found is None:
            print(f"{path:<18}{name:<8}{'실패':<6}{'-':<7}{'-':<9}{'-':<7}{m}")
            total += 1
            continue
        total += 1
        hits += bool(m["적중"])
        gate = "통과" if (m["관문통과"] and m["정상"]) else "차단"
        print(f"{path:<18}{name:<8}{'O' if m['적중'] else 'X':<6}"
              f"{m['IoU']:<7.2f}{m['중심오차']:<9.2f}{found.confidence:<7.2f}{gate}")
    print("-" * 72)
    print(f"적중 {hits}/{total}")
    print()
    print("중심오차는 요소 크기 대비다. 0.5 이하이면 중심이 요소 안에 들어온다.")
    print("IoU 가 낮아도 적중이면 클릭은 된다 — 크기를 못 맞추는 것과 위치를 못 맞추는")
    print("것은 다르고, 이 경로가 필요한 것은 위치뿐이다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
