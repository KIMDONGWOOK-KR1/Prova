"""factory.make_llm 의 mock 경로가 화면이 여럿인 문서를 옳게 다루는가.

## 왜 이 테스트가 필요한가

웹 UI/CLI 의 mock 백엔드는 `factory.make_llm("mock", cfg, pdf)` →
`MockLLM.for_spec(pdf)` 를 쓴다. 이 생성자는 원래 **PDF 하나당 골든 하나만**
등록했다 — 상품등록·주문조회처럼 전제(로그인) 화면을 같은 PDF 에 담는 문서를
열면, 로그인 페이지도 두 번째 화면(주문 조회 등)의 골든을 그대로 돌려받아
화면 ID 가 뒤섞였다. 실측(웹 UI 스모크)에서 로그인 페이지가 '주문 조회' 로
추출되는 것을 직접 봤다 — 계획 화면에 '주문 조회' 그룹만 뜨고 '로그인' 그룹은
아예 나타나지 않았다.

`MockLLM.for_document()` (테스트 전용, 화면마다 골든을 지정해 등록)는 이 문제가
없지만 웹 UI/CLI 경로에서는 쓸 수 없다 — 그 경로는 PDF 경로 하나만 받는다.

## 고친 것

`for_spec` 이 요청받은 PDF 자신의 골든뿐 아니라 `fixtures/specs/*_spec.golden.json`
전부를 화면 ID 로 등록해 두게 했다(`register_screen`). `_pick_screen` 은 이미
프롬프트의 '화면 ID | <id> |' 행을 정확 매칭하므로, 관계없는 골든이 섞여도
엉뚱한 화면을 고르지 않는다 — 후보에 아예 들지 않는다. 요청한 PDF 자신의
골든은 마지막에 다시 등록해, 같은 screen_id 를 공유하는 다른 픽스처
(`product_spec` vs `product_badlogin_spec`)보다 우선하게 했다.
"""

from __future__ import annotations

import yaml

from prova.llm.factory import make_llm
from prova.s1_spec_extractor.extractor import extract_document

CONFIG = "configs/default.yaml"


def _mock_llm(pdf: str):
    cfg = yaml.safe_load(open(CONFIG, encoding="utf-8")) or {}
    llm, warnings = make_llm("mock", cfg, pdf)
    return llm, warnings


class TestTwoScreenDocument:
    """orders_spec.pdf 는 로그인 페이지 + 주문조회 페이지, 한 문서 두 화면이다."""

    def test_두_화면_모두_제_이름으로_추출된다(self):
        llm, _ = _mock_llm("fixtures/specs/orders_spec.pdf")
        doc = extract_document("fixtures/specs/orders_spec.pdf", llm)

        screen_ids = [s.screen_id for s in doc.screens]
        assert screen_ids == ["login", "orders"], screen_ids

        by_id = {s.screen_id: s for s in doc.screens}
        assert by_id["login"].screen_name == "로그인"
        assert by_id["orders"].screen_name == "주문 조회"

    def test_전제_스텝을_만들_로그인_화면을_찾는다(self):
        """login 화면이 더는 orders 골든으로 뒤섞이지 않으므로, 전제(로그인)
        스텝 생성이 '로그인 화면이 문서에 없다' 경고 없이 성공해야 한다."""
        llm, _ = _mock_llm("fixtures/specs/orders_spec.pdf")
        doc = extract_document("fixtures/specs/orders_spec.pdf", llm)

        orders = next(s for s in doc.screens if s.screen_id == "orders")
        assert not any("로그인 화면(login)이 문서에 없어" in w for w in orders.warnings), (
            orders.warnings
        )


class TestSingleScreenDocumentUnaffected:
    """다른 골든이 함께 등록되더라도 단일 화면 PDF 는 그대로 제 화면만 뽑는다."""

    def test_login_spec는_login_화면_하나만_뽑는다(self):
        llm, _ = _mock_llm("fixtures/specs/login_spec.pdf")
        doc = extract_document("fixtures/specs/login_spec.pdf", llm)

        assert len(doc.screens) == 1
        assert doc.screens[0].screen_id == "login"
        assert doc.screens[0].screen_name == "로그인"

    def test_search_spec는_search_화면_하나만_뽑는다(self):
        llm, _ = _mock_llm("fixtures/specs/search_spec.pdf")
        doc = extract_document("fixtures/specs/search_spec.pdf", llm)

        assert len(doc.screens) == 1
        assert doc.screens[0].screen_id == "search"


class TestSameScreenIdDifferentFixture:
    """product_spec 과 product_badlogin_spec 은 같은 screen_id('product')를

    쓰지만 전제 계정이 다르다. 요청한 PDF 자신의 골든이 다른 골든보다
    우선해야, badlogin 픽스처를 열었을 때 good 픽스처의 (올바른) 계정으로
    뒤바뀌지 않는다.
    """

    def test_badlogin_픽스처는_제_전제_계정을_쓴다(self):
        llm, _ = _mock_llm("fixtures/specs/product_badlogin_spec.pdf")
        doc = extract_document("fixtures/specs/product_badlogin_spec.pdf", llm)

        product = next(s for s in doc.screens if s.screen_id == "product")
        assert product.precondition is not None
        assert product.precondition.account_password == "Wrong1!"

    def test_good_픽스처는_제_전제_계정을_쓴다(self):
        llm, _ = _mock_llm("fixtures/specs/product_spec.pdf")
        doc = extract_document("fixtures/specs/product_spec.pdf", llm)

        product = next(s for s in doc.screens if s.screen_id == "product")
        assert product.precondition is not None
        assert product.precondition.account_password != "Wrong1!"
