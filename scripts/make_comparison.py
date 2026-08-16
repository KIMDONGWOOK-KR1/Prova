"""good / bad 실행 결과를 나란히 둔 비교 이미지.

## 이 한 장이 보여주는 것

같은 기획서, 같은 입력값, 다른 구현 → 다른 결과. 프로젝트의 핵심 주장을 설명 없이
보여주는 자료다. 팀원 티칭·멘토링·중간보고에 쓴다.

## 실행이 필요 없다

`runs/real-good` 와 `runs/real-bad` 에 이미 저장된 스텝 스크린샷을 읽어 합성한다.
S4 가 매 스텝 스크린샷을 남기도록 만들어 둔 것이 여기서 쓰인다.

## 두 이미지를 같은 좌표로 크롭한다

에러 문구 길이가 달라 카드 높이가 다르다(good 은 두 줄, bad 은 한 줄). 각자 딱 맞게
자르면 두 카드가 다른 크기로 나와 나란히 놓았을 때 정렬이 어긋난다. 두 스크린샷에서 찾은
카드 영역의 **합집합**으로 잘라 좌표를 통일하면, 정렬은 맞으면서 카드 크기 차이는 그대로
보인다.

## 문구는 인자로 받는다

기본값은 로그인 화면(대문자 규칙)이라 인자 없이 실행하면 지금까지와 같은 이미지가
나온다. 다른 화면·규칙은 문구를 넘겨 쓴다 — 코드에 박아 두면 화면을 늘릴 때마다 이
스크립트를 고쳐야 한다.

사용법:
    uv run python scripts/make_comparison.py
    uv run python scripts/make_comparison.py --case require_uppercase --out runs/cmp.png

    # 회원가입 — 약관 동의(체크박스) 필수 검증
    uv run python scripts/make_comparison.py       --good-run runs/watch-1-good-agree --bad-run runs/watch-2-bad-agree       --case signup-agree_terms-required-014 --step step8.png       --sub "약관 동의를 체크하지 않고 가입을 눌렀을 때"       --bad-head "bad — 약관 동의 검증이 빠진 구현"       --bad-note "에러 없이 가입이 완료됐다 → 규칙이 강제되지 않는다"       --out runs/cmp-signup-agree.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path("C:/Windows/Fonts")

# 리포트와 같은 판정 색 (report_builder._CSS)
INK = (28, 31, 35)
MUTED = (102, 109, 117)
PASS = (26, 127, 75)
FAIL = (192, 38, 38)
PAPER = (246, 247, 249)
LINE = (222, 227, 234)

PAD = 30
GAP = 26
CARD_PAD = 22


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "malgunbd.ttf" if bold else "malgun.ttf"
    path = FONT_DIR / name
    if not path.exists():
        path = FONT_DIR / "malgun.ttf"
    if not path.exists():
        raise SystemExit(f"한글 폰트를 찾을 수 없습니다: {path}")
    return ImageFont.truetype(str(path), size)


def card_bbox(im: Image.Image) -> tuple[int, int, int, int]:
    """흰 카드와 연한 색 에러 박스가 차지하는 영역을 찾는다."""
    rgb = im.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    xs: list[int] = []
    ys: list[int] = []
    for y in range(0, h, 3):
        for x in range(0, w, 3):
            r, g, b = px[x, y]
            is_white = (r, g, b) == (255, 255, 255)
            is_tint = r > 245 and g < 240 and b < 240      # 에러 박스(#fdeaea 계열)
            if is_white or is_tint:
                xs.append(x)
                ys.append(y)
    if not xs:
        return 0, 0, w, h
    return min(xs), min(ys), max(xs), max(ys)


def union_crop(images: list[Image.Image], pad: int = 24) -> tuple[int, int, int, int]:
    boxes = [card_bbox(im) for im in images]
    w, h = images[0].size
    x0 = max(0, min(b[0] for b in boxes) - pad)
    y0 = max(0, min(b[1] for b in boxes) - pad)
    x1 = min(w, max(b[2] for b in boxes) + pad)
    y1 = min(h, max(b[3] for b in boxes) + pad)
    return x0, y0, x1, y1


def rounded(draw: ImageDraw.ImageDraw, box, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def build(
    good_shot: Path,
    bad_shot: Path,
    out: Path,
    sub: str,
    bad_head: str,
    good_note: str,
    bad_note: str,
) -> Path:
    good = Image.open(good_shot)
    bad = Image.open(bad_shot)

    box = union_crop([good, bad])
    g_img = good.crop(box)
    b_img = bad.crop(box)
    sw, sh = g_img.size

    f_title = load_font(23, bold=True)
    f_sub = load_font(14)
    f_head = load_font(16, bold=True)
    f_tag = load_font(14, bold=True)
    f_note = load_font(13)

    # 카드 하나의 크기: 헤더 + 스크린샷 + 판정줄
    head_h = 34
    foot_h = 58
    card_w = sw + CARD_PAD * 2
    card_h = head_h + sh + foot_h + CARD_PAD

    W = PAD * 2 + card_w * 2 + GAP
    top_h = 92
    H = top_h + card_h + PAD

    canvas = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(canvas)

    # 표제
    d.text((PAD, PAD - 4), "같은 기획서 · 같은 입력값 · 다른 구현", font=f_title, fill=INK)
    d.text((PAD, PAD + 30), sub, font=f_sub, fill=MUTED)

    panels = [
        (g_img, "good — 기획서를 지킨 구현", "PASS", PASS, good_note),
        (b_img, bad_head, "FAIL", FAIL, bad_note),
    ]

    for i, (shot, head, tag, color, note) in enumerate(panels):
        x = PAD + i * (card_w + GAP)
        y = top_h

        rounded(d, (x, y, x + card_w, y + card_h), 10, fill=(255, 255, 255),
                outline=LINE, width=1)
        # 판정 색 상단 띠 — 어느 쪽이 통과인지 색으로 먼저 읽히게
        d.rounded_rectangle((x, y, x + card_w, y + 4), radius=2, fill=color)

        d.text((x + CARD_PAD, y + 14), head, font=f_head, fill=INK)

        sx, sy = x + CARD_PAD, y + head_h + 6
        canvas.paste(shot, (sx, sy))
        d.rectangle((sx, sy, sx + sw - 1, sy + sh - 1), outline=LINE, width=1)

        ty = sy + sh + 12
        tw = d.textlength(tag, font=f_tag)
        rounded(d, (x + CARD_PAD, ty, x + CARD_PAD + tw + 18, ty + 24), 12, fill=color)
        d.text((x + CARD_PAD + 9, ty + 3), tag, font=f_tag, fill=(255, 255, 255))
        d.text((x + CARD_PAD + tw + 28, ty + 4), note, font=f_note, fill=MUTED)

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, optimize=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="good/bad 비교 이미지 생성")
    ap.add_argument("--case", default="login-password-require_uppercase-006")
    ap.add_argument("--step", default="step4.png")
    ap.add_argument("--good-run", type=Path, default=Path("runs/real-good"))
    ap.add_argument("--bad-run", type=Path, default=Path("runs/real-bad"))
    ap.add_argument("--out", type=Path, default=Path("runs/comparison.png"))
    # 문구 기본값은 로그인 화면(대문자 규칙)이다. 인자 없이 실행하면 지금까지와
    # 같은 이미지가 나오고, 다른 화면·규칙은 문구를 넘겨 쓴다. 문구를 코드에 박아
    # 두면 화면을 늘릴 때마다 이 스크립트를 고쳐야 한다.
    ap.add_argument("--sub",
                    default="비밀번호에 a1!aaaaa 을 넣었을 때 — 대문자 포함 규칙만 어긴 값이다")
    ap.add_argument("--bad-head", default="bad — 대문자 검증이 빠진 구현")
    ap.add_argument("--good-note", default="기획서가 지정한 에러 문구가 그대로 노출됐다")
    ap.add_argument("--bad-note",
                    default="기획서와 다른 문구가 노출됐다 → 규칙이 강제되지 않는다")
    args = ap.parse_args()

    good_shot = args.good_run / args.case / args.step
    bad_shot = args.bad_run / args.case / args.step
    for p in (good_shot, bad_shot):
        if not p.exists():
            raise SystemExit(
                f"스크린샷이 없습니다: {p}\n"
                f"  먼저 실행하세요: uv run prova run --pdf fixtures/specs/login_spec.pdf "
                f"--url http://localhost:8100/{'good' if 'good' in str(p) else 'bad'} "
                f"--run-id {p.parts[1]}"
            )

    out = build(good_shot, bad_shot, args.out, args.sub, args.bad_head,
                args.good_note, args.bad_note)
    print(f"  {out}  ({out.stat().st_size / 1024:,.0f} KB, {Image.open(out).size})")


if __name__ == "__main__":
    main()
