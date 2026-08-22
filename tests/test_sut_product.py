"""SUT 상품등록 — 심은 결함이 심은 곳에만 있는지 (오탐 0건의 전제).

good 과 bad 는 P1·P2 외에 한 줄도 다르면 안 된다. 다르면 FAIL 이 났을 때
'심은 결함인가, 딴 데가 다른가' 를 구분할 수 없다.
"""
import pytest
from fastapi.testclient import TestClient
from sut.app import app

@pytest.fixture
def client() -> TestClient:
    """테스트마다 새 클라이언트 — 쿠키가 클래스를 넘나들지 않는다.

    모듈 전역 클라이언트를 쓰면 앞 클래스가 남긴 세션 쿠키를 뒤 클래스가
    물려받는다. 파이프라인에서 고친 '남은 세션 쿠키 오탐'(test_product_e2e
    참고)과 정확히 같은 모양이 SUT 단위 테스트에 남아 있었다 (2026-08-22).
    """
    return TestClient(app, follow_redirects=False)


def _login(client: TestClient, variant: str) -> None:
    r = client.post(f"/{variant}/login",
                    data={"email": "seller@test.com", "password": "Seller1!"})
    assert r.status_code == 303


class TestGuard:
    def test_good_은_비로그인을_로그인으로_보낸다(self, client):
        r = client.get("/good/product")
        assert r.status_code == 303 and "/good/login" in r.headers["location"]

    def test_bad_는_비로그인도_연다_P2(self, client):
        assert client.get("/bad/product").status_code == 200


class TestPriceNumeric:
    def test_good_은_가격_문자를_거부한다(self, client):
        _login(client, "good")
        r = client.post("/good/product", data={
            "name": "노트북", "price": "만원", "stock": "3"})
        assert "숫자만 입력" in r.text

    def test_bad_는_가격_문자를_통과시킨다_P1(self, client):
        _login(client, "bad")
        r = client.post("/bad/product", data={
            "name": "노트북", "price": "만원", "stock": "3"})
        assert "상품이 등록되었습니다" in r.text


class TestHappy:
    @pytest.mark.parametrize("variant", ["good", "bad"])
    def test_정상_등록은_양쪽_모두_성공한다(self, client, variant):
        _login(client, variant)
        r = client.post(f"/{variant}/product", data={
            "name": "노트북", "price": "1290000", "stock": "3"})
        assert "상품이 등록되었습니다" in r.text
