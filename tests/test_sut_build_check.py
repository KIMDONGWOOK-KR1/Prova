"""낡은 SUT 를 상대로 재지 않는다 — 실행 전 빌드 도장 확인.

## 무엇을 막는가

떠 있는 대상이 소스보다 낡았으면, 나오는 FAIL 은 **구현의 결함이 아니라 잰
대상이 옛것이라서** 난 것이다. 리포트만 보면 둘은 구별되지 않는다. 이 확인은
그 구별을 실행 **전에** 끝낸다.

## 왜 없으면 조용한가

prova 의 대상은 임의의 웹앱이다. 실물 대상에 `/__build__` 가 없는 것이
정상이고, 없다고 경고하면 그 경고는 늘 뜨므로 아무도 읽지 않게 된다.
'도장이 없다' 와 '도장이 어긋났다' 는 다른 사실이고, 섞지 않는다.
"""

from __future__ import annotations

import pytest

from prova.sut_build import check_sut_build


def _fetch(status: int, body: dict | None):
    calls: list[str] = []

    def fetch(url: str):
        calls.append(url)
        return status, body

    fetch.calls = calls  # type: ignore[attr-defined]
    return fetch


FRESH = {"stamp": "a" * 64, "current": "a" * 64, "stale": False, "files": 9}
STALE = {"stamp": "a" * 64, "current": "b" * 64, "stale": True, "files": 9}


class TestOrigin:
    def test_경로를_떼고_루트에서_묻는다(self):
        """--url 은 보통 변형 경로까지 온다(.../good). 도장은 앱 루트에 있다."""
        fetch = _fetch(200, FRESH)
        check_sut_build("http://localhost:8100/good", fetch=fetch)
        assert fetch.calls == ["http://localhost:8100/__build__"]

    def test_질의문자열도_떼어낸다(self):
        fetch = _fetch(200, FRESH)
        check_sut_build("http://127.0.0.1:8100/bad/orders?x=1", fetch=fetch)
        assert fetch.calls == ["http://127.0.0.1:8100/__build__"]


class TestStates:
    def test_일치하면_match(self):
        assert check_sut_build("http://x/good", fetch=_fetch(200, FRESH)).state \
            == "match"

    def test_어긋나면_stale(self):
        check = check_sut_build("http://x/good", fetch=_fetch(200, STALE))
        assert check.state == "stale"
        assert "재시작" in check.message

    def test_도장이_없으면_absent(self):
        check = check_sut_build("http://x/good", fetch=_fetch(404, None))
        assert check.state == "absent"

    def test_모양이_다른_응답은_도장이_없는_것과_같다(self):
        """`/__build__` 에 남의 라우트가 있을 수 있다. 모르는 응답으로
        '최신이다' 라고 말하면 안 된다."""
        check = check_sut_build("http://x/good", fetch=_fetch(200, {"hello": 1}))
        assert check.state == "absent"

    def test_닿지_않으면_unreachable(self):
        def fetch(url: str):
            raise OSError("connection refused")

        check = check_sut_build("http://x/good", fetch=fetch)
        assert check.state == "unreachable"


class TestBlocking:
    """어긋남만 실행을 막는다. 나머지는 막지 않는다."""

    @pytest.mark.parametrize("status,body,blocks", [
        (200, STALE, True),
        (200, FRESH, False),
        (404, None, False),
    ])
    def test_stale_만_막는다(self, status, body, blocks):
        check = check_sut_build("http://x/good", fetch=_fetch(status, body))
        assert check.blocks is blocks

    def test_닿지_않아도_막지_않는다(self):
        """대상이 죽었으면 파이프라인이 제대로 된 말로 실패한다. 여기서
        가로채면 원인이 '빌드 확인' 으로 잘못 적힌다."""
        def fetch(url: str):
            raise OSError("refused")

        assert check_sut_build("http://x/good", fetch=fetch).blocks is False
