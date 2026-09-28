"""SUT 의 모든 (기획서 × 변형) 조합을 실행해 케이스별 판정·분류를 적는다 — 판정의 안전망.

## 왜 필요한가

S3~S5 의 분류 규칙을 고치면(예: '못 찾음' 과 '구현 결함' 의 경계) 단위 테스트는
고친 분기만 본다. 좋은 구현이 FAIL 로 바뀌거나 결함 변형이 PASS 로 바뀌어도
놓칠 수 있다. 고치기 전후로 떠서 `diff` 하면 판정이 바뀐 케이스가 전부 나온다.

    기획서 stem \\t 변형 \\t case_id \\t 판정 \\t 실패 분류

SUT 의 변형 10종(good·bad·slow·spa·…)은 같은 화면의 올바른 구현과 결함 구현이다.
기획서 9개 × 10 = 90 실행, 약 30분 걸린다.

## 준비

SUT 를 8199 포트로 먼저 띄운다(다른 테스트가 쓰는 포트와 겹치지 않게):

    uv run uvicorn sut.app:app --port 8199

LLM 은 mock 이다 — 모델 흔들림을 빼고 **판정 코드만** 비교하기 위해서다.

## 사용법

    uv run python scripts/dump_verdicts.py out/verdicts_before.tsv out/runs_before
    (고친다)
    uv run python scripts/dump_verdicts.py out/verdicts_after.tsv out/runs_after
    diff out/verdicts_before.tsv out/verdicts_after.tsv
"""

from __future__ import annotations

import argparse
import glob
import time
from pathlib import Path

from prova.llm.factory import make_llm
from prova.pipeline import run_pipeline

VARIANTS = ["good", "bad", "slow", "spa", "hashed", "native", "nolabel", "slowleak",
            "table", "badtable"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path, help="결과 TSV 경로")
    ap.add_argument("runs_root", type=Path, help="실행 산출물(스크린샷 등)을 둘 폴더")
    ap.add_argument("--base", default="http://localhost:8199")
    args = ap.parse_args()

    lines = []
    t0 = time.time()
    for pdf in sorted(glob.glob("fixtures/specs/*_spec.pdf")):
        stem = Path(pdf).stem
        for v in VARIANTS:
            llm, _ = make_llm("mock", {}, Path(pdf))
            try:
                report, _ = run_pipeline(pdf, f"{args.base}/{v}", llm,
                                         run_id=f"{stem}-{v}", runs_root=args.runs_root,
                                         screenshot_every_step=False)
            except Exception as exc:  # 그 변형에 없는 화면이면 파이프라인이 멈출 수 있다
                lines.append(f"{stem}\t{v}\t-\tERROR\t{type(exc).__name__}")
                continue
            for c in report.cases:
                lines.append(f"{stem}\t{v}\t{c.case_id}\t{c.verdict}\t{c.failure_category}")
        print(stem, f"{time.time() - t0:.0f}s", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(len(lines), "rows")


if __name__ == "__main__":
    main()
