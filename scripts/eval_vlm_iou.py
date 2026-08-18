"""굳은 데이터셋으로 탐지 정확도를 채점한다 (VL 서버 필요).

    uv run python scripts/eval_vlm_iou.py --vlm http://localhost:8001/v1 --vlm-model qwen-vl
    uv run python scripts/eval_vlm_iou.py --backend oracle          # 배관만 점검 (GPU 불필요)

## 무엇을 재는가

명세서 §9 는 '탐지 성공률 ≥90%(IoU 기준)' 과 'selector 대비 속도' 를 요구한다. 여기서
네 가지를 낸다.

    탐지 성공률(IoU)   있는 요소를 IoU 문턱값 이상으로 맞힌 비율  ← 명세서가 요구한 지표
    적중률             중심이 요소 안에 들어온 비율               ← 실제 클릭 성패
    오탐률             없는 요소를 '찾았다' 고 한 비율            ← 낮아야 한다
    호출 시간          한 요소를 찾는 데 걸린 시간

## 관문을 채점에 포함하는 이유

파이프라인은 신뢰도가 문턱값 아래면 보정을 포기한다(`heal_with_vlm`). 그래서 모델이
좌표를 맞혔어도 신뢰도가 낮으면 **실제로는 탐지 실패**다. 관문을 무시하고 좌표만 채점하면
보고서의 숫자가 실행 결과보다 좋게 나온다.

그래서 성공은 '관문 통과 + 좌표 정확' 으로 센다. 다만 **관문이 버린 정답의 수를 따로 센다**
— 그 값이 크면 고칠 곳은 모델이 아니라 문턱값이다. 두 원인을 한 숫자에 섞으면 어느 쪽도
고칠 수 없다.

## oracle 백엔드

`--backend oracle` 은 정답을 그대로(또는 `--jitter` 만큼 밀어서) 돌려주는 가짜 모델이다.
GPU 없이 **채점·표·보고서 경로가 도는지**만 확인한다.

**이 값은 정확도가 아니다.** 정답을 보고 답하는 모델이므로 100% 가 나오는 게 당연하다.
2026-08-17 에 MockVLM 초록불을 정확도로 착각할 위험을 이미 만났으므로(`probe_vlm` 의
탄생 이유), 출력에 그 사실을 크게 적는다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from prova.vlm.base import Located, VLMError
from prova.vlm.metrics import DEFAULT_IOU_THRESHOLD, center_error, center_hit, iou


@dataclass
class OracleVLM:
    """정답을 보고 답하는 가짜 모델 — 배관 점검용. 정확도 측정에 쓰면 안 된다.

    `VLMClient` 프로토콜을 그대로 만족시키는 이유: 채점 경로를 실물과 똑같이 지나가야
    점검의 뜻이 있다. 루프 안에서 분기하면 실제로 돌 코드를 점검하지 않게 된다.
    """

    name: str = "oracle"
    jitter: float = 0.0
    #: 다음 호출의 정답. 없는 요소(absent)면 None — 그때는 '못 찾았다' 로 답한다.
    truth: tuple[float, float, float, float] | None = None

    def locate(self, *, image_png: bytes, target: str, hint: str = "") -> Located:
        if self.truth is None:
            # 완벽한 모델이라면 없는 것을 없다고 말한다. 신뢰도 0 으로 관문에 막힌다.
            return Located(bbox=(0.0, 0.0, 0.0, 0.0), confidence=0.0)
        x1, y1, x2, y2 = self.truth
        dx, dy = (x2 - x1) * self.jitter, (y2 - y1) * self.jitter
        return Located(bbox=(x1 + dx, y1 + dy, x2 + dx, y2 + dy), confidence=1.0)


def score_present(item: dict, found: Located, min_conf: float,
                  threshold: float) -> dict:
    """있는 요소 하나를 채점한다."""
    truth = tuple(item["truth"])
    gate = found.confidence >= min_conf and found.is_sane()
    overlap = iou(found.bbox, truth)
    hit = center_hit(found.bbox, truth)
    return {"gate": gate, "iou": overlap, "hit": hit,
            "center_error": center_error(found.bbox, truth),
            "confidence": found.confidence,
            "sane": found.is_sane(),
            # 성공은 관문을 통과한 것만 센다 — 파이프라인이 그렇게 동작한다.
            "success_iou": gate and overlap >= threshold,
            "success_hit": gate and hit,
            # 관문이 정답을 버린 경우. 이 수가 크면 고칠 곳은 문턱값이다.
            "gate_dropped": (not gate) and overlap >= threshold}


def evaluate(items: list[dict], vlm, *, min_conf: float, threshold: float,
             oracle: OracleVLM | None) -> list[dict]:
    rows = []
    for item in items:
        if oracle is not None:
            oracle.truth = tuple(item["truth"]) if item["present"] else None
        image = (Path(item["_dir"]) / item["image"]).read_bytes()
        started = time.perf_counter()
        try:
            found = vlm.locate(image_png=image, target=item["target"],
                               hint=item["hint"])
            error = None
        except VLMError as exc:
            found, error = None, str(exc)[:80]
        elapsed_ms = (time.perf_counter() - started) * 1000

        row = {k: item[k] for k in ("id", "state_id", "note", "target", "kind",
                                    "present")}
        row["elapsed_ms"] = elapsed_ms
        row["error"] = error
        if found is None:
            # 호출 실패는 '못 찾았다' 다. 없는 요소였다면 그게 맞는 답이다.
            row.update({"gate": False, "confidence": None, "bbox": None})
            if item["present"]:
                row.update({"iou": 0.0, "hit": False, "success_iou": False,
                            "success_hit": False, "gate_dropped": False})
        else:
            row["bbox"] = list(found.bbox)
            row["confidence"] = found.confidence
            if item["present"]:
                row.update(score_present(item, found, min_conf, threshold))
            else:
                # 없는 것을 물었다. 관문을 통과했다면 오탐이다.
                row["gate"] = found.confidence >= min_conf and found.is_sane()
        rows.append(row)
        mark = _mark(row)
        print(f"  [{row['id']:>2}] {row['state_id']:<16}{row['target']:<14}"
              f"{mark}  {elapsed_ms:>6.0f}ms")
    return rows


def _mark(row: dict) -> str:
    """한 항목의 결과를 한 눈에. 진행 중 눈으로 따라가려고 쓴다."""
    if row["error"]:
        return f"호출실패 ({row['error'][:30]})"
    if not row["present"]:
        return "오탐" if row["gate"] else "없다고 답함 (정답)"
    if row["success_iou"]:
        return f"성공  IoU {row['iou']:.2f}"
    if row["gate_dropped"]:
        return f"관문차단  IoU {row['iou']:.2f} 신뢰도 {row['confidence']:.2f}"
    if row["hit"] and row["gate"]:
        return f"적중만  IoU {row['iou']:.2f}"
    return f"실패  IoU {row['iou']:.2f}"


def summarize(rows: list[dict], threshold: float) -> dict:
    present = [r for r in rows if r["present"]]
    absent = [r for r in rows if not r["present"]]
    hit_ms = [r["elapsed_ms"] for r in rows]
    return {
        "present": len(present),
        "absent": len(absent),
        "iou_threshold": threshold,
        "success_iou": sum(1 for r in present if r["success_iou"]),
        "success_hit": sum(1 for r in present if r["success_hit"]),
        "gate_dropped": sum(1 for r in present if r["gate_dropped"]),
        "call_failed": sum(1 for r in rows if r["error"]),
        "false_positive": sum(1 for r in absent if r["gate"]),
        "mean_iou": (sum(r["iou"] for r in present) / len(present)
                     if present else 0.0),
        "mean_ms": sum(hit_ms) / len(hit_ms) if hit_ms else 0.0,
        "max_ms": max(hit_ms) if hit_ms else 0.0,
    }


def rate(n: int, total: int) -> str:
    return f"{n}/{total} = {100 * n / total:.1f}%" if total else "0/0"


def _num(value: float | None) -> str:
    """표 칸 하나. 없는 값과 0 을 구분한다 — 없는 값을 0 으로 찍으면 '완벽하게
    맞혔다'(중심오차 0)로 읽힌다. 무한대는 잴 수 없었다는 뜻이므로 그대로 표시한다."""
    if value is None:
        return "-"
    if value == float("inf"):
        return "∞"
    return f"{value:.2f}"


