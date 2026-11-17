"""리포트 옆에 남는 자료 — 결과표 CSV 와 실행 로그 (2026-10 멘토링).

리포트가 화면 하나로만 남으면 차수끼리 비교하거나 실행이 왜 그렇게 흘렀는지
되짚을 수 없다.
"""

import csv

from prova.models import TestReport, Verdict
from prova.pipeline import _logged
from prova.s6_report.report_builder import render_html, save_csv


def _report() -> TestReport:
    cases = [
        Verdict(case_id="login-valid-001", title="정상 로그인", screen_id="login",
                verdict="PASS", evidence={"actual": "경로 '/dashboard' 이동 확인"}),
        Verdict(case_id="login-email-format-003", title="이메일 형식", screen_id="login",
                verdict="FAIL", violates="format", failure_category="assertion_mismatch",
                failure_detail="형식 규칙이 구현에 없다"),
    ]
    return TestReport(run_id="r", target_url="http://x", cases=cases,
                      summary={"total": 2, "pass": 1, "fail": 1, "pass_rate": 50.0,
                               "screen_names": {"login": "로그인"}})


def test_CSV_는_엑셀이_한글을_읽도록_BOM_으로_쓴다(tmp_path):
    path = save_csv(_report(), tmp_path)
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(path.open(encoding="utf-8-sig")))
    assert rows[0][:5] == ["화면", "흐름", "케이스", "제목", "판정"]
    assert rows[2][0] == "로그인" and rows[2][4] == "FAIL" and rows[2][5] == "기획서와 다름"


def test_진행_메시지가_화면과_run_log_에_함께_남는다(tmp_path):
    seen = []
    report = _logged(seen.append, tmp_path)
    report("S1 설계 문서 추출")
    report("   화면 '로그인'")
    assert seen == ["S1 설계 문서 추출", "   화면 '로그인'"]
    log = (tmp_path / "run.log").read_text(encoding="utf-8").splitlines()
    assert log[0].endswith(" S1 설계 문서 추출") and len(log) == 2


def test_리포트가_내보내기_링크와_인쇄_펼침을_싣는다():
    html = render_html(_report())
    assert "href=\"report.csv\"" in html and "href=\"run.log\"" in html
    assert "beforeprint" in html
