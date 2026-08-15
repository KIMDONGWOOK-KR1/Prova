"""자리표시자를 data URI 이미지로 치환해 발행용 HTML 을 만든다.

## 왜 스크립트로 하나

발행되는 웹페이지(Artifact)는 외부 파일을 불러올 수 없다 — CDN, 상대 경로 이미지 모두
차단된다. 그래서 이미지와 GIF 를 base64 data URI 로 문서 안에 넣어야 한다.

그 base64 를 HTML 에 직접 붙여넣으면 파일이 수십만 자가 되어 **다시 편집할 수 없게 된다.**
그래서 소스와 빌드를 나눈다.

    overview.src.html   사람이 편집하는 원본. <!-- MEDIA:name --> 자리표시자만 있다
    overview.html       이 스크립트가 만드는 발행용. data URI 가 들어 있다

발행은 빌드 결과(overview.html)로 하고, 내용을 고칠 때는 원본(overview.src.html)을 고친 뒤
이 스크립트를 다시 돌린다.

사용법:
    uv run python scripts/embed_media.py
"""

from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path

SRC = Path("docs/teaching/overview.src.html")
OUT = Path("docs/teaching/overview.html")

# 자료는 저장소에 함께 둔다. runs/ 는 .gitignore 대상이라 팀원이 클론하면 비어 있고,
# 그러면 이 스크립트가 실패해 페이지를 다시 만들 수 없다.
MEDIA_DIR = Path("docs/teaching/media")

# 자리표시자 이름 -> 파일 경로, alt 텍스트
MEDIA = {
    "comparison": (
        MEDIA_DIR / "comparison.png",
        "같은 기획서와 같은 입력값에 대해 good 구현은 기획서가 지정한 에러 문구를 노출해 "
        "PASS, bad 구현은 다른 문구를 노출해 FAIL 로 판정된 화면 비교",
    ),
    "demo_good": (
        MEDIA_DIR / "demo_good.gif",
        "good 구현에서 대문자 없는 비밀번호를 입력하면 기획서가 지정한 복잡도 에러가 뜨는 실행 장면",
    ),
    "demo_bad": (
        MEDIA_DIR / "demo_bad.gif",
        "bad 구현에서 같은 값을 입력하면 복잡도 검사를 건너뛰어 다른 문구가 뜨는 실행 장면",
    ),
}

PLACEHOLDER = re.compile(r"[ \t]*<!--\s*MEDIA:([a-z_]+)\s*-->")


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"소스가 없습니다: {SRC}")

    missing = [str(p) for p, _ in MEDIA.values() if not p.exists()]
    if missing:
        raise SystemExit(
            "필요한 자료가 없습니다:\n  " + "\n  ".join(missing) + "\n\n"
            "먼저 만드세요:\n"
            "  uv run python scripts/make_comparison.py\n"
            "  uv run python scripts/make_demo_gif.py runs/demo-bad-slow --out runs/demo_bad.gif"
        )

    html = SRC.read_text(encoding="utf-8")
    used: list[str] = []

    def replace(m: re.Match) -> str:
        name = m.group(1)
        if name not in MEDIA:
            raise SystemExit(f"알 수 없는 자리표시자: MEDIA:{name}")
        path, alt = MEDIA[name]
        used.append(name)
        return f'      <img src="{data_uri(path)}" alt="{alt}">'

    built = PLACEHOLDER.sub(replace, html)

    unused = set(MEDIA) - set(used)
    if unused:
        print(f"  경고: 쓰이지 않은 자료 {sorted(unused)}")

    OUT.write_text(built, encoding="utf-8")

    src_kb = len(html.encode("utf-8")) / 1024
    out_kb = len(built.encode("utf-8")) / 1024
    print(f"  {SRC}  ({src_kb:,.0f} KB)")
    print(f"  -> {OUT}  ({out_kb:,.0f} KB, 자료 {len(used)}개 삽입)")
    if out_kb > 15_000:
        print("  주의: 발행 한도(16MB)에 가깝습니다. GIF 를 줄이세요.")


if __name__ == "__main__":
    main()
