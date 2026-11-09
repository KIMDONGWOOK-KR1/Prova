"""리포트를 엑셀(report.xlsx)로 내보낸다 (B-2).

## 왜 따로 두는가

HTML 리포트는 '읽는' 형식이고 엑셀은 '옮겨 가는' 형식이다. QA 담당자는 케이스 표를
자기 양식에 붙이고, 결함 목록만 골라 개발팀에 넘긴다. 그래서 시트를 셋으로 나눈다.

    요약          실행 조건(대상·기획서·모델·화면 크기·2차 경로)과 수, 경고
    케이스        모든 케이스 한 줄씩 — 구분·실패 원인·기대·실제·근거
    기획서와 다름  assertion_mismatch 만 — 넘길 결함 목록

화면 리포트와 같은 사실을 같은 말로 담는다. 구분 이름은 원형차트(chart_segments)와,
실패 원인 이름은 CATEGORY_LABELS 와 같다 — 엑셀에서만 '실행 문제' 가 결함으로 섞이면
옮겨 간 곳에서 오탐이 된다.

## 셀에 넣는 글자

'실제' 칸에는 사이트에서 읽은 글자가 들어간다. openpyxl 은 '=' 로 시작하는 문자열을
수식으로 저장하므로, 남의 사이트 글자가 엑셀을 여는 사람의 PC 에서 수식으로 돌 수 있다
(CSV/수식 주입). 모든 문자열을 문자열 형식으로 못박는다. 엑셀이 받지 않는 제어문자는
openpyxl 이 예외를 내므로 뺀다.
"""

from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from prova.models import TestReport, Verdict
from prova.s6_report.report_builder import CATEGORY_LABELS, is_weak_pass

XLSX_NAME = "report.xlsx"

_HEAD_FONT = Font(bold=True)
_HEAD_FILL = PatternFill("solid", fgColor="E8EAED")
_KIND_FILL = {
    "기획서와 다름": PatternFill("solid", fgColor="FCE8E6"),
    "실행 문제": PatternFill("solid", fgColor="FEF7E0"),
}

CASE_COLUMNS = ["번호", "화면", "케이스 ID", "제목", "유형", "판정", "구분", "실패 원인",
                "기대", "실제", "상세", "URL", "스크린샷", "시간(초)", "개정"]
DEFECT_COLUMNS = ["번호", "화면", "케이스 ID", "제목", "기획서 기대", "실제 화면", "상세",
                  "URL", "스크린샷"]
_WIDTHS = {"번호": 6, "화면": 16, "케이스 ID": 30, "제목": 36, "유형": 10, "판정": 7,
           "구분": 13, "실패 원인": 13, "기대": 40, "실제": 40, "기획서 기대": 40,
           "실제 화면": 40, "상세": 50, "URL": 36, "스크린샷": 28, "시간(초)": 9, "개정": 40}
_TYPE_LABELS = {"positive": "정상", "negative": "위반"}


def kind_of(v: Verdict) -> str:
    """원형차트와 같은 네 구분 (report_builder.chart_segments)."""
    if v.verdict == "PASS":
        return "약한 확인" if is_weak_pass(v) else "통과"
    return "기획서와 다름" if v.failure_category == "assertion_mismatch" else "실행 문제"


def _clean(value):
    if isinstance(value, str):
        return ILLEGAL_CHARACTERS_RE.sub("", value)
    return value


def _put(ws, row: int, col: int, value):
    cell = ws.cell(row=row, column=col, value=_clean(value))
    if isinstance(cell.value, str):
        # '=' 로 시작해도 수식이 아니라 글자다 (위 모듈 설명).
        cell.data_type = "s"
    return cell


def _detail(v: Verdict) -> str:
    if v.failure_detail:
        return v.failure_detail
    errors = [f"스텝 {r.seq}({r.action} '{r.target}'): {r.error_detail}"
              for r in v.step_results if r.status == "error" and r.error_detail]
    return " / ".join(errors)


def _table(ws, columns: list[str], rows: list[list]) -> None:
    for c, name in enumerate(columns, 1):
        cell = _put(ws, 1, c, name)
        cell.font, cell.fill = _HEAD_FONT, _HEAD_FILL
        ws.column_dimensions[get_column_letter(c)].width = _WIDTHS.get(name, 14)
    kind_col = columns.index("구분") + 1 if "구분" in columns else None
    for r, values in enumerate(rows, 2):
        for c, value in enumerate(values, 1):
            _put(ws, r, c, value).alignment = Alignment(vertical="top", wrap_text=True)
        if kind_col:
            fill = _KIND_FILL.get(values[kind_col - 1])
            if fill:
                ws.cell(row=r, column=kind_col).fill = fill
    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{len(rows) + 1}"


def _case_rows(report: TestReport, names: dict) -> list[list]:
    # 이전 판과 비교해 바뀐 것을 건드리는 케이스 (prova.spec_revision). 판정이 아니라 표시다.
    revised = ((report.summary or {}).get("revision") or {}).get("touched") or {}
    rows = []
    for i, v in enumerate(report.cases, 1):
        ev = v.evidence or {}
        category = (CATEGORY_LABELS.get(v.failure_category, CATEGORY_LABELS["unknown"])[0]
                    if v.verdict == "FAIL" else "")
        rows.append([
            i, names.get(v.screen_id, v.screen_id), v.case_id, v.title,
            _TYPE_LABELS.get(v.type, v.type), v.verdict, kind_of(v), category,
            str(ev.get("expected") or ""), str(ev.get("actual") or ""), _detail(v),
            str(ev.get("url") or ""), str(ev.get("screenshot") or ""),
            round(v.elapsed_ms / 1000, 1),
            " / ".join(revised.get(v.case_id) or []),
        ])
    return rows


