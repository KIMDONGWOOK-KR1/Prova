"""SUT 상품등록 — 심은 결함이 심은 곳에만 있는지 (오탐 0건의 전제).

good 과 bad 는 P1·P2 외에 한 줄도 다르면 안 된다. 다르면 FAIL 이 났을 때
'심은 결함인가, 딴 데가 다른가' 를 구분할 수 없다.
"""
import pytest
from fastapi.testclient import TestClient
from sut.app import app

client = TestClient(app, follow_redirects=False)


def _login(variant: str) -> dict:
    r = client.post(f"/{variant}/login",
                    data={"email": "seller@test.com", "password": "Seller1!"})
    assert r.status_code == 303
    return {c: v for c, v in client.cookies.items()}


class TestGuard:
    def test_good_은_비로그인을_로그인으로_보낸다(self):
        client.cookies.clear()
        r = client.get("/good/product")
        assert r.status_code == 303 and "/good/login" in r.headers["location"]

    def test_bad_는_비로그인도_연다_P2(self):
        client.cookies.clear()
        assert client.get("/bad/product").status_code == 200


class TestPriceNumeric:
    def test_good_은_가격_문자를_거부한다(self):
        _login("good")
        r = client.post("/good/product", data={
            "name": "노트북", "price": "만원", "stock": "3"})
        assert "숫자만 입력" in r.text

    def test_bad_는_가격_문자를_통과시킨다_P1(self):
        _login("bad")
        r = client.post("/bad/product", data={
            "name": "노트북", "price": "만원", "stock": "3"})
        assert "상품이 등록되었습니다" in r.text


class TestHappy:
    @pytest.mark.parametrize("variant", ["good", "bad"])
    def test_정상_등록은_양쪽_모두_성공한다(self, variant):
        _login(variant)
        r = client.post(f"/{variant}/product", data={
            "name": "노트북", "price": "1290000", "stock": "3"})
        assert "상품이 등록되었습니다" in r.text
