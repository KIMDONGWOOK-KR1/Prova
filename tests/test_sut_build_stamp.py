"""SUT 빌드 도장 — 떠 있는 프로세스가 자기 소스보다 낡았는지 스스로 답한다.

## 왜 이게 있는가

`--reload` 는 프로세스를 **둘**로 만든다. 부모(감시자)가 파일을 보고, 자식
(일꾼)이 응답한다. 부모가 죽어도 자식은 소켓을 물고 계속 산다 — **포트는
열려 있고 응답도 정상인데 아무도 파일을 보지 않는다.**

2026-08-27 에 실제로 그랬다. 8100 의 감시자 PID 는 사라졌는데 일꾼은
18:32 의 코드를 서빙하고 있었고, 그 스냅샷은 상태 select 는 있고 필터
배선은 없는 **반쯤 새것**이었다. 그래서 화면만 보고는 '업데이트됐구나' 로
읽혔다. 재시작을 잊은 것보다 나쁘다 — `--reload` 를 붙여 뒀으니 안심한다.

## 왜 비교를 SUT 쪽에서 하는가

prova 는 대상의 **URL 만** 안다. 소스가 어느 경로에 있는지, 같은 기계에
있기는 한지 모른다. 그러니 '내 소스가 나보다 새것인가' 는 그 프로세스만
답할 수 있다. prova 는 답을 읽을 뿐이다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import sut.app as sut_app
from sut.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


class TestEndpoint:
    def test_갓_임포트한_앱은_자기_소스와_일치한다(self, client):
        r = client.get("/__build__")
        assert r.status_code == 200
        body = r.json()
        assert body["stale"] is False
        assert body["stamp"] == body["current"]

    def test_실제_트리를_걸었다(self, client):
        """파일 수가 0이면 아무것도 안 걸고 늘 '일치' 라 답하는 것과 같다."""
        assert client.get("/__build__").json()["files"] > 0

    def test_임포트_뒤_소스가_바뀌면_stale_이_된다(self, client, monkeypatch):
        """임포트 시점 도장만 바꾼다 — 요청 시점 해시는 실제 트리에서 온다."""
        monkeypatch.setattr(sut_app, "_BUILD_STAMP", "0" * 64)
        body = client.get("/__build__").json()
        assert body["stale"] is True
        assert body["stamp"] != body["current"]

    def test_변형_경로를_잡아먹지_않는다(self, client):
        """`/{variant}/...` 라우트와 겹치면 도장이 화면 하나를 가린다."""
        assert client.get("/good/login").status_code == 200


class TestTreeHash:
    def test_내용이_바뀌면_해시가_바뀐다(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1", encoding="utf-8")
        before, _ = sut_app._tree_hash(tmp_path)
        (tmp_path / "a.py").write_text("x = 2", encoding="utf-8")
        after, _ = sut_app._tree_hash(tmp_path)
        assert before != after

    def test_파일이_늘면_해시가_바뀐다(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1", encoding="utf-8")
        before, n_before = sut_app._tree_hash(tmp_path)
        (tmp_path / "b.py").write_text("x = 1", encoding="utf-8")
        after, n_after = sut_app._tree_hash(tmp_path)
        assert before != after and n_after == n_before + 1

    def test_이름만_바뀌어도_해시가_바뀐다(self, tmp_path):
        """내용만 이으면 파일 이름 변경이 보이지 않는다."""
        (tmp_path / "a.py").write_text("x = 1", encoding="utf-8")
        before, _ = sut_app._tree_hash(tmp_path)
        (tmp_path / "a.py").rename(tmp_path / "z.py")
        after, _ = sut_app._tree_hash(tmp_path)
        assert before != after

    def test_pycache_는_세지_않는다(self, tmp_path):
        """.pyc 는 실행할 때마다 바뀐다. 세면 늘 '낡았다' 고 답한다."""
        (tmp_path / "a.py").write_text("x = 1", encoding="utf-8")
        before, n_before = sut_app._tree_hash(tmp_path)
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "a.cpython-311.pyc").write_bytes(b"\x00\x01")
        after, n_after = sut_app._tree_hash(tmp_path)
        assert after == before and n_after == n_before
