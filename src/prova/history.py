"""실행 이력 — 같은 검사를 몇 차로 돌렸고 직전과 무엇이 달라졌는가.

## 왜 데이터베이스가 아닌가

이력의 원본은 이미 있다. 실행마다 `runs/<id>/report.json` 이 남고, 웹 UI 도 그것을
훑어 목록을 만든다. 따로 저장소를 두면 '폴더를 지웠는데 이력에는 남아 있는' 어긋남이
생기고, 리포트를 폴더째 넘겨받은 사람의 기계에서는 이력이 사라진다. 그래서 파일을
읽어 그때그때 계산하고, 계산한 결과는 **그 실행의 리포트에 박아 둔다** — 나중에
옛 실행을 지워도 이번 리포트가 말한 비교는 남는다.

## 무엇을 '같은 검사' 로 보는가

    프로젝트를 적었으면   프로젝트 + 기획서
    안 적었으면           기획서 + 대상 URL

납품 차수마다 스테이징 주소가 바뀌는 것이 보통이라, 사람이 프로젝트 이름을 적어
묶겠다고 하면 주소는 보지 않는다. 안 적었을 때는 주소까지 같아야 묶는다 — /good 과
/bad 를 한 줄로 이으면 '고쳐졌다' 가 거짓이 된다.

**mock 과 실제 모델은 잇지 않는다.** 모델이 달라 생긴 차이가 구현이 달라진 것처럼
보이면 안 된다. 같은 이유로 비교는 양쪽에 다 있는 케이스만 한다. 한쪽에만 있는
케이스를 '새로 실패·해결' 에 넣으면 기획서가 바뀐 것과 구현이 바뀐 것이 섞인다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from prova.models import TestReport


def _load(path: Path) -> Optional[dict]:
    """report.json 하나를 읽는다. 깨졌으면 None — 한 건이 목록 전체를 막지 않게."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def load_reports(root: Path) -> list[dict]:
    """runs/ 아래 리포트 원본을 최신순으로 읽는다.

    report.json 이 없는 디렉터리가 많다 — 디버그·데모 잔여물이다.
    """
    root = Path(root)
    if not root.exists():
        return []
    found = []
    for d in root.iterdir():
        meta = d / "report.json"
        if not d.is_dir() or not meta.exists():
            continue
        data = _load(meta)
        if data is not None:
            data.setdefault("run_id", d.name)
            found.append(data)
    found.sort(key=lambda r: (r.get("created_at", ""), r["run_id"]), reverse=True)
    return found


def list_runs(root: Path, limit: Optional[int] = None) -> list[dict]:
    """지난 실행 목록. 케이스 본문은 빼고 목록에 보일 칸만 준다."""
    runs = []
    for data in load_reports(root):
        summary = data.get("summary") or {}
        runs.append({
            "run_id": data["run_id"],
            "target": data.get("target_url", ""),
            "spec": Path(data.get("spec_source", "")).name,
            "created_at": data.get("created_at", ""),
            "total": summary.get("total", 0),
            "pass": summary.get("pass", 0),
            "fail": summary.get("fail", 0),
            "project": summary.get("project", ""),
            "round": (summary.get("history") or {}).get("round"),
            "summary": summary,
        })
    return runs[:limit] if limit is not None else runs


def _is_mock(summary: dict) -> bool:
    return str(summary.get("llm_backend", "")).startswith("mock")


def _same_series(summary: dict, spec: str, target: str, data: dict) -> bool:
    other = data.get("summary") or {}
    project = summary.get("project", "")
    if project != other.get("project", ""):
        return False
    if _is_mock(summary) != _is_mock(other):
        return False
    if spec != Path(data.get("spec_source", "")).name:
        return False
    return bool(project) or target == data.get("target_url", "")


def _is_partial(summary: dict, selection: Optional[dict]) -> bool:
    return bool(summary.get("filtered_by")) or bool((selection or {}).get("excluded"))


def attach_history(report: TestReport, runs_root: Path) -> None:
    """이번 리포트에 차수와 직전 실행과의 비교를 적는다 (summary['history']).

    report.json 을 쓰기 **전에** 불러야 한다. 같은 이름으로 다시 돌린 실행은 자기
    옛 판을 지우고 덮어쓰는 것이므로 비교 대상에 넣지 않는다.
    """
    summary = report.summary
    spec = Path(report.spec_source).name
    earlier = [r for r in load_reports(runs_root)
               if r["run_id"] != report.run_id
               and _same_series(summary, spec, report.target_url, r)]

    history = {"round": len(earlier) + 1, "previous_run": None, "previous_at": "",
               "regressed": [], "fixed": [], "added": 0, "removed": 0, "partial": False}
    if earlier:
        prev = earlier[0]
        before = {c.get("case_id"): c.get("verdict") for c in prev.get("cases") or []}
        now = {v.case_id for v in report.cases}
        history.update(
            previous_run=prev["run_id"],
            previous_at=prev.get("created_at", ""),
            regressed=[v.title for v in report.cases
                       if v.verdict == "FAIL" and before.get(v.case_id) == "PASS"],
            fixed=[v.title for v in report.cases
                   if v.verdict == "PASS" and before.get(v.case_id) == "FAIL"],
            added=len(now - before.keys()),
            removed=len(before.keys() - now),
            # 일부만 돌린 실행과 비교하면 케이스 증감은 기획서 변화가 아니다.
            partial=(_is_partial(prev.get("summary") or {}, prev.get("selection"))
                     or _is_partial(summary, report.selection.model_dump()
                                    if report.selection else None)),
        )
    summary["history"] = history
