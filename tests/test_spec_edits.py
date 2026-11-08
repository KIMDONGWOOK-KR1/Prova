"""사람이 고친 추출 결과로 실행 (계획 화면 '기획서에서 읽은 내용', 2026-11-08).

S1 이 틀리게 읽은 칸을 실행 전에 사람이 고친다. 확인할 것:
    1. 고친 문서로 S2 부터 돈다 — 기획서를 다시 읽으면 고친 것이 사라진다
    2. 무엇을 고쳤는지 원래 추출과 비교해 줄로 남는다 — 판정 근거의 일부가 사람이 적은 값이다
    3. 웹 UI 의 계획·실행이 그 문서를 그대로 쓰고, 리포트가 수정 내역을 보인다
"""

from __future__ import annotations

from prova.llm.mock_backend import MockLLM
from prova.models import ScreenSpec, SpecDocument, UIElement
from prova.pipeline import build_plan
from prova.s6_report.report_builder import render_html
from prova.spec_edits import diff_docs, settle

SPEC = "fixtures/specs/login_spec.pdf"


def _doc(**screen) -> SpecDocument:
    base = dict(screen_id="login", screen_name="로그인", url_path="/login", elements=[
        UIElement(element_id="email", type="input", label="이메일", required=True),
        UIElement(element_id="kind", type="select", label="종류", options=["A", "B"]),
    ])
    base.update(screen)
    return SpecDocument(source="x.pdf", screens=[ScreenSpec(**base)])


class TestDiff:
    def test_같으면_빈_목록(self):
        assert diff_docs(_doc(), _doc()) == []

    def test_라벨_필수_선택항목_경로를_고친_것을_줄로(self):
        edited = _doc(url_path="/signin")
        edited.screens[0].elements[0].label = "전자우편"
        edited.screens[0].elements[0].required = False
        edited.screens[0].elements[1].options = ["A", "C"]
        lines = diff_docs(_doc(), edited)
        assert "[로그인] 경로: '/login' → '/signin'" in lines
        assert "[로그인] '이메일' 라벨: '이메일' → '전자우편'" in lines
        assert "[로그인] '이메일' 필수: 예 → 아니오" in lines
        assert "[로그인] '종류' 선택 항목: [A, B] → [A, C]" in lines

    def test_뺀_요소를_적는다(self):
        edited = _doc()
        edited.screens[0].elements.pop()
        assert diff_docs(_doc(), edited) == ["[로그인] 요소 '종류' 을 뺌"]

    def test_빈_글자와_None_은_같은_것으로_본다(self):
        edited = _doc()
        edited.screens[0].elements[0].placeholder = ""
        assert diff_docs(_doc(), edited) == []


def test_경로를_채우면_경로가_없다는_경고를_지운다():
    from prova.s1_spec_extractor.extractor import NO_PATH_WARNING

    doc = _doc(url_path="/x", warnings=[f"{NO_PATH_WARNING} — …", "다른 경고"])
    assert settle(doc).screens[0].warnings == ["다른 경고"]


def test_고친_문서로_만들면_기획서를_다시_읽지_않고_고친_라벨로_케이스를_만든다(tmp_path):
    llm = MockLLM.with_login_fixtures()
    original, _ = build_plan(SPEC, "http://x", llm, run_dir=tmp_path)
    edited = original.doc.model_copy(deep=True)
    edited.screens[0].element_by_id("email").label = "전자우편"
    calls_before = len(llm.calls)

    state, _ = build_plan(SPEC, "http://x", llm, run_dir=tmp_path, doc=edited)

    assert not any(c["schema_title"] == "ScreenSpec" for c in llm.calls[calls_before:])
    labels = next(c for c in state.all_cases if c.expected.type == "labels_findable")
    assert "전자우편" in labels.expected.labels
    assert "이메일" not in labels.expected.labels
    # 넘긴 문서는 바뀌지 않는다
    assert edited.screens[0].element_by_id("email").label == "전자우편"


def test_리포트가_사람이_고친_값을_보인다():
    from prova.models import TestReport

    r = TestReport(run_id="r", target_url="http://x", summary={
        "total": 0, "pass": 0, "fail": 0, "spec_edits": ["[로그인] '이메일' 라벨: '이메일' → '전자우편'"]})
    html = render_html(r)
    assert "사람이 고친 추출 결과로 실행 — 1건" in html
    assert "전자우편" in html


class TestWebUI:
    """계획 화면 → 고쳐서 다시 만들기 → 실행. SUT 는 conftest 의 sut_base 가 띄운다."""

    def _client(self, monkeypatch, tmp_path):
        from fastapi.testclient import TestClient
        from starlette.routing import Mount

        from prova.server import app as server_app

        runs = tmp_path / "runs"
        runs.mkdir()
        monkeypatch.setattr(server_app, "RUNS", runs)
        static = next(r.app for r in server_app.app.routes
                      if isinstance(r, Mount) and r.name == "runs")
        monkeypatch.setattr(static, "directory", runs)
        monkeypatch.setattr(static, "all_directories", [runs])
        server_app.runner.__init__()
        return TestClient(server_app.app)

    def _job(self, client, res):
        import time

        assert res.status_code == 200, res.text
        job_id = res.json()["job_id"]
        for _ in range(600):
            job = client.get(f"/api/job/{job_id}?since=0").json()
            if job["status"] != "running":
                assert job["status"] == "done", job.get("error")
                return job["result"]
            time.sleep(0.2)
        raise AssertionError("작업이 끝나지 않았습니다")

    def test_고친_성공_조건으로_다시_만들고_실행하면_리포트에_수정이_남는다(
            self, monkeypatch, tmp_path, sut_base):
        client = self._client(monkeypatch, tmp_path)
        body = {"pdf": SPEC, "url": f"{sut_base}/good", "backend": "mock"}
        plan = self._job(client, client.post("/api/plan", json=body))
        assert plan["spec_edits"] == []
        doc = plan["doc"]
        old = doc["screens"][0]["success_condition"]
        doc["screens"][0]["success_condition"] = old.replace("환영합니다", "어서 오세요")

        replan = self._job(client, client.post("/api/plan", json={**body, "doc": doc}))
        assert len(replan["spec_edits"]) == 1
        assert replan["spec_edits"][0].startswith("[로그인] 성공 조건:")
        valid = next(c["case_id"] for c in replan["cases"] if "valid" in c["case_id"])

        out = self._job(client, client.post("/api/run", json={
            **body, "doc": replan["doc"], "case_ids": [valid]}))
        # good 구현은 '환영합니다' 를 보인다 — 사람이 바꾼 문구는 화면에 없으니 FAIL.
        # 고친 문서가 실행까지 그대로 갔다는 증거다.
        assert out["summary"]["fail"] == 1
        assert out["summary"]["spec_edits"] == replan["spec_edits"]

    def test_모양이_틀린_문서는_작업을_띄우기_전에_거절한다(self, monkeypatch, tmp_path):
        client = self._client(monkeypatch, tmp_path)
        res = client.post("/api/plan", json={
            "pdf": SPEC, "url": "http://x", "backend": "mock", "doc": {"screens": "틀림"}})
        assert res.status_code == 400
        assert "고친 추출 결과" in res.text
