"""SUT 주문조회 — 심은 결함 O1(정렬)·O2(합계)가 심은 곳에만 있는지.

good 과 bad 는 O1·O2 외에 한 줄도 다르면 안 된다. 로그인 가드는 상품등록과
같은 이유로 양쪽 동일하다 — 여기서 재는 변수는 O1·O2 뿐이다.
"""
import re

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


def _dates(html: str) -> list[str]:
    return re.findall(r'aria-label="주문일">([^<]+)<', html)


def _total(html: str) -> str:
    m = re.search(r'aria-label="합계">([^<]+)<', html)
    assert m, "합계 요소를 찾지 못했습니다"
    return m.group(1)


class TestGuard:
    def test_good_은_비로그인을_로그인으로_보낸다(self, client):
        r = client.get("/good/orders")
        assert r.status_code == 303 and "/good/login" in r.headers["location"]

    def test_bad_도_비로그인을_로그인으로_보낸다(self, client):
        r = client.get("/bad/orders")
        assert r.status_code == 303 and "/bad/login" in r.headers["location"]


class TestGoodOrders:
    def test_다섯_건이_주문일_내림차순으로_나온다(self, client):
        _login(client, "good")
        r = client.get("/good/orders")
        assert r.status_code == 200
        dates = _dates(r.text)
        assert len(dates) == 5
        assert dates == sorted(dates, reverse=True)

    def test_합계는_전_행의_합이다(self, client):
        _login(client, "good")
        r = client.get("/good/orders")
        assert "1,859,000" in _total(r.text)


class TestBadOrders:
    def test_O1_다섯_건이_주문일_오름차순으로_나온다(self, client):
        _login(client, "bad")
        r = client.get("/bad/orders")
        assert r.status_code == 200
        dates = _dates(r.text)
        assert len(dates) == 5
        assert dates == sorted(dates)

    def test_O2_합계에서_마지막_표시행이_빠진다(self, client):
        # bad 는 O1 때문에 오름차순으로 보여준다 — 마지막 표시 행은
        # ORD-005(1,290,000). 합계 = 1,859,000 - 1,290,000 = 569,000.
        _login(client, "bad")
        r = client.get("/bad/orders")
        assert "569,000" in _total(r.text)


class TestTableMarkup:
    """table/badtable 변형 — 같은 데이터·같은 결함을 aria-label 없는 순수 <table>
    로 렌더한다. 탐지 경로(표 머리글)가 실물 화면 모양에서도 닿는지 보이기 위한
    변형이므로 마크업에 aria-label 이 하나도 없어야 한다."""

    def test_table_은_aria_label_이_없는_표다(self, client):
        _login(client, "table")
        html = client.get("/table/orders").text
        assert "aria-label" not in html
        assert "<table" in html and "<caption>주문 목록</caption>" in html
        assert "<th>주문일</th>" in html and "<th>금액</th>" in html

    def test_table_은_good_과_같은_순서·합계다(self, client):
        _login(client, "table"); t = client.get("/table/orders").text
        _login(client, "good"); g = client.get("/good/orders").text
        assert re.findall(r"<td>(\d{4}-\d{2}-\d{2})</td>", t) == _dates(g)
        assert re.search(r"<th>합계</th><td[^>]*>([^<]+)<", t).group(1) == _total(g)

    def test_badtable_은_bad_와_같은_순서·합계다(self, client):
        _login(client, "badtable"); t = client.get("/badtable/orders").text
        _login(client, "bad"); b = client.get("/bad/orders").text
        assert re.findall(r"<td>(\d{4}-\d{2}-\d{2})</td>", t) == _dates(b)
        assert re.search(r"<th>합계</th><td[^>]*>([^<]+)<", t).group(1) == _total(b)

    def test_table_도_가드가_있다(self, client):
        r = client.get("/table/orders")
        assert r.status_code == 303 and r.headers["location"] == "/table/login"


class TestDateFilter:
    """날짜 필터 — 심은 결함 O3(경계일 제외)·O4(합계 미재계산) (specs/2026-08-24).

    good/bad 는 필터에서도 O3·O4 외에 다르면 안 된다 — 빈 값 전체·빈 결과
    문구는 양쪽 모두 올바르게 구현한다(결함 분리). 폼은 목록 마크업 밖이라
    table 쌍둥이와 공유되고, aria-label 대신 label 로 감싼다 — table 변형의
    'aria-label 0개' 성질을 폼이 깨면 안 된다.
    """

    RANGE = "?start_date=2026-08-03&end_date=2026-08-12"
    EMPTY = "?start_date=2026-08-16&end_date=2026-08-17"

    def _get(self, client, variant: str, query: str) -> str:
        _login(client, variant)
        r = client.get(f"/{variant}/orders{query}")
        assert r.status_code == 200
        return r.text

    def test_good_은_경계_포함_3건이다(self, client):
        html = self._get(client, "good", self.RANGE)
        assert html.count("ORD-0") == 3
        assert "ORD-002" in html and "ORD-005" not in html

    def test_good_합계는_표시_행의_합이다(self, client):
        html = self._get(client, "good", self.RANGE)
        assert "557,000" in html  # 39,000 + 89,000 + 429,000

    def test_good_빈_기간은_문구를_노출한다(self, client):
        html = self._get(client, "good", self.EMPTY)
        assert "기간 내 주문이 없습니다." in html and "ORD-0" not in html

    def test_good_빈_값은_전체_5건이고_문구가_없다(self, client):
        html = self._get(client, "good", "")
        assert html.count("ORD-0") == 5
        assert "기간 내 주문이 없습니다." not in html

    def test_bad_는_시작_경계일을_뺀다(self, client):
        html = self._get(client, "bad", self.RANGE)
        assert "ORD-002" not in html and html.count("ORD-0") == 2

    def test_bad_합계는_필터_전_값_그대로다(self, client):
        html = self._get(client, "bad", self.RANGE)
        assert "569,000" in html  # 무필터 O2 값 — 재계산하지 않는다(O4)

    def test_bad_도_빈_문구는_올바르다(self, client):
        assert "기간 내 주문이 없습니다." in self._get(client, "bad", self.EMPTY)

    def test_table_쌍둥이도_같은_필터_결과다(self, client):
        html = self._get(client, "table", self.RANGE)
        assert "aria-label" not in html
        assert html.count("ORD-0") == 3 and "ORD-002" in html
