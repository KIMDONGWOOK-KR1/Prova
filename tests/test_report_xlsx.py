"""리포트 엑셀 내보내기 (B-2).

엑셀은 리포트를 '옮겨 가는' 형식이다 — QA 양식에 붙이고, 결함 목록을 개발팀에 넘긴다.
그래서 화면 리포트와 같은 사실을 같은 말로 담아야 한다: '기획서와 다름' 과 '실행 문제'
가 갈리고, 약한 확인이 통과와 섞이지 않고, 사람이 고친 값으로 돈 실행이면 그렇다고 말한다.

사이트에서 읽은 글자가 셀에 들어가므로 '=' 로 시작하는 값이 수식으로 실행되면 안 된다.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from prova.models import StepResult, TestReport, Verdict
from prova.s5_verifier.assertion_engine import WEAK_PASS_REASON
from prova.s6_report.report_builder import render_html
from prova.s6_report.xlsx_export import save_xlsx


def _v(case_id: str, verdict: str = "PASS", category=None, actual: str = "ok",
       screen: str = "login", **kw) -> Verdict:
    return Verdict(case_id=case_id, title=f"{case_id} 제목", type="positive", verdict=verdict,
                   screen_id=screen, failure_category=category,
                   evidence={"expected": f"{case_id} 기대", "actual": actual,
                             "url": "http://x/login", "screenshot": f"{case_id}/step1.png"},
                   **kw)


def _report(verdicts: list[Verdict], **summary) -> TestReport:
    s = TestReport.summarize(verdicts)
    s["screen_names"] = {"login": "로그인", "join": "회원가입"}
    s.update(summary)
    return TestReport(run_id="run-1", target_url="http://x", spec_source="s.pdf", summary=s,
                      cases=verdicts, created_at="2026-11-09T10:00:00+09:00")


MIXED = [
    _v("a"),
    _v("b", actual=WEAK_PASS_REASON),
    _v("c", "FAIL", "assertion_mismatch", actual="다른 문구", failure_detail="문구가 다름",
       screen="join"),
    _v("d", "FAIL", "element_not_found", actual="", failure_detail="요소 없음"),
]


def _rows(ws) -> list[list]:
    return [list(r) for r in ws.iter_rows(values_only=True)]


def _table(ws) -> list[dict]:
    rows = _rows(ws)
    return [dict(zip(rows[0], r)) for r in rows[1:]]


def test_시트_세_장을_만든다(tmp_path: Path):
    path = save_xlsx(_report(MIXED), tmp_path)
    assert path == tmp_path / "report.xlsx"
    assert load_workbook(path).sheetnames == ["요약", "케이스", "기획서와 다름"]


def test_케이스_시트는_모든_케이스와_구분을_담는다(tmp_path: Path):
    wb = load_workbook(save_xlsx(_report(MIXED), tmp_path))
    rows = _table(wb["케이스"])
    assert [r["케이스 ID"] for r in rows] == ["a", "b", "c", "d"]
    # 구분은 화면 리포트의 원형차트와 같은 네 이름이다.
    assert [r["구분"] for r in rows] == ["통과", "약한 확인", "기획서와 다름", "실행 문제"]
    c = rows[2]
    assert c["화면"] == "회원가입"
    assert c["판정"] == "FAIL"
    assert c["실패 원인"] == "기획서와 다름"
    assert c["기대"] == "c 기대" and c["실제"] == "다른 문구"
    assert c["상세"] == "문구가 다름"
    assert c["스크린샷"] == "c/step1.png"
    assert rows[3]["실패 원인"] == "요소 미탐지"


def test_결함_목록에는_기획서와_다름만_들어간다(tmp_path: Path):
    wb = load_workbook(save_xlsx(_report(MIXED), tmp_path))
    rows = _table(wb["기획서와 다름"])
    assert [r["케이스 ID"] for r in rows] == ["c"]
    assert rows[0]["기획서 기대"] == "c 기대"
    assert rows[0]["실제 화면"] == "다른 문구"


def test_결함이_없으면_없다고_적는다(tmp_path: Path):
    wb = load_workbook(save_xlsx(_report([_v("a")]), tmp_path))
    rows = _rows(wb["기획서와 다름"])
    assert any("없습니다" in str(c) for r in rows for c in r if c)


def test_요약은_화면_리포트와_같은_수를_말한다(tmp_path: Path):
    wb = load_workbook(save_xlsx(_report(MIXED, viewport="390x844", vlm=""), tmp_path))
    kv = {r[0]: r[1] for r in _rows(wb["요약"]) if r and r[0]}
    assert kv["실행 ID"] == "run-1"
    assert kv["대상 URL"] == "http://x"
    assert kv["전체"] == 4 and kv["통과"] == 2 and kv["실패"] == 2
    assert kv["기획서와 다름"] == 1
    assert kv["실행 문제"] == 1
    assert kv["약한 확인"] == 1
    assert kv["화면 크기"] == "390x844"
    assert kv["2차 경로(화면 이미지)"] == "꺼짐"


def test_사람이_고친_값으로_돈_실행이면_요약이_말한다(tmp_path: Path):
    wb = load_workbook(save_xlsx(_report(MIXED, spec_edits=["로그인 · 라벨 '아이디' → 'ID'"]),
                                 tmp_path))
    text = " ".join(str(c) for r in _rows(wb["요약"]) for c in r if c)
    assert "사람이 고친" in text
    assert "로그인 · 라벨 '아이디' → 'ID'" in text


def test_mock_실행이면_요약이_경고한다(tmp_path: Path):
    wb = load_workbook(save_xlsx(_report(MIXED, llm_backend="mock"), tmp_path))
    text = " ".join(str(c) for r in _rows(wb["요약"]) for c in r if c)
    assert "mock" in text and "실제" in text


def test_등호로_시작하는_글자는_수식이_되지_않는다(tmp_path: Path):
    v = _v("x", "FAIL", "assertion_mismatch", actual="=HYPERLINK(\"http://evil\",\"클릭\")")
    wb = load_workbook(save_xlsx(_report([v]), tmp_path))
    row = _table(wb["케이스"])[0]
    assert row["실제"] == "=HYPERLINK(\"http://evil\",\"클릭\")"
    # openpyxl 은 '=' 로 시작하는 문자열을 수식(data_type 'f')으로 저장한다 — 그러면 안 된다.
    ws = wb["케이스"]
    header = [c.value for c in ws[1]]
    cell = ws.cell(row=2, column=header.index("실제") + 1)
    assert cell.data_type == "s"


def test_엑셀이_못_받는_제어문자는_빼고_저장한다(tmp_path: Path):
    v = _v("x", "FAIL", "assertion_mismatch", actual="앞\x00\x07뒤")
    wb = load_workbook(save_xlsx(_report([v]), tmp_path))
    assert _table(wb["케이스"])[0]["실제"] == "앞뒤"


def test_HTML_리포트에_엑셀_받기_링크가_있다():
    assert "href='report.xlsx'" in render_html(_report(MIXED))


def test_예전_report_json_으로도_만든다(tmp_path: Path):
    from prova.s6_report.report_builder import save_json
    from prova.s6_report.xlsx_export import export_run_dir

    save_json(_report(MIXED), tmp_path)
    path = export_run_dir(tmp_path)
    assert path == tmp_path / "report.xlsx"
    assert len(_table(load_workbook(path)["케이스"])) == 4


def test_스텝_오류는_상세가_비면_대신_쓴다(tmp_path: Path):
    v = _v("x", "FAIL", "element_not_found", actual="",
           step_results=[StepResult(seq=1, action="fill", target="아이디", status="error",
                                    error_detail="일치하는 요소가 없음")])
    wb = load_workbook(save_xlsx(_report([v]), tmp_path))
    assert "일치하는 요소가 없음" in _table(wb["케이스"])[0]["상세"]


def test_CLI_export_xlsx(tmp_path: Path):
    from typer.testing import CliRunner

    from prova.cli import app
    from prova.s6_report.report_builder import save_json

    save_json(_report(MIXED), tmp_path)
    result = CliRunner().invoke(app, ["export-xlsx", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "report.xlsx").exists()


def test_CLI_export_xlsx_report_json_이_없으면_알린다(tmp_path: Path):
    from typer.testing import CliRunner

    from prova.cli import app

    result = CliRunner().invoke(app, ["export-xlsx", str(tmp_path)])
    assert result.exit_code != 0
    assert "report.json" in result.output
