"""탐지 시험지의 정답 상자를 화면 사진 위에 그려서 보여준다 (7회차 실습용).

## 왜 이게 있는가

`fixtures/iou/dataset.json` 은 화면 18장에 대해 "이 요소의 진짜 위치는 여기다" 를
숫자로 적어 둔 시험지다. 숫자만 보면 감이 안 온다 — 0.367, 0.437 이 화면 어디인지
사람은 모른다. 눈으로 봐야 "아, 저 입력란이구나" 가 된다.

VLM 이 이 상자를 얼마나 맞히는지가 노트 13 의 주제이고, 그 채점 기준(IoU·적중)이
`src/prova/vlm/metrics.py` 에 있다.

## 설치할 것이 없다

표준 라이브러리만 쓴다. 이미지를 다시 그리지 않고 **HTML 로 겹쳐 놓기** 때문이다 —
사진은 `<img>` 로 두고 그 위에 반투명한 네모를 얹는다. Pillow 로 픽셀을 칠하면
파일이 커지고 확대하면 뭉개지는데, 이 방법은 브라우저에서 자유롭게 확대된다.

## 쓰는 법

    uv run python docs/study/tools/draw_boxes.py
    uv run python docs/study/tools/draw_boxes.py --state login-empty

만들어진 HTML 을 브라우저로 열면 된다. 경로는 실행 후 화면에 나온다.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

IOU_DIR = Path("fixtures/iou")
OUT = Path("runs/study/iou-boxes.html")

# 있음/없음을 색으로 가른다. '없음' 항목은 정답 상자가 없다 — 모델이 무언가를
# 찾아내면 그게 오탐이라는 뜻이라, 시험지에 일부러 넣어 둔 것이다.
CSS = """
body { font-family: system-ui, sans-serif; margin: 24px; background: #f6f7f9; color: #111; }
h1 { font-size: 20px; }
h2 { font-size: 15px; margin: 28px 0 8px; }
.shot { position: relative; display: inline-block; border: 1px solid #ccc; background: #fff; }
.shot img { display: block; max-width: 100%; height: auto; }
.box { position: absolute; border: 2px solid #d63; background: rgba(221,102,51,.12); }
.tag { position: absolute; top: -19px; left: -2px; font-size: 11px; line-height: 1;
       background: #d63; color: #fff; padding: 3px 5px; white-space: nowrap; }
.absent { margin: 6px 0 0; font-size: 13px; color: #666; }
"""


def load_items() -> list[dict]:
    data = json.loads((IOU_DIR / "dataset.json").read_text(encoding="utf-8"))
    return data["items"]


def render(items: list[dict]) -> str:
    by_state: dict[str, list[dict]] = {}
    for it in items:
        by_state.setdefault(it["state_id"], []).append(it)

    parts = [f"<style>{CSS}</style>", "<h1>탐지 시험지 — 정답 상자</h1>"]
    for state, group in by_state.items():
        note = group[0].get("note", "")
        image = (IOU_DIR / group[0]["image"]).resolve().as_uri()
        parts.append(f"<h2>{html.escape(state)} — {html.escape(note)}</h2>")
        parts.append(f'<div class="shot"><img src="{image}">')
        for it in group:
            if not it.get("present"):
                continue
            x1, y1, x2, y2 = it["truth"]           # 0~1 상대값
            style = (f"left:{x1*100:.3f}%; top:{y1*100:.3f}%; "
                     f"width:{(x2-x1)*100:.3f}%; height:{(y2-y1)*100:.3f}%")
            label = html.escape(f'{it["target"]} ({it["kind"]})')
            parts.append(f'<div class="box" style="{style}"><span class="tag">{label}</span></div>')
        parts.append("</div>")

        absent = [it["target"] for it in group if not it.get("present")]
        if absent:
            parts.append(
                '<p class="absent">이 화면에 <b>없는</b> 것으로 시험지에 넣어 둔 항목: '
                + html.escape(", ".join(absent))
                + " — 모델이 이걸 찾았다고 하면 오탐이다.</p>"
            )
    return "\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description="정답 상자를 사진 위에 겹쳐 HTML 로 만든다")
    ap.add_argument("--state", help="한 화면만 (예: login-empty). 없으면 전부")
    args = ap.parse_args()

    items = load_items()
    if args.state:
        items = [it for it in items if it["state_id"] == args.state]
        if not items:
            states = sorted({it["state_id"] for it in load_items()})
            raise SystemExit(f"그런 화면이 없습니다: {args.state}\n있는 것: {', '.join(states)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(items), encoding="utf-8")
    shots = len({it["state_id"] for it in items})
    boxes = sum(1 for it in items if it.get("present"))
    print(f"화면 {shots}장 · 정답 상자 {boxes}개 -> {OUT}")
    print(f"브라우저로 열기:  start {OUT}")


if __name__ == "__main__":
    main()
