"""웹 UI 에서 2차 경로(VLM)를 켤 수 있는가 — 그리고 켰다고 착각하지 않는가.

## 무엇이 없었나

CLI 는 `--vlm URL` 로 2차 경로를 켠다. 웹 UI 에는 그 길이 없었다.
`configs/default.yaml` 의 `vlm_confidence_threshold` 주석이 그 사실을 적어 두고
있었다 — "웹 UI(prova serve)는 아직 VLM 을 붙이지 않아 이 값을 읽어도 아무 일도
하지 않는다".

그래서 화면으로는 자가치유(계획서 2차 목표 5번)를 보여 줄 수 없었다. 산출물 6번이
"QA Agent 웹 데모" 인데 데모에서 빠지는 기능이 있는 셈이다.

## 지키는 선

1. **비우면 끄는 것이 기본.** 1차 경로만으로 돈다. 못 찾은 요소는 탐지 실패로
   남고, 없는 결함으로 보고되지 않는다.
2. **연결이 안 되면 실행하지 않는다.** 조용히 보정 없이 진행하면 '2차 경로를
   켰다' 고 믿는 실행이 실제로는 그냥 1차 경로다. 그 결과를 보고 "2차가 필요
   없다" 는 반대 결론까지 낼 수 있다. CLI 가 같은 이유로 멈춘다.
3. **켠 사실을 진행 로그에 남긴다.** 보정이 한 건도 없었던 실행은 켠 것과 끈 것이
   리포트에서 똑같아 보인다. 무엇을 켜고 돌렸는지는 판정의 전제다.
4. **계획 단계는 받지 않는다.** 계획은 브라우저를 열지 않으므로 요소를 찾을 일이
   없다. 읽지 않는 값을 받으면 화면이 거짓 약속을 한다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from prova.server import app as server_app

SPEC = "fixtures/specs/login_spec.pdf"


@pytest.fixture
def client():
    return TestClient(server_app.app)


@pytest.fixture
def captured(monkeypatch):
    """run_pipeline 을 가로채 넘어온 인자만 기록한다. 브라우저를 열지 않는다."""
    seen = {}

    def fake_run_pipeline(**kw):
        seen.update(kw)

        class _R:
            summary = {"total": 0, "pass": 0, "fail": 0}
        return _R(), "runs/fake"

    monkeypatch.setattr(server_app, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(server_app, "check_sut_build",
                        lambda url, **kw: _ok_build())
    return seen


def _ok_build():
    from prova.sut_build import BuildCheck
    return BuildCheck("match", "일치")


def _run(client, **extra):
    body = {"pdf": SPEC, "url": "http://localhost:8100/bad", "backend": "mock",
            "case_ids": ["login-valid-001"]}
    body.update(extra)
    return client.post("/api/run", json=body)


def _finish(client, res):
    """작업이 끝날 때까지 따라가 최종 상태를 돌려준다."""
    import time
    job_id = res.json()["job_id"]
    for _ in range(200):
        job = client.get(f"/api/job/{job_id}?since=0").json()
        if job["status"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("작업이 끝나지 않았다")


class TestOffByDefault:
    def test_비우면_2차_경로를_쓰지_않는다(self, client, captured):
        res = _run(client)
        assert res.status_code == 200
        job = _finish(client, res)
        assert job["status"] == "done", job.get("error")
        assert captured["vlm"] is None

    def test_계획_요청은_vlm_을_받지_않는다(self):
        """읽지 않는 값을 받으면 화면이 거짓 약속을 한다."""
        assert "vlm" not in server_app.PlanRequest.model_fields
        assert "vlm" in server_app.RunRequest.model_fields


class TestPassThrough:
    def test_주소를_주면_클라이언트가_넘어간다(self, client, captured, monkeypatch):
        made = {}

        class _FakeVLM:
            name, model = "fake-vlm", "fake-model"

            def health(self):
                made["health"] = True

        monkeypatch.setattr("prova.vlm.qwen_vl.QwenVLClient",
                            lambda **kw: (made.update(kw) or _FakeVLM()))
        res = _run(client, vlm="http://localhost:8001/v1")
        job = _finish(client, res)
        assert job["status"] == "done", job.get("error")
        assert made.get("health") is True, "연결을 확인하지 않고 넘기면 안 된다"
        assert captured["vlm"] is not None

    def test_켠_사실을_진행_로그에_남긴다(self, client, captured, monkeypatch):
        class _FakeVLM:
            name, model = "fake-vlm", "fake-model"

            def health(self):
                pass

        monkeypatch.setattr("prova.vlm.qwen_vl.QwenVLClient", lambda **kw: _FakeVLM())
        res = _run(client, vlm="http://localhost:8001/v1")
        job = _finish(client, res)
        joined = "\n".join(job["messages"])
        assert "2차 경로" in joined and "localhost:8001" in joined


class TestFailsLoudly:
    def test_연결이_안_되면_실행하지_않는다(self, client, captured, monkeypatch):
        from prova.vlm.base import VLMError

        class _Dead:
            name, model = "x", "y"

            def health(self):
                raise VLMError("연결 거부")

        monkeypatch.setattr("prova.vlm.qwen_vl.QwenVLClient", lambda **kw: _Dead())
        res = _run(client, vlm="http://localhost:8001/v1")
        job = _finish(client, res)
        assert job["status"] == "error"
        assert "vlm" not in captured, "연결 실패인데 파이프라인이 돌았다"

    def test_사유에_주소와_다음_행동이_있다(self, client, captured, monkeypatch):
        from prova.vlm.base import VLMError

        class _Dead:
            name, model = "x", "y"

            def health(self):
                raise VLMError("연결 거부")

        monkeypatch.setattr("prova.vlm.qwen_vl.QwenVLClient", lambda **kw: _Dead())
        job = _finish(client, _run(client, vlm="http://localhost:8001/v1"))
        assert "localhost:8001" in job["error"]
        assert "비우면" in job["error"], "끄고 돌리는 길을 알려 줘야 한다"