def by_state(rows: list[dict]) -> list[tuple[str, int, int, int]]:
    """화면별 (성공, 있음, 오탐) 집계.

    전체 비율만 보면 **어느 화면이 약한지 안 보인다.** 아이콘 버튼 화면이 통째로
    틀리고 나머지가 다 맞아도, 합쳐 놓으면 '조금 부족하다' 로 읽힌다. 2차 경로를
    쓸지 말지는 그 화면에서 되는지로 정해진다.
    """
    order, seen = [], {}
    for r in rows:
        if r["state_id"] not in seen:
            seen[r["state_id"]] = [0, 0, 0]
            order.append(r["state_id"])
        cell = seen[r["state_id"]]
        if r["present"]:
            cell[1] += 1
            cell[0] += bool(r.get("success_iou"))
        else:
            cell[2] += bool(r["gate"])
    return [(sid, *seen[sid]) for sid in order]


def write_report(path: Path, meta: dict, rows: list[dict], s: dict) -> None:
    """사람이 읽을 표를 쓴다. 전체 요약 -> 화면별 -> 항목별 순서다."""
    lines = [
        f"# VLM 탐지 정확도 — {meta['model']}",
        "",
        f"- 데이터셋 `{meta['dataset_id']}` · 화면 {meta['states']}장 · "
        f"항목 {s['present'] + s['absent']}개 (있음 {s['present']} · 없음 {s['absent']})",
        f"- IoU 문턱값 {s['iou_threshold']} · 신뢰도 문턱값 {meta['min_confidence']}",
        *(["", "> **연습 실행이다 — 데이터셋의 일부만 채점했다.** 전체 측정값이 아니다."]
          if meta.get("partial") else []),
        "",
        "## 결과",
        "",
        "| 지표 | 값 | 뜻 |",
        "|---|---|---|",
        f"| 탐지 성공률 (IoU 기준) | {rate(s['success_iou'], s['present'])} | "
        "명세서 §9 가 요구한 지표 |",
        f"| 적중률 (중심이 요소 안) | {rate(s['success_hit'], s['present'])} | "
        "실제로 클릭이 되는 비율 |",
        f"| 오탐 (없는 것을 찾았다고 함) | {rate(s['false_positive'], s['absent'])} | "
        "낮아야 한다 |",
        f"| 관문이 버린 정답 | {s['gate_dropped']}개 | "
        "크면 고칠 곳은 모델이 아니라 문턱값이다 |",
        f"| 호출 실패 | {s['call_failed']}개 | 서버·응답 문제 |",
        f"| 평균 IoU | {s['mean_iou']:.3f} | |",
        f"| 호출 시간 | 평균 {s['mean_ms']:.0f}ms · 최대 {s['max_ms']:.0f}ms | |",
        "",
        "## 화면별",
        "",
        "| 화면 | 탐지 성공 (IoU) | 오탐 |",
        "|---|---|---|",
    ]
    for sid, ok, total, fp in by_state(rows):
        lines.append(f"| {sid} | {rate(ok, total)} | {fp}개 |")
    lines += [
        "",
        "## 항목별",
        "",
        "| 화면 | 요소 | 종류 | 결과 | IoU | 중심오차 | 신뢰도 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        name = r["target"] if r["present"] else f"{r['target']} (없음)"
        cells = [r["state_id"], name, r["kind"], _mark(r),
                 _num(r.get("iou")), _num(r.get("center_error")),
                 _num(r.get("confidence"))]
        lines.append("| " + " | ".join(cells) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default="fixtures/iou/dataset.json")
    ap.add_argument("--backend", choices=("qwen", "oracle"), default="qwen")
    ap.add_argument("--vlm", default="http://localhost:8001/v1")
    ap.add_argument("--vlm-model", default="qwen-vl")
    ap.add_argument("--min-confidence", type=float, default=None,
                    help="기본값은 파이프라인과 같은 MIN_CONFIDENCE 다")
    ap.add_argument("--iou-threshold", type=float, default=DEFAULT_IOU_THRESHOLD)
    ap.add_argument("--jitter", type=float, default=0.0,
                    help="oracle 백엔드가 정답을 요소 크기의 이 비율만큼 밀어 답한다")
    ap.add_argument("--limit", type=int, default=0,
                    help="앞에서 N개만 채점한다 (0=전부). 형식 확인용 연습 실행에 쓴다 — "
                         "50개를 다 돌린 뒤에 응답 형식 문제를 발견하면 시간을 두 번 쓴다")
    ap.add_argument("--out", default=None, help="결과 파일 접두어 (기본: 데이터셋 옆)")
    args = ap.parse_args()

    from prova.s3_grounder.dom_locator import MIN_CONFIDENCE

    min_conf = args.min_confidence if args.min_confidence is not None else MIN_CONFIDENCE

    path = Path(args.dataset)
    if not path.exists():
        print(f"데이터셋이 없습니다: {path}\n"
              f"먼저 만드세요: uv run python scripts/build_iou_dataset.py")
        return 2
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data["items"]
    for item in items:
        item["_dir"] = str(path.parent)

    oracle = None
    if args.backend == "oracle":
        oracle = OracleVLM(jitter=args.jitter)
        vlm = oracle
        model_name = f"oracle(jitter={args.jitter})"
        print("=" * 72)
        print("oracle 백엔드입니다 — 정답을 보고 답하는 가짜 모델.")
        print("여기서 나오는 숫자는 정확도가 아니라 배관 점검 결과다.")
        print("=" * 72)
    else:
        from prova.vlm.qwen_vl import QwenVLClient
        vlm = QwenVLClient(base_url=args.vlm, model=args.vlm_model)
        try:
            vlm.health()
        except VLMError as exc:
            print(f"VL 서버에 닿지 않습니다: {exc}")
            return 2
        model_name = args.vlm_model

    if args.limit:
        items = items[:args.limit]
        # 부분 실행임을 결과 파일에도 남긴다. 남기지 않으면 나중에 이 숫자를 전체
        # 측정값으로 읽게 된다 — '실행하지 않은 것과 통과한 것' 을 섞는 것과 같은 실수다.
        print(f"[연습 실행] 앞 {args.limit}개만 채점합니다 — 전체 측정값이 아닙니다")

    print(f"데이터셋 {data['dataset_id']} · 항목 {len(items)}개 · 모델 {model_name}")
    rows = evaluate(items, vlm, min_conf=min_conf,
                    threshold=args.iou_threshold, oracle=oracle)
    s = summarize(rows, args.iou_threshold)

    # 결과는 `runs/`(gitignore)에 둔다. 시험지(fixtures/iou)와 답안지를 같은 폴더에
    # 두면 연습 실행 파일까지 저장소에 섞여 들어가, 나중에 어느 것이 보고에 쓴
    # 측정값인지 알 수 없게 된다. 보고에 쓸 결과만 사람이 docs/ 로 옮긴다.
    suffix = f"-first{args.limit}" if args.limit else ""
    safe = model_name.replace("(", "-").replace(")", "")
    stem = args.out or f"runs/iou/result-{safe}{suffix}"
    Path(stem).parent.mkdir(parents=True, exist_ok=True)
    meta = {"model": model_name, "dataset_id": data["dataset_id"],
            "states": len({r["state_id"] for r in rows}),
            "min_confidence": min_conf,
            "partial": bool(args.limit)}
    Path(f"{stem}.json").write_text(
        json.dumps({"meta": meta, "summary": s, "rows": rows},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(Path(f"{stem}.md"), meta, rows, s)

    print()
    print(f"탐지 성공률 (IoU≥{args.iou_threshold})  {rate(s['success_iou'], s['present'])}")
    print(f"적중률 (중심이 요소 안)      {rate(s['success_hit'], s['present'])}")
    print(f"오탐 (없는 것을 찾았다고)     {rate(s['false_positive'], s['absent'])}")
    print(f"관문이 버린 정답            {s['gate_dropped']}개")
    print(f"호출 실패                 {s['call_failed']}개")
    print(f"평균 IoU                 {s['mean_iou']:.3f}")
    print(f"호출 시간                 평균 {s['mean_ms']:.0f}ms · 최대 {s['max_ms']:.0f}ms")
    print()
    print(f"-> {stem}.md · {stem}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
