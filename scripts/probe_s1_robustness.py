"""실물 기획서를 만나면 S1 이 어떻게 깨지는가 — 훼손 6종 측정.

## 왜 이 측정이 필요한가

픽스처 기획서 4개는 전부 우리가 마크다운으로 써서 스크립트로 PDF 로 만든 것이다.
7열이 정확한 순서로, 정확한 헤더 이름으로, 표 형태로 있다. **S1 의 결정적 표 독해
여덟 개가 전부 그 모양을 전제한다.**

그런데 실제 화면기획서는 그렇게 생기지 않을 가능성이 높다. Figma 캡처와 산문,
표가 이미지, 열 이름이 '항목/설명', 셀 병합 — 실물 문서의 흔한 모양들이다.

S1 이 깨지면 그 뒤 400여 개 테스트가 전부 무의미하다. 지금까지의 '오탐 0건' 이
"우리가 만든 문서에서는" 이라는 조건 아래 있다. 이 측정은 그 조건을 드러낸다.

## 재는 것은 '깨지는가' 가 아니라 '어떻게 깨지는가'

    조용한 실패    일부를 놓치고도 경고 없이 정상처럼 보인다     <- 가장 위험
    시끄러운 실패  경고를 남기거나 예외로 끊는다                 <- 괜찮다

앞쪽이 나오면 사람이 초록불을 믿고 넘어간다. 뒤쪽이면 사람이 문서를 고치거나 도구를
고친다. 이 도구의 가치는 후자로 만드는 데 있다.

## 훼손 6종

    1. 열 이름 변경  '요소 ID' -> '항목'                _element_table() 판별 조건
    2. 열 누락       '안내 문구' 열 제거                있는 열만 읽는지
    3. 산문 서술     요소 표를 문장으로 대체            표가 아예 없을 때
    4. 셀 병합       한 요소가 두 줄에 걸침             행 단위 짝짓기가 어긋나는지
    5. 표 이미지화   표를 못 읽는 상태                  pdfplumber 가 무시할 때
    6. 절 번호 없음  '## 2. UI 요소 정의' -> '## UI 요소 정의'  절 탐색이 번호에 의존하는지

각 훼손은 **하나만** 적용한다. 둘을 겹치면 어느 것이 원인인지 분리되지 않는다 —
negative 케이스가 규칙을 하나씩만 위반하는 것과 같은 이유다.

## LLM 을 어떻게 쓰는가

mock 을 쓰지 않는다. mock 은 PDF 를 읽지 않고 정답을 돌려주므로 훼손된 문서에서도
같은 답을 낸다 — 측정이 성립하지 않는다. 실물 7B 가 필요하다.

## 사용법

    uv run python scripts/probe_s1_robustness.py            측정하고 파일 정리
    uv run python scripts/probe_s1_robustness.py --keep      훼손된 기획서를 남긴다
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

BASE_MD = Path("fixtures/specs/login_spec.md")


# ---------------------------------------------------------------- 훼손 정의

def d_rename_header(md: str) -> str:
    """'요소 ID' -> '항목'. 실물 기획서가 우리 용어를 쓸 이유가 없다."""
    return md.replace("| 요소 ID | 유형 |", "| 항목 | 유형 |")


def d_drop_column(md: str) -> str:
    """'안내 문구' 열을 통째로 제거한다 (헤더와 각 행에서 6번째 칸)."""
    out = []
    for line in md.splitlines():
        if line.startswith("| ") and line.count("|") == 8:
            cells = line.split("|")
            # cells[0] 과 [-1] 은 빈 문자열. 데이터는 1..7, '안내 문구' 는 6번째
            del cells[6]
            out.append("|".join(cells))
        else:
            out.append(line)
    return "\n".join(out)


def d_prose(md: str) -> str:
    """UI 요소 표를 산문으로 바꾼다. 표가 아예 없는 문서."""
    prose = (
        "이 화면에는 이메일 입력란과 비밀번호 입력란, 그리고 로그인 버튼이 있습니다.\n\n"
        "이메일은 필수이며 @ 를 포함한 이메일 형식이어야 합니다. 형식이 맞지 않으면 "
        "'올바른 이메일 형식을 입력하세요.' 를 노출합니다. "
        "안내 문구는 '이메일을 입력하세요' 입니다.\n\n"
        "비밀번호는 필수이며 8자 이상, 대문자 1자 이상, 특수문자 1자 이상이어야 합니다. "
        "조건을 만족하지 않으면 '비밀번호는 8자 이상이며 대문자·특수문자를 각 1자 이상 "
        "포함해야 합니다.' 를 노출합니다. "
        "안내 문구는 '비밀번호를 입력하세요' 입니다.\n"
    )
    return _replace_element_table(md, prose)


def d_merge_cells(md: str) -> str:
    """비밀번호 행의 검증 규칙을 두 줄로 쪼갠다 (셀 병합의 텍스트 표현).

    실물 PDF 의 병합 셀은 pdfplumber 가 빈 칸으로 읽거나 앞 칸에 합쳐 읽는다.
    여기서는 '두 번째 줄의 다른 칸이 비어 있는' 모양으로 재현한다.
    """
    out = []
    for line in md.splitlines():
        if line.startswith("| password |"):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            first = list(cells)
            first[4] = "8자 이상,"
            second = [""] * len(cells)
            second[4] = "대문자 1자 이상, 특수문자 1자 이상"
            out.append("| " + " | ".join(first) + " |")
            out.append("| " + " | ".join(second) + " |")
        else:
            out.append(line)
    return "\n".join(out)


def d_image_table(md: str) -> str:
    """표를 이미지로 대체한다. pdfplumber 는 아무것도 못 읽는다.

    실제 이미지를 만들지 않는다 — 측정하려는 것은 S1 이 표를 못 읽었을 때의
    행동이고, 그 상태는 표가 없는 것과 같다. 그림 자리를 나타내는 문장만 남긴다.
    산문 서술과 다른 점: 본문에 규칙이 한 글자도 없다.
    """
    return _replace_element_table(md, "(UI 요소 정의 표는 별첨 이미지 참조)")


def d_no_section_numbers(md: str) -> str:
    """'## 2. UI 요소 정의' -> '## UI 요소 정의'. 절 번호를 모두 뗀다."""
    return re.sub(r"^(#{2,3}) \d+(-\d+)?\. ", r"\1 ", md, flags=re.M)


def _replace_element_table(md: str, replacement: str) -> str:
    """UI 요소 표 블록만 replacement 로 바꾼다 (다른 표는 건드리지 않는다)."""
    lines = md.splitlines()
    out, i = [], 0
    while i < len(lines):
        if lines[i].startswith("| 요소 ID |"):
            while i < len(lines) and lines[i].startswith("|"):
                i += 1
            out.append(replacement)
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


DEGRADATIONS = [
    ("원본", None, "훼손 없음 — 기준선"),
    ("열 이름 변경", d_rename_header, "'요소 ID' -> '항목'"),
    ("열 누락", d_drop_column, "'안내 문구' 열 제거"),
    ("산문 서술", d_prose, "요소 표를 문장으로"),
    ("셀 병합", d_merge_cells, "한 요소가 두 줄"),
    ("표 이미지화", d_image_table, "표를 못 읽는 상태"),
    ("절 번호 없음", d_no_section_numbers, "'## 2.' -> '##'"),
]


# ---------------------------------------------------------------- 측정

def measure(pdf: Path, llm) -> dict:
    """훼손된 PDF 하나에 S1 을 돌리고 무엇이 남았는지 기록한다."""
    from prova.s1_spec_extractor.extractor import extract_from_pdf
    from prova.s1_spec_extractor.pdf_parser import parse_pdf

    doc = parse_pdf(pdf)
    table = doc._element_table()

    result = {
        "표찾음": table is not None,
        "declared_ids": doc.declared_element_ids(),
        "declared_types": doc.declared_element_types(),
        "declared_placeholders": doc.declared_placeholders(),
        "declared_meta": doc.declared_screen_meta(),
    }

    try:
        spec = extract_from_pdf(pdf, llm)
    except Exception as exc:
        result.update(추출실패=f"{type(exc).__name__}: {exc}"[:90],
                      요소수=0, 규칙수=0, placeholder수=0, 경고=[])
        return result

    result.update(
        요소수=len(spec.elements),
        규칙수=sum(len(e.constraints) for e in spec.elements),
        placeholder수=sum(1 for e in spec.elements if e.placeholder),
        경고=list(spec.warnings),
    )
    return result


def _report(rows) -> None:
    base = rows[0][2]
    print()
    print(f"{'훼손':<15}{'표':<5}{'요소':<6}{'규칙':<6}{'안내':<6}{'경고':<6}판정")
    print("-" * 76)
    silent = []
    for name, note, r in rows:
        if "추출실패" in r:
            print(f"{name:<15}{'-':<5}{'-':<6}{'-':<6}{'-':<6}{'-':<6}"
                  f"예외로 끊김 — 시끄러운 실패")
            continue
        # 조용한 실패: 기준선보다 잃은 것이 있는데 경고가 하나도 없다
        lost = (r["요소수"] < base["요소수"]
                or r["규칙수"] < base["규칙수"]
                or r["placeholder수"] < base["placeholder수"])
        if not lost:
            verdict = "영향 없음"
        elif r["경고"]:
            verdict = "시끄러운 실패 (경고 있음)"
        else:
            verdict = "*** 조용한 실패 ***"
            silent.append(name)
        print(f"{name:<15}{'O' if r['표찾음'] else 'X':<5}"
              f"{r['요소수']:<6}{r['규칙수']:<6}{r['placeholder수']:<6}"
              f"{len(r['경고']):<6}{verdict}")
    print("-" * 76)

    print()
    print("결정적 표 독해가 무엇을 돌려줬나 (빈손이면 LLM 답이 그대로 쓰인다):")
    for name, _, r in rows:
        print(f"  {name:<15} ids={len(r['declared_ids'])} "
              f"types={len(r['declared_types'])} "
              f"placeholders={len(r['declared_placeholders'])} "
              f"meta={len(r['declared_meta'])}")

    print()
    print("경고 내역:")
    any_warn = False
    for name, _, r in rows:
        if r.get("경고"):
            any_warn = True
            print(f"  [{name}]")
            for w in r["경고"]:
                print(f"    - {w[:112]}")
    if not any_warn:
        print("  (없음)")

    print()
    if silent:
        print(f"조용한 실패 {len(silent)}건: {', '.join(silent)}")
        print("이것이 최우선 수정 대상이다 — 사람이 초록불을 믿고 넘어가는 경로다.")
    else:
        print("조용한 실패 없음. 잃은 것이 있을 때는 모두 경고나 예외로 드러났다.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="runs/s1-robustness",
                    help="훼손된 기획서를 둘 곳 (픽스처를 건드리지 않는다)")
    ap.add_argument("--keep", action="store_true", help="측정 후 파일을 남긴다")
    args = ap.parse_args()

    from make_spec_pdf import convert, register_fonts

    from prova.llm.vllm_backend import VLLMClient

    llm = VLLMClient()
    try:
        llm.health()
    except Exception as exc:
        print("7B 서버가 필요합니다 — mock 은 PDF 를 읽지 않아 측정이 성립하지 않습니다.")
        print(f"  {exc}")
        return 2

    register_fonts()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = BASE_MD.read_text(encoding="utf-8")

    rows = []
    for index, (name, fn, note) in enumerate(DEGRADATIONS):
        md = base if fn is None else fn(base)
        md_path = out_dir / f"login_{index}.md"
        md_path.write_text(md, encoding="utf-8")
        pdf = convert(md_path)
        print(f"측정 {index + 1}/{len(DEGRADATIONS)}: {name} ({note})")
        rows.append((name, note, measure(pdf, llm)))

    _report(rows)
    if not args.keep:
        shutil.rmtree(out_dir, ignore_errors=True)
    else:
        print(f"\n훼손된 기획서를 남겼습니다: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
