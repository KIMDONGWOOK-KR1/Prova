"""리포트를 PDF 로 받는다 (2026-11-19) — 기획자용·고치는 사람용 둘 다.

브라우저(Chromium)가 없는 환경에서는 건너뛴다.
"""

from __future__ import annotations

import pytest

from prova.models import StepResult, TestReport, Verdict
from prova.s6_report.planner_view import save_planner_html
from prova.s6_report.report_builder import save_html


def _report() -> TestReport:
    cases = [
        Verdict(case_id=f"{s}-valid-001", title="열림", plain="화면이 열린다", screen_id=s,
                verdict="PASS", evidence={"actual": "확인됨"},
                step_results=[StepResult(seq=1, action="navigate", target="/")])
        for s in ("main", "contact")]
    return TestReport(run_id="ui-20261119-000000", target_url="https://example.test",
                      spec_source="spec.pdf", cases=cases, created_at="2026-11-19T10:00:00+09:00",
                      summary={**TestReport.summarize(cases),
                               "screen_names": {"main": "메인화면", "contact": "CONTACT"}})


def _save_pdf(html, pdf):
    from prova.s6_report.pdf_export import save_pdf
    try:
        return save_pdf(html, pdf)
    except Exception as e:  # 브라우저가 설치되지 않은 환경
        pytest.skip(f"Chromium 을 띄우지 못했습니다: {e}")


def test_두_리포트를_PDF로_저장한다(tmp_path):
    report = _report()
    for html in (save_planner_html(report, tmp_path), save_html(report, tmp_path)):
        pdf = _save_pdf(html, html.with_suffix(".pdf"))
        data = pdf.read_bytes()
        assert data[:5] == b"%PDF-" and len(data) > 5000


def test_서버가_PDF를_내려준다(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from prova.s6_report.report_builder import save_json
    from prova.server import app as server

    run_dir = tmp_path / "ui-20261119-000000"
    report = _report()
    save_json(report, run_dir)
    save_html(report, run_dir)
    monkeypatch.setattr(server, "RUNS", tmp_path)
    made = []
    import prova.s6_report.pdf_export as pdf_export
    monkeypatch.setattr(pdf_export, "save_pdf",
                        lambda html, pdf: (made.append(html.name), pdf.write_bytes(b"%PDF-1.7 x"), pdf)[2])
    client = TestClient(server.app)

    # 기획자용 — 이 기능 전의 실행(planner.html 없음)이면 그 자리에서 만든다.
    r = client.get(f"/api/report/{run_dir.name}/pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert (run_dir / "planner.html").exists() and (run_dir / "planner.pdf").exists()
    r = client.get(f"/api/report/{run_dir.name}/pdf?view=dev")
    assert r.status_code == 200 and (run_dir / "report.pdf").exists()
    # 두 번째부터는 만들어 둔 것을 준다.
    client.get(f"/api/report/{run_dir.name}/pdf")
    assert made == ["planner.html", "report.html"]

    assert client.get(f"/api/report/{run_dir.name}/pdf?view=x").status_code == 400
    assert client.get("/api/report/없는실행/pdf").status_code == 404
    assert client.get("/api/report/../pdf").status_code == 404

    # 결과 화면이 여는 주소.
    r = client.get(f"/api/report/{run_dir.name}/planner", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"].endswith("/planner.html")
