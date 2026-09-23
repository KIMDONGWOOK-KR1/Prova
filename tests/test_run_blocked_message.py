"""실행이 시작되지 않았을 때 화면이 **맞는 이유**를 말하는가.

## 무엇이 문제였나

`POST /api/run` 은 409 를 두 가지 이유로 낸다.

    1. 이미 다른 작업이 돌고 있다        (`runner.submit` → `_submit`)
    2. 대상 웹앱이 안 떠 있거나 낡았다   (`check_sut_build` → blocks)

서버는 둘을 구분해 **무엇을 하면 되는지** 적어 보낸다. 그런데 `app.js` 가 409 를
한 덩어리로 잡아 "이미 실행 중입니다 — 지금 도는 작업이 끝난 뒤 다시 눌러
주세요" 로 덮어쓰고 있었다.

그래서 SUT 를 안 띄운 사람이 **있지도 않은 작업을 기다렸다**(2026-09-23, 웹 UI
점검). 원인을 잘못 짚는 메시지는 없느니만 못하다 — 사람을 엉뚱한 곳으로 보낸다.
`tests/test_ui_messages.py`(2026-09-22)가 같은 모양을 서버 쪽에서 잡았고, 이번엔
그리는 쪽이었다.

## 지키는 것

- 서버는 두 이유를 **다른 문장**으로 낸다. 한쪽 문구가 다른 쪽에 새면 안 된다.
- 화면은 서버 문장을 **그대로** 보인다(`api()` 가 detail 을 `err.message` 로
  옮겨 준다). 화면이 자기 문구로 덮어쓰면 서버가 아무리 정확해도 소용없다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from prova.server import app as server_app
from prova.sut_build import BuildCheck

APP_JS = Path("src/prova/server/static/app.js")
SPEC = "fixtures/specs/login_spec.pdf"


@pytest.fixture
def client():
    return TestClient(server_app.app)


class TestServerSaysWhy:
    def test_대상이_꺼져_있으면_대상_얘기를_한다(self, client, monkeypatch):
        monkeypatch.setattr(
            server_app, "check_sut_build",
            lambda url, **kw: BuildCheck(
                "refused", "대상 URL 에 연결할 수 없습니다 — 웹앱을 먼저 띄웠나요?"))
        res = client.post("/api/run", json={
            "pdf": SPEC, "url": "http://localhost:8199/bad", "backend": "mock",
            "case_ids": ["login-valid-001"],
        })
        assert res.status_code == 409
        assert "띄웠나요" in res.text
        assert "이미 실행 중" not in res.text, (
            "작업 중복과 대상 미기동은 사람이 할 일이 완전히 다르다"
        )


class TestScreenShowsServerMessage:
    """화면이 서버 문장을 덮어쓰지 않는가 — 이 회귀가 실제로 일어났다."""

    def _js(self) -> str:
        return APP_JS.read_text(encoding="utf-8")

    def test_실행_경로가_409_를_한_문구로_덮지_않는다(self):
        js = self._js()
        assert 'showError("이미 실행 중입니다",' not in js, (
            "409 를 한 문구로 덮으면 대상 미기동이 '이미 실행 중' 으로 보인다"
        )

    def test_실행_경로가_서버_메시지를_보인다(self):
        js = self._js()
        assert "실행을 시작하지 않았습니다" in js
        assert "err.message" in js

    def test_계획_경로도_서버_메시지를_보인다(self):
        js = self._js()
        assert 'showError("계획을 만들지 못했습니다", err.message)' in js


class TestStaticNotCached:
    """화면 코드를 고쳤는데 브라우저가 옛 것을 쓰면, 고친 사람이 코드를 의심한다."""

    def test_static_은_캐시하지_않는다(self, client):
        res = client.get("/static/app.js")
        assert res.status_code == 200
        assert res.headers.get("cache-control") == "no-store"

    def test_css_도_마찬가지다(self, client):
        """app.js 만 고치는 것이 아니다 — 스타일도 같은 함정에 걸린다."""
        res = client.get("/static/app.css")
        assert res.headers.get("cache-control") == "no-store"

    def test_runs_에는_걸지_않는다(self, client):
        """실행 산출물은 한 번 쓰이면 바뀌지 않고 스크린샷이 많다 — 캐시가 값을 한다.
        여기까지 끄면 리포트를 열 때마다 이미지를 전부 다시 받는다."""
        from prova.server.app import RUNS

        target = next((p for p in RUNS.glob("*/report.html")), None)
        if target is None:
            pytest.skip("리포트가 없다 — prova run 을 먼저 돌려야 볼 수 있는 경로다")
        rel = target.relative_to(RUNS).as_posix()
        res = client.get(f"/runs/{rel}")
        assert res.status_code == 200
        assert res.headers.get("cache-control") != "no-store"
