"""제목 다듬기 분리 — 제목을 기다리느라 실행을 늦추지 않는다.

제목은 판정 근거가 아니고, 계획 시간의 35~43% 를 쓴다(2026-11-02 실측). 뒤에서 돌리고
결과는 한 지점(finish_titles)에서만 반영한다. 실행 도중에 제목이 바뀌면 같은 케이스가
로그와 리포트에서 다른 이름이 된다.
"""

from __future__ import annotations

import threading

from prova.llm.base import LLMError
from prova.llm.mock_backend import MockLLM
from prova.models import Verdict
from prova.nodes import AgentState, extract_spec, finish_titles, generate_test_cases
from prova.pipeline import plan_pipeline, run_pipeline

PDF = "fixtures/specs/login_spec.pdf"


class SlowTitles:
    """제목 호출만 release 가 열릴 때까지 붙든다."""

    name = "slow"

    def __init__(self, reply=None, error=None):
        self.inner = MockLLM.for_document(PDF)
        self.release = threading.Event()
        self.reply, self.error = reply, error

    def complete_json(self, *, system, user, schema, **kw):
        if schema.get("title") != "CaseTitles":
            return self.inner.complete_json(system=system, user=user, schema=schema, **kw)
        assert self.release.wait(20)
        if self.error:
            raise self.error
        return self.reply


def _planned(llm) -> AgentState:
    state = AgentState(pdf_path=PDF, base_url="http://x", run_id="r", run_dir="runs/r", llm=llm)
    return generate_test_cases(extract_spec(state))


def test_제목을_기다리지_않고_케이스를_돌려준다():
    llm = SlowTitles(reply={"titles": []})
    state = _planned(llm)  # 붙든 채로 돌아와야 한다
    assert state.cases
    llm.release.set()
    finish_titles(state)


def test_다듬은_제목은_마칠_때_한꺼번에_반영한다():
    llm = SlowTitles()
    state = _planned(llm)
    first = state.cases[0]
    rule_title = first.title
    llm.reply = {"titles": [{"case_id": first.case_id, "title": "다듬은 제목"}]}
    state.verdicts = [Verdict(case_id=first.case_id, title=rule_title, type=first.type,
                              verdict="PASS")]
    llm.release.set()
    assert first.title == rule_title  # 마치기 전에는 그대로
    finish_titles(state)
    assert first.title == "다듬은 제목"
    assert state.verdicts[0].title == "다듬은 제목"


def test_제외_목록의_제목도_바꾼다():
    llm = SlowTitles()
    state = _planned(llm)
    from prova.models import CaseSelection

    cid = state.cases[0].case_id
    state.selection = CaseSelection(excluded=[cid], excluded_titles={cid: "옛"})
    llm.reply = {"titles": [{"case_id": cid, "title": "새 제목"}]}
    llm.release.set()
    finish_titles(state)
    assert state.selection.excluded_titles[cid] == "새 제목"


def test_실패해도_멈추지_않고_경고로_남긴다():
    llm = SlowTitles(error=LLMError("꺼짐"))
    state = _planned(llm)
    titles = [c.title for c in state.cases]
    llm.release.set()
    finish_titles(state)
    assert [c.title for c in state.cases] == titles
    assert any("제목 다듬기" in w for w in state.doc.all_warnings)


def test_예상_못_한_오류도_경고로_남긴다():
    llm = SlowTitles(error=KeyError("x"))
    state = _planned(llm)
    llm.release.set()
    finish_titles(state)
    assert any("제목 다듬기" in w for w in state.doc.all_warnings)


def test_두_번_불러도_된다():
    llm = SlowTitles(reply={"titles": []})
    state = _planned(llm)
    llm.release.set()
    finish_titles(state)
    finish_titles(state)


def test_LLM_없이는_아무것도_하지_않는다():
    finish_titles(AgentState(pdf_path=PDF, base_url="x", run_id="r", run_dir="runs/r"))


def test_리포트에_다듬은_제목이_실린다(sut_base, tmp_path):
    llm = SlowTitles()
    llm.reply = {"titles": [{"case_id": "login-valid-001", "title": "다듬은 제목"}]}
    llm.release.set()
    report, _ = run_pipeline(PDF, f"{sut_base}/good", llm, run_id="r", runs_root=tmp_path,
                             only="login-valid")
    assert report.cases[0].title == "다듬은 제목"


def test_저장한_계획에_다듬은_제목이_실린다(tmp_path):
    from prova.plan_store import load_plan

    llm = SlowTitles()
    llm.reply = {"titles": [{"case_id": "login-valid-001", "title": "다듬은 제목"}]}
    llm.release.set()
    _, path = plan_pipeline(PDF, "http://x", llm, run_id="p", runs_root=tmp_path)
    plan = load_plan(path.parent)
    assert next(c for c in plan.all_cases if c.case_id == "login-valid-001").title == "다듬은 제목"
