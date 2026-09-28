"""픽스처 기획서 전부에서 만든 케이스를 한 줄씩 적는다 — 생성 결과의 안전망.

## 왜 필요한가

S1·S2 를 고치면 단위 테스트는 고친 자리만 본다. 다른 기획서의 케이스가 조용히
늘거나 사라지거나 기대값이 바뀌어도 테스트는 초록일 수 있다. 고치기 전후로 이
파일을 떠서 `diff` 하면, 바뀐 줄이 곧 이번 변경이 건드린 케이스 전부다. 의도한
줄만 바뀌었는지 사람이 한 번 읽는다.

    기획서 stem \\t case_id \\t 기대 유형 \\t 기대 값

## mock 과 vllm

기본은 mock 이다 — 골든을 정답으로 돌려주므로 S1 의 모델 추출을 빼고 **코드가
만드는 부분(S1 결정적 독해 + S2)만** 비교한다. 코드 변경의 안전망은 이쪽이다.

`--llm vllm` 은 실물 모델의 추출까지 포함한다. 모델을 바꿀 때(예: 7B -> 다른 모델)
두 모델로 각각 떠서 비교하는 데 쓴다. 모델 출력은 매번 조금씩 다를 수 있으므로
같은 모델로 두 번 떠서 흔들림부터 확인한 뒤 차이를 읽는다.

## 사용법

    uv run python scripts/dump_cases.py out/cases_before.tsv
    (고친다)
    uv run python scripts/dump_cases.py out/cases_after.tsv
    diff out/cases_before.tsv out/cases_after.tsv

    uv run python scripts/dump_cases.py out/cases_7b.tsv --llm vllm
"""

from __future__ import annotations

import argparse
import glob
import tempfile
from pathlib import Path

import yaml

from prova.llm.factory import make_llm
from prova.pipeline import build_plan


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path, help="결과 TSV 경로")
    ap.add_argument("--llm", default="mock", choices=["mock", "vllm"])
    ap.add_argument("--model", help="vllm 서빙 모델 이름 (기본: configs/default.yaml)")
    ap.add_argument("--specs", default="fixtures/specs/*_spec.pdf")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path("configs/default.yaml").read_text(encoding="utf-8"))
    if args.model:
        cfg.setdefault("llm", {})["model"] = args.model

    lines = []
    with tempfile.TemporaryDirectory() as run_dir:
        for pdf in sorted(glob.glob(args.specs)):
            llm, _ = make_llm(args.llm, cfg, Path(pdf))
            state, _ = build_plan(pdf, "http://localhost:8100/good", llm,
                                  run_dir=Path(run_dir))
            cases = getattr(state, "all_cases", None) or state.cases
            for c in cases:
                lines.append(f"{Path(pdf).stem}\t{c.case_id}\t"
                             f"{c.expected.type}\t{c.expected.value}")
            print(Path(pdf).stem, len(cases), flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(len(lines), "cases")


if __name__ == "__main__":
    main()
