"""리포트가 명세서 §9 의 다섯 필드를 다 담고 있는가 — 필드 체크리스트 채점.

    uv run python scripts/eval_report_completeness.py
    uv run python scripts/eval_report_completeness.py --runs runs --md

## 무엇을 재는가

명세서 §9 의 마지막 줄이다.

    | 리포트 완결성 | 로그·입력·기대·실제·원인 포함 여부 | 필드 체크리스트 | 100% |

계획서 4-6 의 5번도 같은 것을 요구한다 — "실행 로그·입력 데이터·기대 결과·
실제 결과·실패 원인이 리포트에 정확히 포함되는지 확인".

목표가 **100%** 인데 그동안 이 항목만 측정 결과 문서가 없었다. 기능은 다 들어가
있다고 적혀 있었지만, **적혀 있는 것과 실제로 들어 있는 것은 다르다** — 이
저장소가 반복해서 치른 값이다. 그래서 `report.json` 을 열어 케이스마다 센다.

## 다섯 필드를 어디서 보는가

| 명세서 항목 | 리포트의 어디 | 없으면 |
|---|---|---|
| 실행 로그 | `cases[].step_results[]` (seq·action·status·elapsed_ms) | 개발자가 어디까지 갔는지 모른다 |
| 입력 데이터 | `cases[].step_results[].value` (입력 계열 스텝) | **"정말 그런가" 를 재현할 수 없다** |
| 기대 결과 | `cases[].evidence.expected` | 무엇과 비교했는지 모른다 |
| 실제 결과 | `cases[].evidence.actual` | 판정의 근거가 없다 |
| 실패 원인 | `cases[].failure_category` + `failure_detail` | 무엇을 고쳐야 하는지 모른다 |

## 해당 없음(n/a)과 누락(missing)을 가른다

케이스마다 다섯이 다 필요한 것은 아니다.

- **입력 데이터** 는 입력하는 스텝(`fill`·`select`·`type`)이 있는 케이스에만 해당한다.
  화면을 열어 보기만 하는 케이스에는 입력이 없고, 없는 것을 누락으로 세면 통과율이
  케이스 구성에 따라 흔들린다.
- **실패 원인** 은 FAIL 에만 해당한다. PASS 에 원인을 요구하면 통과율이 실패 비율을
  따라 움직인다.

n/a 는 분모에서 뺀다. **채워야 하는 칸 중 채워진 비율**이 이 지표다.

## 채점을 파일 입출력과 나눈 이유

`check_case` 는 dict 하나를 받아 dict 를 돌려주는 순수 함수다. 리포트를 만들지
않고도 채점을 테스트할 수 있고, 특히 **일부러 필드를 뺀 가짜 리포트**로 점수가
실제로 내려가는지 확인할 수 있다(`tests/test_report_completeness.py`).

좋은 소식만 낼 수 있는 지표는 없는 것보다 나쁘다. 이 지표는 목표가 100% 라서
더 그렇다 — 늘 100% 를 내는 채점기는 아무것도 재지 않는 것과 같다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

# 값을 넣는 스텝. 이 스텝이 있는 케이스에만 '입력 데이터' 를 요구한다.
INPUT_ACTIONS = ("fill", "select", "type")

# 명세서 §9 의 다섯 항목. 출력 순서를 고정하려고 튜플로 둔다.
FIELDS = ("log", "input", "expected", "actual", "cause")

FIELD_LABELS = {
    "log": "실행 로그",
    "input": "입력 데이터",
    "expected": "기대 결과",
    "actual": "실제 결과",
    "cause": "실패 원인",
}

OK, MISSING, NA = "ok", "missing", "n/a"


def _filled(value) -> bool:
    """None·빈 문자열·빈 컬렉션을 '없음' 으로 본다.

    0 과 False 는 값이다 — `elapsed_ms=0` 인 스텝을 누락으로 세면 빠른 스텝이
    벌을 받는다.
    """
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    return True


def check_case(case: dict) -> dict[str, str]:
    """케이스 하나의 판정 dict 를 받아 필드별 ok/missing/n-a 를 돌려준다."""
    steps = case.get("step_results") or []
    evidence = case.get("evidence") or {}
    result: dict[str, str] = {}

    # 1) 실행 로그 — 스텝이 있고, 각 스텝이 무엇을 했는지 읽을 수 있어야 한다.
    if not steps:
        result["log"] = MISSING
    elif all(_filled(s.get("action")) and _filled(s.get("status")) for s in steps):
        result["log"] = OK
    else:
        result["log"] = MISSING

    # 2) 입력 데이터 — 입력 계열 스텝이 있는 케이스에만 해당한다.
    # **빈 문자열은 값이다.** 필수 입력 검증 케이스가 넣는 값이 정확히 그것이라서,
    # `_filled` 로 재면 그 케이스들이 통째로 누락으로 잡힌다(2026-09-23 에 32건).
    # 여기서 보는 것은 '무엇을 넣었는지가 기록됐는가' 이지 '값이 비어 있지
    # 않은가' 가 아니다.
    input_steps = [s for s in steps if s.get("action") in INPUT_ACTIONS]
    if not input_steps:
        result["input"] = NA
    elif all(s.get("value") is not None for s in input_steps):
        result["input"] = OK
    else:
        result["input"] = MISSING

    # 3)·4) 기대와 실제 — 판정의 양쪽이다. 하나만 있으면 비교가 성립하지 않는다.
    result["expected"] = OK if _filled(evidence.get("expected")) else MISSING
    result["actual"] = OK if _filled(evidence.get("actual")) else MISSING

    # 5) 실패 원인 — FAIL 에만 해당한다. 분류와 설명이 둘 다 있어야 조치가 된다.
    if case.get("verdict") != "FAIL":
        result["cause"] = NA
    elif _filled(case.get("failure_category")) and _filled(case.get("failure_detail")):
        result["cause"] = OK
    else:
        result["cause"] = MISSING

    return result


def evaluate(reports: Iterable[dict]) -> dict:
    """리포트 여러 개를 채점해 필드별·전체 집계를 돌려준다.

    Returns:
        {"fields": {필드: {"ok": n, "missing": n, "na": n, "rate": %}},
         "total": {"required": n, "ok": n, "rate": %},
         "cases": n, "reports": n,
         "examples": {필드: [케이스 id …]}}   # 빠진 케이스를 몇 개 남긴다
    """
    tally = {f: {"ok": 0, "missing": 0, "na": 0} for f in FIELDS}
    examples: dict[str, list[str]] = {f: [] for f in FIELDS}
    cases = 0
    n_reports = 0

    for report in reports:
        n_reports += 1
        for case in report.get("cases") or []:
            cases += 1
            for field, status in check_case(case).items():
                key = {OK: "ok", MISSING: "missing", NA: "na"}[status]
                tally[field][key] += 1
                if status == MISSING and len(examples[field]) < 5:
                    examples[field].append(case.get("case_id", "?"))

    fields = {}
    required_total = ok_total = 0
    for f in FIELDS:
        t = tally[f]
        required = t["ok"] + t["missing"]
        required_total += required
        ok_total += t["ok"]
        fields[f] = {
            **t,
            "required": required,
            "rate": round(t["ok"] / required * 100, 1) if required else None,
        }

    return {
        "reports": n_reports,
        "cases": cases,
        "fields": fields,
        "total": {
            "required": required_total,
            "ok": ok_total,
            "rate": round(ok_total / required_total * 100, 1) if required_total else 0.0,
        },
        "examples": examples,
    }


def load_reports(root: Path) -> list[dict]:
    """runs/<run-id>/report.json 을 전부 읽는다."""
    out = []
    for path in sorted(root.glob("*/report.json")):
        out.append(json.loads(path.read_text(encoding="utf-8")))
    return out


def format_table(result: dict, md: bool = False) -> str:
    lines = []
    bar = "|---|---:|---:|---:|---:|"
    lines.append("| 필드 | 채워야 함 | 채워짐 | 빠짐 | 비율 |")
    lines.append(bar)
    for f in FIELDS:
        d = result["fields"][f]
        rate = "—" if d["rate"] is None else f"{d['rate']}%"
        lines.append(
            f"| {FIELD_LABELS[f]} | {d['required']} | {d['ok']} | {d['missing']} | {rate} |"
        )
    t = result["total"]
    lines.append(f"| **전체** | **{t['required']}** | **{t['ok']}** | "
                 f"**{t['required'] - t['ok']}** | **{t['rate']}%** |")
    body = "\n".join(lines)
    if md:
        return body
    return body.replace("|", " ").replace("---:", "").replace("---", "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="runs", help="리포트가 모인 디렉터리")
    ap.add_argument("--md", action="store_true", help="측정 문서용 표를 낸다")
    args = ap.parse_args()

    root = Path(args.runs)
    reports = load_reports(root)
    if not reports:
        print(f"{root}/*/report.json 이 없습니다. 먼저 prova run 으로 리포트를 만드세요.")
        return 2

    result = evaluate(reports)
    print(f"리포트 {result['reports']}개 · 케이스 {result['cases']}건\n")
    print(format_table(result, md=args.md))

    missing = {f: v for f, v in result["examples"].items() if v}
    if missing:
        print("\n빠진 케이스 예시:")
        for f, ids in missing.items():
            print(f"  {FIELD_LABELS[f]}: {', '.join(ids)}")

    # 목표가 100% 다. 미달이면 종료 코드로도 알린다 — CI 에 걸 수 있게.
    return 0 if result["total"]["rate"] == 100.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
