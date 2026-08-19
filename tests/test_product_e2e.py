"""상품등록 화면 관통 테스트 — 전제가 있는 화면의 첫 수용 기준 (스펙 §3-6·§3-7).

## 이 테스트가 지키는 것

    1. good (기획서 준수 구현) -> 전 케이스 PASS
    2. bad  (P1 가격 숫자 검사 누락, P2 로그인 가드 누락) -> 그 둘만 FAIL, 오탐 0건
    3. 전제 계정 자체가 틀리면(비밀번호 불일치) 그 실패는 이 화면의 결함이 아니라
       precondition_failed 로 분류된다 — 로그인 화면이 이미 자신의 결함을 낸다.

## 왜 product_spec.md 가 두 화면(로그인 + 상품 등록)을 담는가

`expand_precondition` 은 전제가 가리키는 로그인 화면을 **같은 문서 안에서** 찾는다
(s2_case_generator/precondition.py). 상품등록 화면만 담은 단일 화면 PDF로는 그
탐색이 실패해 전제 스텝이 생기지 않는다. 그래서 multi_spec.md 가 화면을 조립하는
것과 같은 방식으로 — 로그인 화면 개요·요소 표를 그대로 재사용해 — 두 화면짜리
문서를 만들었다(fixtures/specs/product_spec.md).

로그인 화면 자체의 케이스(10건)는 여기서 확인하지 않는다 — 이미
test_pipeline_e2e.py 가 지킨다. 그래서 `run_pipeline` 을 `only="product"` 로 불러
상품등록 화면의 케이스만 실행한다. 이렇게 하지 않으면 bad 실행에서 로그인 화면
자신의 심어 둔 결함(B1~B3)까지 섞여, "오탐 0건" 판정이 상품등록이 아닌 로그인의
결함까지 걸러내야 하는 문제가 된다.

## product_badlogin_spec 는 왜 별도 픽스처인가

전제 계정의 비밀번호만 다르다(`Wrong1!`) — 나머지 화면 정의는 product_spec.md 와
완전히 같다. `/good` 구현(전제·검증 모두 올바른 구현)에 대고 돌려서, 구현이 아니라
**기획서가 준 전제 계정 자체가 틀렸을 때**의 분류를 확인한다.
"""

from __future__ import annotations

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline

LOGIN_PDF = "fixtures/specs/login_spec.pdf"
PRODUCT_PDF = "fixtures/specs/product_spec.pdf"
BADLOGIN_PDF = "fixtures/specs/product_badlogin_spec.pdf"


def _run(pdf: str, variant: str, sut_base: str, tmp_path):
    """product 화면 케이스만 실행한다 (로그인 화면 케이스는 test_pipeline_e2e.py 몫)."""
    report, run_dir = run_pipeline(
        pdf_path=pdf,
        base_url=f"{sut_base}/{variant}",
        llm=MockLLM.for_document(LOGIN_PDF, pdf),
        run_id=f"test-product-{variant}-{pdf.split('/')[-1]}",
        runs_root=tmp_path,
        only="product",
    )
    return report, run_dir


@pytest.fixture(scope="module")
def good_run(sut_base, tmp_path_factory):
    return _run(PRODUCT_PDF, "good", sut_base, tmp_path_factory.mktemp("product-good"))


@pytest.fixture(scope="module")
def bad_run(sut_base, tmp_path_factory):
    return _run(PRODUCT_PDF, "bad", sut_base, tmp_path_factory.mktemp("product-bad"))


@pytest.fixture(scope="module")
def badlogin_run(sut_base, tmp_path_factory):
    # 브리프대로 /good 에 대고 돈다 — 전제 계정이 틀렸을 뿐 구현은 올바르다.
    return _run(BADLOGIN_PDF, "good", sut_base, tmp_path_factory.mktemp("product-badlogin"))


class TestGood:
    def test_전부_통과한다(self, good_run):
        report, _ = good_run
        failures = [v for v in report.cases if v.verdict == "FAIL"]
        assert not failures, (
            "기획서 준수 구현에서 실패가 났다 — 오탐이다:\n"
            + "\n".join(f"  {v.case_id}: {v.failure_detail}" for v in failures)
        )
        assert report.summary["fail"] == 0

    def test_케이스가_생성됐다(self, good_run):
        """0건 통과를 100% 통과로 착각하지 않게 한다."""
        report, _ = good_run
        assert report.summary["total"] > 0


class TestBad:
    def test_심은_결함만_지목한다(self, bad_run):
        report, _ = bad_run
        fails = {v.case_id for v in report.cases if v.verdict == "FAIL"}
        assert any("price-numeric" in c for c in fails), fails  # P1
        assert any("precondition-guard" in c for c in fails), fails  # P2
        # 오탐 0건: 위 둘 외의 FAIL 이 없다
        assert all(("price-numeric" in c) or ("precondition-guard" in c)
                   for c in fails), fails

    def test_재고수량_숫자_검사는_통과한다(self, bad_run):
        """P1 은 가격 필드만의 결함이다. 재고수량은 bad 에도 구현돼 있으므로
        같은 규칙(numeric)의 다른 요소까지 오탐으로 잡히지 않아야 한다."""
        report, _ = bad_run
        stock_case = next(
            v for v in report.cases if "stock-numeric" in v.case_id)
        assert stock_case.verdict == "PASS", stock_case.failure_detail


class TestBrokenLogin:
    def test_전제_실패는_따로_분류된다(self, badlogin_run):
        report, _ = badlogin_run
        cats = {v.case_id: v.failure_category for v in report.cases
                if v.verdict == "FAIL"}
        normal = {c: k for c, k in cats.items() if "guard" not in c}
        assert normal, "전제 계정이 틀렸는데 FAIL 이 하나도 없다"
        assert all(k == "precondition_failed" for k in normal.values()), cats
