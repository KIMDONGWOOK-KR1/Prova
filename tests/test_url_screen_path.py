"""대상 URL 에 화면 경로까지 넣어도 돈다 — 떼고, 뗀 사실을 남긴다.

## 왜 (2026-09-23 실제로 일어났다)

웹 UI 에 대상 URL 을 `http://localhost:8100/bad/login` 으로 넣고 상품등록 기획서를
돌렸다. 도구는 기획서의 화면 경로 `/login` 을 뒤에 붙이므로 `/bad/login/login` 을
열어 404 가 났고, 케이스 20개가 전부 첫 스텝에서 멈췄다. 사람이 흔히 하는
실수다 — 브라우저 주소창에 보이는 주소를 그대로 복사하면 이렇게 된다.

사용자 결정으로 **자동으로 뗀다.** 다만 조용히 바꾸지 않는다: 진행 로그와
리포트 머리말에 무엇을 뗐는지 남는다. 대상 URL 은 판정의 전제이므로, 바뀐
사실이 안 보이면 리포트를 읽는 사람은 자기가 넣은 주소로 잰 줄 안다.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline, strip_screen_path


def _doc(*paths):
    return SimpleNamespace(screens=[SimpleNamespace(url_path=p) for p in paths])


@pytest.mark.parametrize("given,paths,expected,removed", [
    ("http://h:8100/bad/login", ["/login"], "http://h:8100/bad", "/login"),
    ("http://h:8100/bad/login/", ["/login"], "http://h:8100/bad", "/login"),
    ("http://h:8100/bad/product", ["/login", "/product"], "http://h:8100/bad", "/product"),
    # 화면 경로가 여러 단이면 긴 쪽이 이긴다
    ("http://h/app/orders/list", ["/list", "/orders/list"], "http://h/app", "/orders/list"),
    # 떼지 않는 경우: 이미 올바르다 / 단어 중간 일치 / 루트 경로
    ("http://h:8100/bad", ["/login"], "http://h:8100/bad", None),
    ("http://h:8100/bad/mylogin", ["/login"], "http://h:8100/bad/mylogin", None),
    ("http://h:8100/", ["/"], "http://h:8100/", None),
])
def test_떼는_규칙(given, paths, expected, removed):
    assert strip_screen_path(given, _doc(*paths)) == (expected, removed)


def test_화면_경로가_붙은_URL_로도_판정이_같고_리포트가_그_사실을_말한다(sut_base, tmp_path):
    lines: list[str] = []
    report, run_dir = run_pipeline(
        pdf_path="fixtures/specs/login_spec.pdf",
        base_url=f"{sut_base}/bad/login",
        llm=MockLLM.with_login_fixtures(),
        run_id="urlfix", runs_root=tmp_path, on_progress=lines.append,
    )
    # /bad 로 넣었을 때와 같다 — 4 통과 / 6 실패
    assert (report.summary["pass"], report.summary["fail"]) == (4, 6)
    assert report.target_url == f"{sut_base}/bad"
    assert any("'/login'" in l and "뗐습니다" in l for l in lines)
    html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert "뗐습니다" in html


def test_계획_화면도_그_사실을_받는다(sut_base):
    from fastapi.testclient import TestClient
    from prova.server.app import app

    import time
    client = TestClient(app)
    res = client.post("/api/plan", json={
        "pdf": "fixtures/specs/login_spec.pdf", "url": f"{sut_base}/bad/login",
        "backend": "mock"})
    assert res.status_code == 200, res.text
    job = res.json()["job_id"]
    for _ in range(200):
        body = client.get(f"/api/job/{job}").json()
        if body["status"] != "running":
            break
        time.sleep(0.05)
    assert body["status"] == "done", body
    assert "'/login'" in body["result"]["url_note"]