def _defect_rows(report: TestReport, names: dict) -> list[list]:
    rows = []
    for v in report.cases:
        if v.verdict != "FAIL" or v.failure_category != "assertion_mismatch":
            continue
        ev = v.evidence or {}
        rows.append([
            len(rows) + 1, names.get(v.screen_id, v.screen_id), v.case_id, v.title,
            str(ev.get("expected") or ""), str(ev.get("actual") or ""), _detail(v),
            str(ev.get("url") or ""), str(ev.get("screenshot") or ""),
        ])
    return rows


def _summary_sheet(ws, report: TestReport) -> None:
    s = report.summary or {}
    kinds = [kind_of(v) for v in report.cases]
    backend = str(s.get("llm_backend") or "")
    lines: list[tuple] = [
        ("Prova 검증 리포트",),
        (),
        ("실행 ID", report.run_id),
        ("실행 시각", report.created_at),
        ("대상 URL", report.target_url),
        ("설계 문서", report.spec_source),
        ("모델", backend),
    ]
    if s.get("viewport"):
        lines.append(("화면 크기", s["viewport"]))
    if "vlm" in s:
        lines.append(("2차 경로(화면 이미지)", f"켬 · {s['vlm']}" if s["vlm"] else "꺼짐"))
    if s.get("project"):
        lines.append(("프로젝트", s["project"]))
    lines += [
        (),
        ("전체", s.get("total", len(report.cases))),
        ("통과", s.get("pass", 0)),
        ("실패", s.get("fail", 0)),
        ("통과율(%)", s.get("pass_rate", 0.0)),
        ("기획서와 다름", kinds.count("기획서와 다름")),
        ("실행 문제", kinds.count("실행 문제")),
        ("약한 확인", kinds.count("약한 확인")),
        ("", "실행 문제는 구현 결함이 아닐 수 있습니다 — 도구·환경(대상·로그인·요소 탐지)을 "
             "먼저 확인하세요. 약한 확인은 성공 조건이 없어 '에러 없음' 만 본 통과입니다."),
    ]
    warnings: list[str] = []
    dry = s.get("dry_run")
    if dry:
        warnings.append(
            f"dry-run — 쓰기 요청을 막고 실행했습니다. 막은 요청 {dry.get('requests_blocked')}건, "
            f"그 때문에 확인 불가가 된 케이스 {dry.get('cases_blocked')}개, 통과시킨 전제(로그인) 요청 "
            f"{dry.get('setup_allowed')}건. {dry.get('limits')}")
    if backend.startswith("mock"):
        warnings.append("mock 백엔드로 실행된 리포트입니다 — 실제 모델의 결과가 아닙니다.")
    edits = s.get("spec_edits") or []
    if edits:
        warnings.append(f"사람이 고친 추출 결과로 실행했습니다({len(edits)}건) — 이 값에 기댄 "
                        "판정은 그 수정이 맞을 때만 유효합니다.")
        warnings += [f"  · {m}" for m in edits]
    rev = s.get("revision") or {}
    if rev:
        changes = rev.get("changes") or []
        touched = len(rev.get("touched") or {})
        warnings.append(f"이전 판 기획서 {rev.get('since')} 과 비교 — 바뀐 것 {len(changes)}건"
                        " (기획서끼리의 차이이며 결함이 아닙니다).")
        warnings.append(
            f"  바뀐 것을 건드리는 케이스 {touched}개만 실행했습니다 (전체 {rev.get('cases_available')}개)."
            if rev.get("changed_only") else
            f"  바뀐 것을 건드리는 케이스 {touched}개는 케이스 시트의 '개정' 칸에 표시했습니다.")
        warnings += [f"  · {m}" for m in changes]
    for gap in s.get("coverage_gaps") or []:
        warnings.append(f"확인하지 않은 것: {gap}")
    if warnings:
        lines += [(), ("주의",)] + [("", w) for w in warnings]

    names = s.get("screen_names") or {}
    by_screen = s.get("by_screen") or {}
    if by_screen:
        lines += [(), ("화면별", "전체", "통과", "실패")]
        lines += [(names.get(k, k), n.get("total", 0), n.get("pass", 0), n.get("fail", 0))
                  for k, n in by_screen.items()]

    for r, values in enumerate(lines, 1):
        for c, value in enumerate(values, 1):
            cell = _put(ws, r, c, value)
            if c == 1 and value:
                cell.font = _HEAD_FONT
            if c == 2:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws["A1"].font = Font(bold=True, size=14)
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 80


def build_workbook(report: TestReport) -> Workbook:
    names = (report.summary or {}).get("screen_names") or {}
    wb = Workbook()
    summary = wb.active
    summary.title = "요약"
    _summary_sheet(summary, report)
    _table(wb.create_sheet("케이스"), CASE_COLUMNS, _case_rows(report, names))
    defects = wb.create_sheet("기획서와 다름")
    rows = _defect_rows(report, names)
    if rows:
        _table(defects, DEFECT_COLUMNS, rows)
    else:
        _put(defects, 1, 1, "기획서와 다른 케이스가 없습니다.")
        defects.column_dimensions["A"].width = 40
    return wb


def save_xlsx(report: TestReport, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / XLSX_NAME
    build_workbook(report).save(path)
    return path


def export_run_dir(run_dir: Path) -> Path:
    """이미 끝난 실행 폴더의 report.json 으로 엑셀을 만든다 (예전 실행용)."""
    data = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    return save_xlsx(TestReport.model_validate(data), run_dir)
