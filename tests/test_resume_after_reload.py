"""실행 중에 새로고침해도 진행 화면으로 돌아간다 (서버 runner·/api/state, 웹 UI app.js).

2026-11-27 점검: 실행 중 새로고침하면 첫 화면만 나오고, 다시 누르면 "이미 실행 중이에요" 만 떴다.
작업은 서버에서 끝까지 돌았지만 화면은 그 작업을 다시 찾을 길이 없었다 — 서버는 진행 메시지를
처음부터 다시 읽게 쌓아 두는데(runner.py), 화면이 작업 번호를 잊었다.

- 서버: /api/state 가 지금 도는 작업(job)과 서버 실행 표식(boot)을 알린다. 작업 번호는 서버를
  다시 띄우면 job-1 부터 다시 세므로, boot 가 같을 때만 같은 작업이다.
- 화면: 작업을 시작할 때 그 탭(sessionStorage)에 작업 번호와 계획을 적어 두고, 다시 열리면
  그 작업에 다시 붙는다. 다른 창이 시작한 작업이면 붙지 않고 '진행 중' 만 알린다.
"""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from prova.server import app as server_app
from prova.server.runner import JobRunner

from test_ui_run_progress import base, page  # noqa: F401 — 같은 정적 서버·브라우저를 쓴다


# ── 서버 ─────────────────────────────────────────────────────────────────────

def _until(cond, what):
    for _ in range(200):
        if cond():
            return
        time.sleep(0.01)
    raise AssertionError(what)


def test_도는_작업을_알려_준다():
    r = JobRunner()
    gate = threading.Event()
    job = r.submit("run", lambda report: gate.wait(5))
    assert r.active is job
    gate.set()
    _until(lambda: r.active is None, "작업이 끝나지 않았다")


def test_서버를_다시_띄우면_표식이_바뀐다():
    assert JobRunner().boot and JobRunner().boot != JobRunner().boot


def test_상태가_도는_작업과_표식을_싣는다():
    server_app.runner.__init__()
    client = TestClient(server_app.app)
    idle = client.get("/api/state").json()
    assert idle["job"] is None and idle["boot"] == server_app.runner.boot

    gate = threading.Event()
    job = server_app.runner.submit("run", lambda report: gate.wait(5))
    try:
        busy = client.get("/api/state").json()
        assert busy["busy"] is True
        assert busy["job"] == {"job_id": job.job_id, "kind": "run"}
    finally:
        gate.set()
        _until(lambda: not server_app.runner.busy, "작업이 끝나지 않았다")
    assert client.get("/api/state").json()["job"] is None


# ── 화면 ─────────────────────────────────────────────────────────────────────

PLAN = "{ cases: ['c1', 'c2', 'c3'].map(id => ({ case_id: id, title: id, selected: id !== 'c3' })) }"
OUT = "{ run_id: 'r1', report_url: '/runs/r1/report.html', summary: { total: 2, pass: 2, fail: 0 } }"


@pytest.fixture
def ui(page):  # noqa: F811
    """서버 호출을 흉내로 바꾼다. follow 는 테스트가 풀어 줄 때까지 기다린다."""
    page.evaluate("""() => {
      window.__real = window.__real || { api, follow, showResult, showPlan, loadRuns };
      sessionStorage.clear();
      state.plan = null; state.busy = false; state.boot = 'b1';
      $('formNote').innerHTML = '';
      window.__log = [];
      window.__release = null;
      api = async (path) => { window.__log.push('api ' + path); return { job_id: 'job-7' }; };
      follow = (id, on) => { window.__log.push('follow ' + id);
        return new Promise((ok, no) => { window.__release = { ok, no }; }); };
      showResult = (out) => { window.__log.push('result ' + out.run_id); };
      showPlan = () => { window.__log.push('plan ' + state.plan.cases.length); };
      loadRuns = () => { window.__log.push('runs'); };
    }""")
    yield page
    page.evaluate("""() => {
      ({ api, follow, showResult, showPlan, loadRuns } = window.__real);
      sessionStorage.clear(); state.busy = false; state.plan = null;
    }""")


def _snap(ui, boot="b1", kind="run"):
    ui.evaluate(f"""([boot, kind]) => sessionStorage.setItem(JOB_KEY, JSON.stringify(
      {{ boot, kind, job_id: 'job-7', started: Date.now() - 5000, plan: {PLAN} }}))""", [boot, kind])


def test_실행을_시작하면_그_탭에_작업을_적어_둔다(ui):
    ui.evaluate(f"() => {{ state.plan = {PLAN}; startRun(); }}")
    ui.wait_for_function("window.__release !== null")
    snap = ui.evaluate("() => JSON.parse(sessionStorage.getItem(JOB_KEY))")
    assert (snap["boot"], snap["kind"], snap["job_id"]) == ("b1", "run", "job-7")
    assert [c["case_id"] for c in snap["plan"]["cases"]] == ["c1", "c2", "c3"]


def test_실행이_끝나면_적어_둔_것을_지운다(ui):
    ui.evaluate(f"() => {{ state.plan = {PLAN}; window.__done = startRun(); }}")
    ui.wait_for_function("window.__release !== null")
    ui.evaluate(f"async () => {{ window.__release.ok({OUT}); await window.__done; }}")
    assert ui.evaluate("() => sessionStorage.getItem(JOB_KEY)") is None
    assert "result r1" in ui.evaluate("() => window.__log")


