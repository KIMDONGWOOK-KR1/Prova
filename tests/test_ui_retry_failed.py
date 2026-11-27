"""'통과 못 한 N건만 다시 실행' 은 그 실행 한 번만 실패분을 고른다 (웹 UI app.js, 실제 브라우저).

2026-11-27: retryFailed 가 항목 선택을 실패분으로 덮어쓰고 되돌리지 않았다. 이어서 결과 화면의
'다시 실행' 을 누르면 전체가 아니라 실패분만 돌았고, 검토 화면에 돌아가면 나머지 체크가 풀려
있었다. 안내도 없었다. 다시 돌린 뒤에는 사용자가 골라 둔 선택 그대로여야 한다.
"""

from __future__ import annotations

from test_ui_run_progress import base, page  # noqa: F401 — 같은 정적 서버·브라우저를 쓴다


def _setup(page, selected):
    page.evaluate(
        """(sel) => {
      state.plan = { cases: ['c1', 'c2', 'c3'].map(id => ({ case_id: id, title: id, selected: sel[id] })) };
      state.report = { cases: [
        { case_id: 'c1', verdict: 'PASS' }, { case_id: 'c2', verdict: 'FAIL' }, { case_id: 'c3', verdict: 'PASS' },
      ] };
      window.__ran = null;
      window.__realStartRun = window.__realStartRun || startRun;
      startRun = async () => { window.__ran = picked(); };
    }""",
        selected,
    )


def _selected(page):
    return page.evaluate("() => state.plan.cases.filter(c => c.selected).map(c => c.case_id)")


def test_다시_실행은_실패분만_보낸다(page):  # noqa: F811
    _setup(page, {"c1": True, "c2": True, "c3": True})
    page.evaluate("() => retryFailed()")
    assert page.evaluate("() => window.__ran") == ["c2"]


def test_다시_실행한_뒤에는_원래_선택으로_돌아온다(page):  # noqa: F811
    _setup(page, {"c1": True, "c2": True, "c3": True})
    page.evaluate("() => retryFailed()")
    assert _selected(page) == ["c1", "c2", "c3"]


def test_사용자가_뺀_항목은_뺀_채로_돌아온다(page):  # noqa: F811
    _setup(page, {"c1": True, "c2": True, "c3": False})
    page.evaluate("() => retryFailed()")
    assert _selected(page) == ["c1", "c2"]


def test_실행이_실패해도_선택은_돌아온다(page):  # noqa: F811
    _setup(page, {"c1": True, "c2": True, "c3": True})
    page.evaluate("() => { startRun = async () => { window.__ran = picked(); throw new Error('x'); }; }")
    page.evaluate("() => retryFailed().catch(() => {})")
    assert _selected(page) == ["c1", "c2", "c3"]
