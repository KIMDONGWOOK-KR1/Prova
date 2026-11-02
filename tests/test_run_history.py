"""실행 이력 — 같은 기획서·같은 대상을 몇 차로 돌렸고 직전과 무엇이 달라졌는가.

외주 결과물을 차수마다 검사하는 기획자가 묻는 말은 '이번에 몇 % 인가' 보다 '지난번보다
새로 깨진 것과 고쳐진 것이 무엇인가' 다.
"""

from __future__ import annotations

import json
from pathlib import Path

from prova.history import attach_history, list_runs
from prova.models import TestReport, Verdict


def _report(run_id: str, verdicts: dict[str, str], spec="fixtures/specs/login_spec.pdf",
            target="http://x/good", created="2026-11-02T10:00:00+09:00",
            project="", backend="vllm:m") -> TestReport:
    cases = [Verdict(case_id=c, title=f"제목 {c}", type="positive", verdict=v,
                     failure_category=None if v == "PASS" else "assertion_mismatch")
             for c, v in verdicts.items()]
    s = TestReport.summarize(cases)
    s["llm_backend"] = backend
    if project:
        s["project"] = project
    return TestReport(run_id=run_id, target_url=target, spec_source=spec, summary=s,
                      cases=cases, created_at=created)


def _save(root: Path, report: TestReport) -> None:
    d = root / report.run_id
    d.mkdir(parents=True)
    (d / "report.json").write_text(json.dumps(report.model_dump(), ensure_ascii=False),
                                   encoding="utf-8")


def test_처음_실행은_1차고_비교_대상이_없다(tmp_path):
    r = _report("a", {"c1": "PASS"})
    attach_history(r, tmp_path)
    assert r.summary["history"]["round"] == 1
    assert r.summary["history"]["previous_run"] is None


def test_직전_실행과_비교해_새로_깨진_것과_고쳐진_것을_센다(tmp_path):
    _save(tmp_path, _report("a", {"c1": "PASS", "c2": "FAIL", "c3": "PASS"}))
    r = _report("b", {"c1": "FAIL", "c2": "PASS", "c3": "PASS"},
                created="2026-11-02T11:00:00+09:00")
    attach_history(r, tmp_path)
    h = r.summary["history"]
    assert (h["round"], h["previous_run"]) == (2, "a")
    assert h["regressed"] == ["제목 c1"]
    assert h["fixed"] == ["제목 c2"]


def test_가장_최근_실행과_비교한다(tmp_path):
    _save(tmp_path, _report("new", {"c": "PASS"}, created="2026-11-02T10:00:00+09:00"))
    _save(tmp_path, _report("old", {"c": "FAIL"}, created="2026-11-01T10:00:00+09:00"))
    r = _report("z", {"c": "PASS"}, created="2026-11-02T11:00:00+09:00")
    attach_history(r, tmp_path)
    assert r.summary["history"]["previous_run"] == "new"
    assert r.summary["history"]["fixed"] == []


def test_대상이_다르면_차수를_잇지_않는다(tmp_path):
    _save(tmp_path, _report("a", {"c": "PASS"}, target="http://x/bad"))
    r = _report("b", {"c": "PASS"}, target="http://x/good")
    attach_history(r, tmp_path)
    assert r.summary["history"]["round"] == 1


def test_mock_실행과_실제_모델_실행은_비교하지_않는다(tmp_path):
    _save(tmp_path, _report("a", {"c": "FAIL"}, backend="mock"))
    r = _report("b", {"c": "PASS"}, backend="vllm:m")
    attach_history(r, tmp_path)
    assert r.summary["history"]["previous_run"] is None


def test_프로젝트가_다르면_따로_센다(tmp_path):
    _save(tmp_path, _report("a", {"c": "PASS"}, project="A사"))
    r = _report("b", {"c": "PASS"}, project="B사")
    attach_history(r, tmp_path)
    assert r.summary["history"]["round"] == 1


def test_같은_이름으로_다시_돌리면_자기_자신과_비교하지_않는다(tmp_path):
    _save(tmp_path, _report("a", {"c": "FAIL"}))
    r = _report("a", {"c": "PASS"}, created="2026-11-02T11:00:00+09:00")
    attach_history(r, tmp_path)
    assert r.summary["history"]["previous_run"] is None


