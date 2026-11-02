"""실물 기획서의 추출 정확도를 사람이 옮겨 적은 정답표로 채점한다 (prova.truth).

    uv run python scripts/score_truth.py --template D:/private/truth.yaml
    (기획서만 보고 표를 채운다 — 추출 결과를 먼저 보지 않는다)
    uv run python scripts/score_truth.py --pdf uploads/실물.pdf --truth D:/private/truth.yaml

정답표는 기획서의 사본이나 다름없다. 저장소 안의 추적되는 경로면 읽지도 쓰지도 않는다.
결과에도 기획서 문구가 찍히므로 터미널로만 낸다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from prova.llm.factory import make_llm
from prova.s1_spec_extractor.extractor import extract_document
from prova.truth import blank_template, format_score, is_private_path, score


def _private(path: Path) -> Path:
    if not is_private_path(path):
        sys.exit(f"{path} 는 저장소에 올라갈 수 있는 경로입니다 — 정답표는 저장소 밖에 두세요.")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--template", type=Path, help="빈 정답표를 이 경로에 쓴다")
    ap.add_argument("--pdf", help="채점할 기획서")
    ap.add_argument("--truth", type=Path, help="채운 정답표(YAML)")
    ap.add_argument("--backend", default="vllm", choices=["vllm", "mock"])
    ap.add_argument("--config", type=Path, default=Path("configs/default.yaml"))
    args = ap.parse_args()

    if args.template:
        path = _private(args.template)
        if path.exists():
            sys.exit(f"{path} 가 이미 있습니다 — 채운 표를 덮어쓰지 않습니다.")
        path.write_text(blank_template(), encoding="utf-8")
        print(f"빈 정답표: {path}")
        return
    if not (args.pdf and args.truth):
        sys.exit("--template 또는 --pdf 와 --truth 가 필요합니다.")

    truth = yaml.safe_load(_private(args.truth).read_text(encoding="utf-8")) or {}
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    llm, warnings = make_llm(args.backend, cfg, Path(args.pdf))
    for w in warnings:
        print(f"! {w}", file=sys.stderr)
    try:
        print(format_score(score(truth, extract_document(args.pdf, llm))))
    except ValueError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
