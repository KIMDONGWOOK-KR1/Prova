"""실행 영상(webm) → GIF 변환.

`prova run --video` 로 녹화한 영상을 팀원·멘토에게 보여줄 GIF 로 만든다.

## 왜 크롭하나

녹화는 960x600 이고 로그인 카드는 화면 중앙 360x320 영역만 차지한다. 전체를 그냥 줄이면
GIF 폭에 맞추느라 텍스트가 작아져 **입력값과 에러 문구를 읽을 수 없다.** 자료로서 읽히지
않으면 만든 의미가 없으므로, 카드 영역만 잘라 원본 크기를 유지한다.

## 왜 2패스인가

`ffmpeg -i in.webm out.gif` 는 GIF 의 256색 제약을 무작정 처리해 색이 뭉개지고 용량도 크다.
프레임 전체를 훑어 최적 팔레트를 먼저 만들고(palettegen) 그 팔레트로 변환하면(paletteuse)
같은 용량에서 훨씬 깨끗하다.

## 팔레트를 256색으로 두고 부분 프레임 최적화를 끄는 이유

여기서 한 번 크게 헤맸다. 색을 96개로 줄이고 ffmpeg 기본 최적화를 쓰면 GIF 용량이
작아지는데, **브라우저에서 흰 화면으로 보인다.** PIL 로 프레임을 뽑아 보면 내용이
멀쩡해서 원인을 찾기 어렵다.

원인은 두 가지가 겹친 것이다.

1. GIF 헤더의 배경색 인덱스가 255 인데 팔레트에 96색만 있어 그 인덱스가 정의되지 않는다
2. ffmpeg 가 변화 없는 프레임을 1x1 픽셀만 갱신하도록 최적화한다(offsetting)

브라우저는 프레임을 그리기 전에 정의되지 않은 배경색으로 화면을 지우고, 다음 프레임이
1픽셀만 채우므로 나머지가 흰색으로 남는다. 그래서 `max_colors=256`(배경 인덱스가 팔레트
안에 들어오게)과 `-gifflags -offsetting`(모든 프레임을 전체 크기로)을 함께 쓴다.
용량은 조금 늘지만(약 15%) 브라우저에서 확실히 재생된다.

## 마지막 프레임을 늘리는 이유

이 GIF 의 요점은 **마지막에 뜨는 에러 문구**다. 그런데 클릭 직후 영상이 끝나 문구를 읽을
시간이 없다. tpad 로 마지막 프레임을 1.8초 유지해 읽을 틈을 준다.

사용법:
    uv run python scripts/make_demo_gif.py runs/demo-bad-slow
    uv run python scripts/make_demo_gif.py runs/demo-bad-slow --out runs/demo.gif
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# 로그인 카드 영역 (960x600 녹화 기준). w:h:x:y
CROP = "360:320:300:140"
FPS = 8
HOLD_LAST_SEC = 1.8
MAX_COLORS = 256

# 녹화 시작 직후 약 0.4초는 페이지가 아직 로드되지 않아 빈 화면이다. GIF 는 무한
# 반복되므로 그 구간을 남겨 두면 루프마다 화면이 깜빡이고 "이미지가 깨졌나" 싶어진다.
SKIP_HEAD_SEC = 0.4


def find_video(run_dir: Path) -> Path:
    videos = sorted((run_dir / "video").glob("*.webm"))
    if not videos:
        raise SystemExit(
            f"{run_dir}/video 에 webm 이 없습니다.\n"
            f"  --video 옵션으로 다시 실행하세요:\n"
            f"  uv run prova run --pdf ... --url ... --only <패턴> --slow 500 --video"
        )
    return videos[-1]


def convert(video: Path, out: Path, crop: str = CROP,
            skip_head: float = SKIP_HEAD_SEC) -> Path:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg 를 찾을 수 없습니다.")

    out.parent.mkdir(parents=True, exist_ok=True)
    # 팔레트는 임시 파일로. 같은 필터 체인 안에서 split 해도 되지만, 두 명령으로 나누면
    # 실패 지점이 명확해지고 팔레트만 따로 확인할 수 있다.
    palette = out.parent / f".{out.stem}_palette.png"

    common = f"crop={crop},tpad=stop_mode=clone:stop_duration={HOLD_LAST_SEC},fps={FPS}"

    seek = ["-ss", str(skip_head)] if skip_head else []

    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *seek, "-i", str(video),
         # stats_mode=full: 프레임 전체를 보고 팔레트를 만든다. diff 모드는 움직이는
         # 영역에 색을 집중시켜 정적 배경색이 팔레트에서 빠질 수 있다.
         "-vf", f"{common},palettegen=max_colors={MAX_COLORS}:stats_mode=full",
         str(palette)],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *seek, "-i", str(video), "-i", str(palette),
         "-lavfi", f"{common}[x];[x][1:v]paletteuse=dither=sierra2_4a",
         # -offsetting 끄기: 모든 프레임을 전체 크기로 저장한다 (위 설명 참고)
         "-gifflags", "-offsetting",
         "-loop", "0", str(out)],
        check=True,
    )
    palette.unlink(missing_ok=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="실행 영상을 GIF 로 변환")
    ap.add_argument("run_dir", type=Path, help="prova run --video 의 실행 디렉터리")
    ap.add_argument("--out", type=Path, default=None, help="출력 GIF 경로")
    ap.add_argument("--crop", default=CROP, help=f"crop w:h:x:y (기본 {CROP})")
    ap.add_argument("--skip-head", type=float, default=SKIP_HEAD_SEC,
                    help=f"앞부분을 잘라낼 초 (기본 {SKIP_HEAD_SEC})")
    args = ap.parse_args()

    if not args.run_dir.exists():
        raise SystemExit(f"디렉터리가 없습니다: {args.run_dir}")

    video = find_video(args.run_dir)
    out = args.out or args.run_dir / "demo.gif"
    convert(video, out, args.crop, args.skip_head)

    kb = out.stat().st_size / 1024
    print(f"  {video.name}  ->  {out}  ({kb:,.0f} KB)")
    if kb > 1500:
        print("  주의: 1.5MB 를 넘습니다. --crop 을 좁히거나 FPS 를 낮추세요.", file=sys.stderr)


if __name__ == "__main__":
    main()