def test_양쪽에_다_있는_케이스만_비교하고_나머지는_수로_말한다(tmp_path):
    _save(tmp_path, _report("a", {"c1": "PASS", "gone": "PASS"}))
    r = _report("b", {"c1": "PASS", "added": "FAIL"}, created="2026-11-02T11:00:00+09:00")
    attach_history(r, tmp_path)
    h = r.summary["history"]
    assert h["regressed"] == [] and h["fixed"] == []
    assert (h["added"], h["removed"]) == (1, 1)


def test_깨진_report_json_은_건너뛴다(tmp_path):
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "report.json").write_text("{", encoding="utf-8")
    _save(tmp_path, _report("a", {"c": "PASS"}))
    assert [r["run_id"] for r in list_runs(tmp_path)] == ["a"]


def test_리포트가_비교_결과를_보여_준다(tmp_path):
    from prova.s6_report.report_builder import render_html

    _save(tmp_path, _report("a", {"c1": "PASS", "c2": "FAIL"}))
    r = _report("b", {"c1": "FAIL", "c2": "PASS"}, created="2026-11-02T11:00:00+09:00")
    attach_history(r, tmp_path)
    html = render_html(r)
    assert "2차" in html and "새로 실패" in html and "제목 c1" in html and "해결" in html


def test_파이프라인이_이력과_실행_로그를_남긴다(sut_base, tmp_path):
    from prova.llm.mock_backend import MockLLM
    from prova.pipeline import run_pipeline

    pdf = "fixtures/specs/login_spec.pdf"
    for rid in ("r1", "r2"):
        report, run_dir = run_pipeline(pdf, f"{sut_base}/good", MockLLM.for_document(pdf),
                                       run_id=rid, runs_root=tmp_path, only="login-valid",
                                       project="1차 납품")
    assert report.summary["history"]["round"] == 2
    assert report.summary["project"] == "1차 납품"
    log = (run_dir / "run.log").read_text(encoding="utf-8")
    assert "S1 설계 문서 추출" in log and "S6 리포트 생성" in log


def test_프로젝트를_적으면_대상_주소가_바뀌어도_차수를_잇는다(tmp_path):
    # 납품 차수마다 스테이징 주소가 바뀌는 것이 보통이다
    _save(tmp_path, _report("a", {"c": "PASS"}, target="http://x/v1", project="A사"))
    r = _report("b", {"c": "PASS"}, target="http://x/v2", project="A사",
                created="2026-11-02T11:00:00+09:00")
    attach_history(r, tmp_path)
    assert r.summary["history"]["round"] == 2


def test_일부만_돌린_실행과_비교하면_그렇다고_표시한다(tmp_path):
    partial = _report("a", {"c1": "PASS"})
    partial.summary["filtered_by"] = "c1"
    _save(tmp_path, partial)
    r = _report("b", {"c1": "PASS", "c2": "PASS"}, created="2026-11-02T11:00:00+09:00")
    attach_history(r, tmp_path)
    assert r.summary["history"]["partial"] is True
    assert "일부만 실행" in __import__("prova.s6_report.report_builder", fromlist=["x"]).render_html(r)


def test_실행이_도중에_실패해도_로그에_이유가_남는다(tmp_path):
    from prova.llm.mock_backend import MockLLM
    from prova.pipeline import run_pipeline
    import pytest

    pdf = "fixtures/specs/login_spec.pdf"
    with pytest.raises(ValueError):
        run_pipeline(pdf, "http://127.0.0.1:1/x", MockLLM.for_document(pdf), run_id="f",
                     runs_root=tmp_path, only="없는케이스")
    assert "없는케이스" in (tmp_path / "f" / "run.log").read_text(encoding="utf-8")


def test_같은_이름으로_다시_돌리면_로그를_새로_쓴다(sut_base, tmp_path):
    from prova.llm.mock_backend import MockLLM
    from prova.pipeline import run_pipeline

    pdf = "fixtures/specs/login_spec.pdf"
    for _ in range(2):
        _, run_dir = run_pipeline(pdf, f"{sut_base}/good", MockLLM.for_document(pdf),
                                  run_id="same", runs_root=tmp_path, only="login-valid")
    assert (run_dir / "run.log").read_text(encoding="utf-8").count("S6 리포트 생성") == 1
