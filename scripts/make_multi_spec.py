"""통합 기획서(여러 화면이 한 문서에 든 것)를 화면별 기획서에서 조립한다.

## 왜 이 스크립트가 필요한가

`multi_spec.md` 는 로그인·회원가입·검색 기획서를 이어 붙인 문서다. 처음에는 손으로
이어 붙였는데, 그러면 **화면 기획서를 고쳤을 때 통합 문서가 조용히 낡는다.**

실제로 겪었다. 로그인 기획서에 예시 동작 절(§6)을 추가하고 PDF 만 다시 만들었더니,
통합 문서에는 그 절이 없어서 로그인 화면 케이스가 9건이 아니라 7건으로 나왔다. 관통
테스트가 숫자로 잡아 줬지만, 잡히지 않았다면 **통합 문서 쪽 검증이 조용히 두 건 줄어든
채로** 넘어갔을 것이다.

그래서 조립을 코드로 옮기고, 낡았는지를 테스트가 확인한다
(tests/test_fixture_consistency.py). 스크립트만 두면 실행을 잊는 것을 막지 못한다.

## 원본과 산출물

    fixtures/specs/_multi_front.md   표지 (문서번호·작성일)
    fixtures/specs/{화면}_spec.md    화면별 기획서 — '## 1.' 부터 가져온다
    fixtures/specs/_multi_flows.md   화면 흐름 정의 (손으로 쓴 부분)
        -> fixtures/specs/multi_spec.md

`_` 로 시작하는 파일은 조각이므로 `make_spec_pdf.py` 가 PDF 로 만들지 않는다.

화면별 기획서에서 앞머리(제목·문서번호)를 걷어내는 이유: 통합 문서는 표지를 하나만
가져야 한다. '## 1.' 은 화면 개요 절의 시작이고, 그 앞은 문서 수준 정보다.
"""

from __future__ import annotations

import sys
from pathlib import Path

SPEC_DIR = Path("fixtures/specs")

#: 조립할 문서들. 이름 -> (표지 조각, 가져올 화면 기획서, 흐름 조각).
#:
#: 화면 기획서 하나가 화면 하나라는 법은 없다 — `product_spec.md` 는 로그인과
#: 상품 등록 두 화면을 담는다. '## 1.' 부터 끝까지 가져오므로 그 안의 페이지
#: 구분도 함께 온다. 그래서 onboarding 은 조각 둘로 화면 셋이 된다.
DOCUMENTS = {
    "multi": ("_multi_front.md", ("login", "signup", "search"), "_multi_flows.md"),
    "onboarding": ("_onboarding_front.md", ("signup", "product"),
                   "_onboarding_flows.md"),
}

# 화면 경계 마커. make_spec_pdf.py 가 이걸 보고 PDF 페이지를 나눈다.
#
# 화면마다 페이지를 새로 시작해야 하는 이유: S1 은 페이지 단위로 화면을 가른다
# (pdf_parser.split_screens). 한 페이지에 두 화면이 섞이면 뒤 화면의 요소 표가 앞
# 화면 것으로 추출되어 두 화면의 검증이 모두 조용히 어긋난다.
PAGE_BREAK = "<!-- page -->"


def screen_body(stem: str) -> str:
    """화면 기획서에서 '## 1.' 부터 끝까지. 앞머리(제목·문서번호)는 뺀다."""
    lines = (SPEC_DIR / f"{stem}_spec.md").read_text(encoding="utf-8").splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith("## 1.")), None)
    if start is None:
        raise SystemExit(f"{stem}_spec.md 에 '## 1.' 절이 없습니다 — 구조가 바뀌었나요?")
    return "\n".join(lines[start:]).rstrip() + "\n"


def out_path(name: str) -> Path:
    return SPEC_DIR / f"{name}_spec.md"


def assemble(name: str = "multi") -> str:
    """통합 문서 본문을 만든다. 파일을 쓰지 않으므로 테스트에서 그대로 쓴다."""
    front, screens, flows = DOCUMENTS[name]
    parts = [(SPEC_DIR / front).read_text(encoding="utf-8").rstrip() + "\n"]
    for stem in screens:
        parts.append(screen_body(stem) + f"\n{PAGE_BREAK}\n")
    parts.append((SPEC_DIR / flows).read_text(encoding="utf-8").rstrip() + "\n")
    return "\n".join(parts)


def main() -> int:
    """--check 를 주면 아무것도 쓰지 않고 낡았는지만 알린다 (종료 코드 1).

    쓰지 않는 모드가 필요한 이유: 테스트가 이 스크립트를 그냥 실행하면 **추적 중인
    픽스처를 고쳐 버린다.** 실제로 겪었다 — 낡음 검출을 확인하려고 화면 기획서에
    임시 절을 넣고 테스트를 돌렸더니, 스크립트가 그 임시 절을 통합 문서에 박아 넣어서
    임시 절을 지운 뒤에도 어긋난 상태가 남았다.

    테스트는 부작용이 없어야 한다. 그리고 이 모드는 CI 에서도 쓸 수 있다.
    """
    check = "--check" in sys.argv[1:]
    stale = 0
    # 문서 하나가 어긋났다고 나머지를 건너뛰지 않는다 — 한 번 돌려서 전부
    # 알아야, 고치고 다시 돌리는 일을 문서 수만큼 반복하지 않는다.
    for name in DOCUMENTS:
        out = out_path(name)
        text = assemble(name)
        if out.exists() and out.read_text(encoding="utf-8") == text:
            print(f"  {out} 는 이미 최신입니다")
            continue
        if check:
            print(f"  {out} 가 화면별 기획서와 어긋났습니다 — --check 없이 다시 실행하세요")
            stale += 1
            continue
        out.write_text(text, encoding="utf-8")
        print(f"  {out} 갱신 ({len(text):,} chars) — PDF 도 다시 만드세요:")
        print(f"    uv run python scripts/make_spec_pdf.py {out}")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
