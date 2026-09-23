"""판정이 정답 라벨과 맞는가 — 명세서 §9 의 PASS/FAIL 판단 정확도.

    uv run python scripts/eval_verdict_accuracy.py
    uv run python scripts/eval_verdict_accuracy.py --labels fixtures/labels/verdict-labels.json --md

## 무엇을 재는가

    | PASS/FAIL 판단 정확도 | 정답 라벨 대비 판정 일치율 | 라벨링된 케이스셋 | ≥ 90% |

README 의 실측 표는 이 능력을 화면마다 문장으로 적어 왔다("심은 결함 4종을 모두
지목, 오탐 0건"). 맞는 말이지만 **한 숫자가 아니다.** "정확도가 얼마냐" 는 물음에
지금까지 댈 수 있는 값이 없었다. 그 하나를 만든다.

## 두 종류의 틀림을 나눠 센다

정확도 하나로 합치면 성질이 다른 실패가 섞인다.

    오탐 (false positive)   정답은 PASS 인데 FAIL 로 보고했다
    미탐 (false negative)   정답은 FAIL 인데 PASS 로 보고했다

이 도구에서 **오탐이 더 나쁘다.** 미탐은 도구의 한계로 남지만, 오탐은 개발자의
시간을 쓰고 한 번 겪으면 진짜 결함 보고까지 무시되기 시작한다. 그래서 합계와
함께 둘을 따로 낸다.

## 라벨을 실행 결과에서 뽑지 않는다

라벨을 결과에서 만들면 정확도는 정의상 100% 가 되고, 그 100% 는 아무것도 재지
않는다. 라벨의 출처는 `sut/app.py` 의 '심은 결함' 표이고, 화면별 건수는 README 와
e2e 테스트에 이 측정보다 먼저 기록돼 있다(`fixtures/labels/verdict-labels.json`
의 `_about` 참고).

## 라벨이 없는 실행은 세지 않는다 — 그리고 그 사실을 보고한다

주문조회는 결함↔케이스 대응이 확인되지 않아 비워 뒀다. 라벨이 없는 케이스를
'맞았다' 쪽에 넣으면 정확도가 부풀고, '틀렸다' 쪽에 넣으면 도구를 억울하게
깎는다. 어느 쪽도 사실이 아니므로 분모에서 빼고, **몇 건 중 몇 건을 쟀는지**를
결과에 항상 함께 낸다. 커버리지 없는 정확도는 숫자만 있는 것이다.

## 채점을 파일 입출력과 나눈 이유

`score` 는 (라벨, 판정) 두 dict 를 받아 집계를 돌려주는 순수 함수다. 일부러
틀린 판정을 먹여 오탐·미탐이 실제로 올라가는지 테스트할 수 있다
(`tests/test_verdict_accuracy.py`). 좋은 소식만 낼 수 있는 지표는 없는 것보다
나쁘다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PASS, FAIL = "PASS", "FAIL"


def expected_verdicts(run_label: dict, case_ids: list[str]) -> dict[str, str]:
    """실행 하나의 라벨을 케이스별 정답 판정으로 펼친다.

    Raises:
        ValueError: `fail` 목록에 그 실행에 없는 case_id 가 있을 때. 라벨이 낡으면
            조용히 정확도가 내려가는데, 원인이 도구가 아니라 라벨이다 — 그 둘을
            섞지 않으려고 여기서 멈춘다.
    """
    mode = run_label.get("expect")
    if mode == "all_pass":
        return {cid: PASS for cid in case_ids}
    if mode == "fail_listed":
        listed = run_label.get("fail") or {}
        unknown = [cid for cid in listed if cid not in case_ids]
        if unknown:
            raise ValueError(f"라벨에 없는 케이스: {', '.join(sorted(unknown))}")
        return {cid: (FAIL if cid in listed else PASS) for cid in case_ids}
    raise ValueError(f"알 수 없는 expect: {mode!r}")


def score(expected: dict[str, str], actual: dict[str, str]) -> dict:
    """정답과 판정을 대조한다. 두 dict 의 키는 같아야 한다.

    Returns:
        {"total", "correct", "false_positive", "false_negative", "accuracy",
         "fp_cases", "fn_cases"}
    """
    fp, fn, correct = [], [], 0
    for cid, want in expected.items():
        got = actual.get(cid)
        if got == want:
            correct += 1
        elif want == PASS and got == FAIL:
            fp.append(cid)
        elif want == FAIL and got == PASS:
            fn.append(cid)
        else:  # 판정이 아예 없는 경우 — 실행이 그 케이스를 내지 않았다
            fn.append(cid)
    total = len(expected)
    return {
        "total": total,
        "correct": correct,
        "false_positive": len(fp),
        "false_negative": len(fn),
        "accuracy": round(correct / total * 100, 1) if total else None,
        "fp_cases": fp,
        "fn_cases": fn,
    }


def evaluate(labels: dict, reports: dict[str, dict]) -> dict:
    """라벨 파일과 {run_id: report dict} 를 받아 실행별·전체 집계를 돌려준다."""
    per_run: dict[str, dict] = {}
    agg = {"total": 0, "correct": 0, "false_positive": 0, "false_negative": 0}
    missing_runs = []

    for run_id, run_label in (labels.get("runs") or {}).items():
        report = reports.get(run_id)
        if report is None:
            missing_runs.append(run_id)
            continue
        cases = report.get("cases") or []
        actual = {c["case_id"]: c["verdict"] for c in cases}
        exp = expected_verdicts(run_label, list(actual))
        s = score(exp, actual)
        s["screen"] = run_label.get("screen", "?")
        s["target"] = run_label.get("target", "?")
        per_run[run_id] = s
        for k in agg:
            agg[k] += s[k]

    agg["accuracy"] = (round(agg["correct"] / agg["total"] * 100, 1)
                       if agg["total"] else None)

    # 커버리지 — 라벨이 없어 세지 않은 케이스까지 분모에 넣어 몇 %를 쟀는지 낸다.
    unlabeled = 0
    for run_id in (labels.get("unlabeled") or {}):
        report = reports.get(run_id)
        if report:
            unlabeled += len(report.get("cases") or [])

    return {
        "per_run": per_run,
        "total": agg,
        "coverage": {
            "labeled": agg["total"],
            "unlabeled": unlabeled,
            "rate": (round(agg["total"] / (agg["total"] + unlabeled) * 100, 1)
                     if agg["total"] + unlabeled else None),
        },
        "missing_runs": missing_runs,
    }


def load_reports(root: Path) -> dict[str, dict]:
    out = {}
    for path in sorted(root.glob("*/report.json")):
        out[path.parent.name] = json.loads(path.read_text(encoding="utf-8"))
    return out


def format_table(result: dict) -> str:
    lines = ["| 실행 | 화면 | 대상 | 케이스 | 맞음 | 오탐 | 미탐 | 정확도 |",
             "|---|---|---|---:|---:|---:|---:|---:|"]
    for run_id, s in result["per_run"].items():
        lines.append(
            f"| `{run_id}` | {s['screen']} | {s['target']} | {s['total']} | "
            f"{s['correct']} | {s['false_positive']} | {s['false_negative']} | "
            f"{s['accuracy']}% |"
        )
    t = result["total"]
    lines.append(
        f"| **전체** | | | **{t['total']}** | **{t['correct']}** | "
        f"**{t['false_positive']}** | **{t['false_negative']}** | **{t['accuracy']}%** |"
    )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--labels", default="fixtures/labels/verdict-labels.json")
    ap.add_argument("--md", action="store_true", help="측정 문서용 표를 낸다")
    args = ap.parse_args()

    labels = json.loads(Path(args.labels).read_text(encoding="utf-8"))
    reports = load_reports(Path(args.runs))
    if not reports:
        print(f"{args.runs}/*/report.json 이 없습니다. 먼저 prova run 으로 만드세요.")
        return 2

    result = evaluate(labels, reports)
    if result["missing_runs"]:
        print("라벨은 있는데 리포트가 없는 실행: "
              + ", ".join(result["missing_runs"]) + "\n")

    cov = result["coverage"]
    print(f"라벨링된 케이스 {cov['labeled']}건 "
          f"(미라벨 {cov['unlabeled']}건 제외 · 커버리지 {cov['rate']}%)\n")
    print(format_table(result))

    t = result["total"]
    fps = [c for s in result["per_run"].values() for c in s["fp_cases"]]
    fns = [c for s in result["per_run"].values() for c in s["fn_cases"]]
    if fps:
        print("\n오탐(정답 PASS · 판정 FAIL): " + ", ".join(fps))
    if fns:
        print("\n미탐(정답 FAIL · 판정 PASS): " + ", ".join(fns))

    return 0 if t["accuracy"] is not None and t["accuracy"] >= 90.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