def test_새로고침_뒤_내_작업이면_진행_화면으로_돌아간다(ui):
    _snap(ui)
    kind = ui.evaluate("""() => {
      window.__kind = null;
      resumeJob({ boot: 'b1', busy: true, job: { job_id: 'job-7', kind: 'run' } }).then(k => { window.__kind = k; });
    }""")
    ui.wait_for_function("window.__release !== null")
    assert ui.evaluate("() => window.__log") == ["follow job-7"]
    assert ui.evaluate("() => state.busy") is True
    assert ui.evaluate("() => state.plan.cases.length") == 3
    assert ui.evaluate("() => document.querySelectorAll('#pCases tr').length") == 2  # 고른 것만 깐다
    assert ui.evaluate("() => $('pStop') && !$('pStop').hidden") is True

    ui.evaluate(f"async () => {{ window.__release.ok({OUT}); await new Promise(r => setTimeout(r, 50)); }}")
    assert ui.evaluate("() => window.__kind") == "mine"
    assert "result r1" in ui.evaluate("() => window.__log")
    assert ui.evaluate("() => state.busy") is False


def test_새로고침하는_사이_끝났어도_결과를_보인다(ui):
    """상태에는 도는 작업이 없지만 적어 둔 작업은 서버에 남아 있다 — 끝난 결과를 바로 받는다."""
    _snap(ui)
    ui.evaluate("() => { window.__p = resumeJob({ boot: 'b1', busy: false, job: null }); }")
    ui.wait_for_function("window.__release !== null")
    ui.evaluate(f"async () => {{ window.__release.ok({OUT}); await window.__p; }}")
    assert "result r1" in ui.evaluate("() => window.__log")
    assert ui.evaluate("() => sessionStorage.getItem(JOB_KEY)") is None


def test_기획서를_읽는_중이었으면_항목_검토로_이어진다(ui):
    _snap(ui, kind="plan")
    ui.evaluate("() => { window.__p = resumeJob({ boot: 'b1', busy: true, job: { job_id: 'job-7', kind: 'plan' } }); }")
    ui.wait_for_function("window.__release !== null")
    ui.evaluate(f"async () => {{ window.__release.ok({PLAN}); await window.__p; }}")
    assert "plan 3" in ui.evaluate("() => window.__log")


def test_서버가_다시_떴으면_옛_작업_번호에_붙지_않는다(ui):
    """작업 번호는 서버를 띄울 때마다 job-1 부터 다시 센다 — 번호만 같은 남의 작업일 수 있다."""
    _snap(ui, boot="old")
    ui.evaluate("""() => {
      resumeJob({ boot: 'b1', busy: true, job: { job_id: 'job-7', kind: 'run' } }).then(k => { window.__kind = k; });
    }""")
    ui.wait_for_function("window.__release !== null")
    assert ui.evaluate("() => state.plan") is None
    assert ui.evaluate("() => sessionStorage.getItem(JOB_KEY)") is None
    assert "다른 창" in ui.evaluate("() => $('formNote').innerText")


def test_다른_창의_작업은_알리기만_하고_끝나면_잠금을_푼다(ui):
    ui.evaluate("""() => {
      window.__p = resumeJob({ boot: 'b1', busy: true, job: { job_id: 'job-9', kind: 'run' } });
    }""")
    ui.wait_for_function("window.__release !== null")
    assert "다른 창" in ui.evaluate("() => $('formNote').innerText")
    assert ui.evaluate("() => state.busy") is True
    assert ui.evaluate("() => $('planBtn').disabled") is True

    kind = ui.evaluate("async () => { window.__release.no(new Error('실패')); return await window.__p; }")
    assert kind == "other"
    assert ui.evaluate("() => state.busy") is False
    assert ui.evaluate("() => $('formNote').innerText") == ""
    assert "runs" in ui.evaluate("() => window.__log")
    assert not any(line.startswith("result") for line in ui.evaluate("() => window.__log"))


def test_도는_작업이_없으면_아무것도_하지_않는다(ui):
    assert ui.evaluate("() => resumeJob({ boot: 'b1', busy: false, job: null })") == "none"
    assert ui.evaluate("() => window.__log") == []
    assert ui.evaluate("() => state.busy") is False


def test_다시_붙은_화면은_지난_항목의_걸린_시간을_지어내지_않는다(ui):
    """지난 메시지는 한 묶음으로 온다 — 항목마다 '0.0초' 가 찍히고 '0:01 지남 · 곧 끝나요' 가 떴다."""
    _snap(ui)
    ui.evaluate("""() => {
      follow = (id, on) => new Promise((ok) => { window.__release = { ok, on }; });
      resumeJob({ boot: 'b1', busy: true, job: { job_id: 'job-7', kind: 'run' } });
    }""")
    ui.wait_for_function("window.__release !== null")
    ui.evaluate("""() => window.__release.on([
      '  케이스 1/2 · c1', '집계 통과 1 · 기획서와 다름 0 · 실행 문제 0', '  케이스 2/2 · c2'])""")
    times = ui.evaluate("() => [...document.querySelectorAll('#pCases tr')].map(r => r.querySelector('.t').textContent)")
    assert times == ["", "진행 중"]
    assert ui.evaluate("() => Date.now() - runClock.start") >= 5000   # 적어 둔 시작 시각(5초 전)부터 센다
    assert ui.evaluate("() => Date.now() - runClock.first") >= 5000

    ui.evaluate("() => window.__release.on(['집계 통과 2 · 기획서와 다름 0 · 실행 문제 0'])")
    last = ui.evaluate("() => document.querySelector('#pCases tr:nth-child(2) .t').textContent")
    assert last.endswith("초")   # 다시 붙은 뒤에 끝난 항목은 잰 시간을 적는다
