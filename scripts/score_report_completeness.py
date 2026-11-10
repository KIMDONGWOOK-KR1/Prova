"""리포트 완결성 — 실패 케이스마다 계획서의 다섯 칸이 리포트에 찼는지 센다 (성과 지표, 목표 100%).

## 무엇을 세는가

운영 계획서는 실패 케이스의 리포트가 다섯 가지를 담아야 한다고 적었다. 실행 폴더의
`report.json`(HTML·엑셀이 같은 자료로 그려진다)에서 실패 케이스마다 아래를 본다.

| 칸 | 찼다고 치는 조건 |
|---|---|
| 실행 로그 | 스텝 기록이 한 줄 이상 있고, 줄마다 동작·결과가 있다 |
| 입력 데이터 | 입력·선택 스텝마다 넣은 값이 적혀 있다(빈 칸으로 둔 것은 빈 글자로 적힌다). 입력 스텝이 실행되지 않은 케이스(입력이 없는 확인, 첫 이동에서 멈춘 실행)는 넣은 값이 없으므로 해당 없음 — 찬 것으로 세되 따로 센다 |
| 기대 결과 | '기대' 문장이 있다 |
| 실제 결과 | '실제' 문장과 최종 URL 이 있다 |
| 실패 원인 | 실패 분류와 사유 문장이 있다 |

다섯 칸이 모두 찬 실패 케이스의 비율이 완결성이다.

## 따로 세는 것 (완결성에 넣지 않는다)

- **기획서 근거** — 계획서의 다섯 칸에 없는, 나중에 더한 줄이다. 못 찾으면 비우는 것이 설계다.
- **증거 파일** — 리포트가 가리키는 스크린샷·DOM 파일이 실행 폴더에 실제로 있는가.
- **엑셀** — '기획서와 다름' 시트의 기대·실제·상세·재현 절차 칸이 비지 않았는가.
- **통과 케이스** — 실패 원인을 뺀 네 칸.

## 사용법

    uv run python scripts/dump_verdicts.py out/v.tsv runs/completeness/runs --every-step
    uv run python scripts/score_report_completeness.py runs/completeness/runs

실행 폴더 하나(`report.json` 이 든 폴더)를 줘도 되고, 그런 폴더들이 든 폴더를 줘도 된다.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

FIELDS = ["실행 로그", "입력 데이터", "기대 결과", "실제 결과", "실패 원인"]
INPUT_ACTIONS = {"fill", "select"}


def _has(text) -> bool:
    return isinstance(text, str) and bool(text.strip())


def score_case(case: dict) -> dict[str, bool]:
    """케이스 하나의 다섯 칸. 키는 FIELDS."""
    steps = case.get("step_results") or []
    evidence = case.get("evidence") or {}
    inputs = [s for s in steps if s.get("action") in INPUT_ACTIONS]
    return {
        "실행 로그": bool(steps) and all(_has(s.get("action")) and _has(s.get("status"))
                                     for s in steps),
        # None 은 '값이 기록되지 않음', "" 는 '빈 칸으로 둠' 이다.
        "입력 데이터": all(s.get("value") is not None for s in inputs),
        "기대 결과": _has(evidence.get("expected")),
        "실제 결과": _has(evidence.get("actual")) and _has(evidence.get("url")),
        "실패 원인": _has(case.get("failure_category")) and _has(case.get("failure_detail")),
    }


def has_inputs(case: dict) -> bool:
    return any(s.get("action") in INPUT_ACTIONS for s in case.get("step_results") or [])


def missing_files(case: dict, run_dir: Path) -> list[str]:
    """리포트가 가리키는데 실행 폴더에 없는 증거 파일."""
    names = [(case.get("evidence") or {}).get("screenshot")]
    for step in case.get("step_results") or []:
        names += [step.get("screenshot"), step.get("dom_snapshot")]
    return [n for n in names if n and not (run_dir / n).exists()]


def xlsx_gaps(run_dir: Path) -> tuple[int, list[str]]:
    """엑셀 '기획서와 다름' 시트의 (행 수, 빈 칸이 있는 '케이스 ID:칸' 목록)."""
    path = run_dir / "report.xlsx"
    if not path.exists():
        return 0, []
    from openpyxl import load_workbook

    ws = load_workbook(path, read_only=True)["기획서와 다름"]
    rows = list(ws.iter_rows(values_only=True))
    if not rows or "케이스 ID" not in rows[0]:
        return 0, []  # '기획서와 다른 케이스가 없습니다.'
    head = list(rows[0])
    gaps = []
    for row in rows[1:]:
        for name in ("기획서 기대", "실제 화면", "상세", "재현 절차", "URL"):
            if not _has(row[head.index(name)]):
                gaps.append(f"{row[head.index('케이스 ID')]}:{name}")
    return len(rows) - 1, gaps


def find_runs(root: Path) -> list[Path]:
    if (root / "report.json").exists():
        return [root]
    return sorted(p.parent for p in root.glob("*/report.json"))


def score(root: Path) -> dict:
    """실행 폴더들을 훑어 집계한다."""
    out = {
        "runs": 0, "cases": 0, "fail": 0, "fail_complete": 0, "fail_no_input_steps": 0,
        "field_filled": Counter(), "category": Counter(), "category_complete": Counter(),
        "incomplete": [],
        "fail_with_source": 0, "fail_spec_mismatch": 0, "fail_spec_mismatch_with_source": 0,
        "fail_files_ok": 0, "missing_files": [],
        "pass": 0, "pass_complete": 0, "pass_incomplete": [],
        "xlsx_rows": 0, "xlsx_gaps": [], "runs_without_log": [],
    }
    for run_dir in find_runs(root):
        report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
        out["runs"] += 1
        if not (run_dir / "run.log").exists():
            out["runs_without_log"].append(run_dir.name)
        rows, gaps = xlsx_gaps(run_dir)
        out["xlsx_rows"] += rows
        out["xlsx_gaps"] += [f"{run_dir.name}/{g}" for g in gaps]
        for case in report["cases"]:
            out["cases"] += 1
            fields = score_case(case)
            where = f"{run_dir.name}/{case['case_id']}"
            if case["verdict"] != "FAIL":
                out["pass"] += 1
                empty = [f for f in FIELDS[:4] if not fields[f]]
                out["pass_complete"] += not empty
                if empty:
                    out["pass_incomplete"].append(f"{where}: {', '.join(empty)}")
                continue
            out["fail"] += 1
            out["category"][case.get("failure_category") or "(없음)"] += 1
            out["fail_no_input_steps"] += not has_inputs(case)
            for name in FIELDS:
                out["field_filled"][name] += fields[name]
            empty = [f for f in FIELDS if not fields[f]]
            out["fail_complete"] += not empty
            out["category_complete"][case.get("failure_category") or "(없음)"] += not empty
            if empty:
                out["incomplete"].append(f"{where}: {', '.join(empty)}")
            sourced = bool(case.get("spec_sources"))
            out["fail_with_source"] += sourced
            if case.get("failure_category") == "assertion_mismatch":
                out["fail_spec_mismatch"] += 1
                out["fail_spec_mismatch_with_source"] += sourced
            lost = missing_files(case, run_dir)
            out["fail_files_ok"] += not lost
            out["missing_files"] += [f"{where}: {n}" for n in lost]
    return out


def _pct(part: int, whole: int) -> str:
    return f"{part}/{whole} ({part / whole * 100:.1f}%)" if whole else f"{part}/{whole}"


def render(r: dict) -> str:
    lines = [
        f"실행 {r['runs']}건, 케이스 {r['cases']}건 (실패 {r['fail']}, 통과 {r['pass']})",
        "",
        f"완결성 — 다섯 칸이 모두 찬 실패 케이스: {_pct(r['fail_complete'], r['fail'])}",
    ]
    for name in FIELDS:
        lines.append(f"  {name}: {_pct(r['field_filled'][name], r['fail'])}")
    lines += [
        f"  (입력 스텝이 실행되지 않아 '입력 데이터' 가 해당 없음인 실패 케이스: "
        f"{r['fail_no_input_steps']})",
        "",
        "실패 분류별 완결성",
        *[f"  {k}: {_pct(r['category_complete'][k], v)}" for k, v in r["category"].most_common()],
        "",
        "따로 센 것",
        f"  기획서 근거가 붙은 실패 케이스: {_pct(r['fail_with_source'], r['fail'])}",
        f"    그중 '기획서와 다름': "
        f"{_pct(r['fail_spec_mismatch_with_source'], r['fail_spec_mismatch'])}",
        f"  증거 파일이 모두 있는 실패 케이스: {_pct(r['fail_files_ok'], r['fail'])}",
        f"  엑셀 '기획서와 다름' 행 {r['xlsx_rows']}개 중 빈 칸: {len(r['xlsx_gaps'])}",
        f"  run.log 가 없는 실행: {len(r['runs_without_log'])}",
        f"  통과 케이스의 네 칸(실패 원인 제외): {_pct(r['pass_complete'], r['pass'])}",
    ]
    for title, items in (("빈 칸이 있는 실패 케이스", r["incomplete"]),
                         ("없는 증거 파일", r["missing_files"]),
                         ("엑셀의 빈 칸", r["xlsx_gaps"]),
                         ("빈 칸이 있는 통과 케이스", r["pass_incomplete"])):
        if items:
            lines += ["", f"{title} ({len(items)})"] + [f"  {i}" for i in items[:30]]
            if len(items) > 30:
                lines.append(f"  … 외 {len(items) - 30}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, help="실행 폴더 또는 실행 폴더들이 든 폴더")
    ap.add_argument("--json", type=Path, help="집계를 JSON 으로도 적는다")
    args = ap.parse_args()
    result = score(args.root)
    if not result["runs"]:
        raise SystemExit(f"report.json 을 찾지 못했습니다: {args.root}")
    print(render(result))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
