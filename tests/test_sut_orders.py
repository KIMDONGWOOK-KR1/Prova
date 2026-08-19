"""SUT 주문조회 — 심은 결함 O1(정렬)·O2(합계)가 심은 곳에만 있는지.

good 과 bad 는 O1·O2 외에 한 줄도 다르면 안 된다. 로그인 가드는 상품등록과
같은 이유로 양쪽 동일하다 — 여기서 재는 변수는 O1·O2 뿐이다.
"""
import re

import pytest
from fastapi.testclient import TestClient
from sut.app import app

client = TestClient(app, follow_redirects=False)


def _login(variant: str) -> None:
    r = client.post(f"/{variant}/login",
                    data={"email": "seller@test.com", "password": "Seller1!"})
    assert r.status_code == 303


def _dates(html: str) -> list[str]:
    return re.findall(r'aria-label="주문일">([^<]+)<', html)


def _total(html: str) -> str:
    m = re.search(r'aria-label="합계">([^<]+)<', html)
    assert m, "합계 요소를 찾지 못했습니다"
    return m.group(1)


class TestGuard:
    def test_good_은_비로그인을_로그인으로_보낸다(self):
        client.cookies.clear()
        r = client.get("/good/orders")
        assert r.status_code == 303 and "/good/login" in r.headers["location"]

    def test_bad_도_비로그인을_로그인으로_보낸다(self):
        client.cookies.clear()
        r = client.get("/bad/orders")
        assert r.status_code == 303 and "/bad/login" in r.headers["location"]


class TestGoodOrders:
    def test_다섯_건이_주문일_내림차순으로_나온다(self):
        _login("good")
        r = client.get("/good/orders")
        assert r.status_code == 200
        dates = _dates(r.text)
        assert len(dates) == 5
        assert dates == sorted(dates, reverse=True)

    def test_합계는_전_행의_합이다(self):
        _login("good")
        r = client.get("/good/orders")
        assert "1,859,000" in _total(r.text)


class TestBadOrders:
    def test_O1_다섯_건이_주문일_오름차순으로_나온다(self):
        _login("bad")
        r = client.get("/bad/orders")
        assert r.status_code == 200
        dates = _dates(r.text)
        assert len(dates) == 5
        assert dates == sorted(dates)

    def test_O2_합계에서_마지막_표시행이_빠진다(self):
        # bad 는 O1 때문에 오름차순으로 보여준다 — 마지막 표시 행은
        # ORD-005(1,290,000). 합계 = 1,859,000 - 1,290,000 = 569,000.
        _login("bad")
        r = client.get("/bad/orders")
        assert "569,000" in _total(r.text)
