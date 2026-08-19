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

## TestFullDocumentNoFilter 는 왜 따로 있는가

위 세 픽스처는 전부 `only="product"` 로 걸러서 돌린다. 그런데 실제 CLI 사용은
필터 없이 문서 전체(로그인 + 상품등록)를 한 번에 돈다. 한 `run_pipeline` 호출은
브라우저 컨텍스트(쿠키 저장소) 하나를 케이스 전부가 공유하므로, 필터 없이 돌리면
로그인 화면의 `login-valid-001` 이 먼저 실행돼 도메인 전역 세션 쿠키
(`session_good`)를 남기고, 그 뒤에 도는 `product-precondition-guard-001` 은
**이미 로그인된 상태로 열려** '비로그인 접근' 을 확인하지 못한 채 리다이렉트가
없다는 이유로 FAIL — 올바른 구현을 오탐으로 지목하는 것이다.

`nodes.run_cases` 가 케이스마다 실행 전에 쿠키를 지우도록 고친 뒤에는(케이스
격리) 실행 순서·필터 여부와 무관하게 가드 케이스가 정직해진다. 이 테스트는
그 격리가 실제로 동작하는지, `only` 필터에 의존하지 않고도 오탐이 없는지를
직접 확인한다 — 격리가 없으면 반드시 실패하는 시나리오다.
"""

from __future__ import annotations

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline

LOGIN_PDF = "fixtures/specs/login_spec.pdf"
PRODUCT_PDF = "fixtures/specs/product_spec.pdf"
BADLOGIN_PDF = "fixtures/specs/product_badlogin_spec.pdf"


def _run(pdf: str, variant: str, sut_base: str, tmp_path, step_timeout_ms: int = 10000):
    """product 화면 케이스만 실행한다 (로그인 화면 케이스는 test_pipeline_e2e.py 몫)."""
    report, run_dir = run_pipeline(
        pdf_path=pdf,
        base_url=f"{sut_base}/{variant}",
        llm=MockLLM.for_document(LOGIN_PDF, pdf),
        run_id=f"test-product-{variant}-{pdf.split('/')[-1]}",
        runs_root=tmp_path,
        only="product",
        step_timeout_ms=step_timeout_ms,
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
    #
    # step_timeout_ms 를 짧게 준다. 여기서 확인하는 것은 "틀린 비밀번호가
    # precondition_failed 로 분류되는가" 이지 도착 확인의 대기 시간이 아니다.
    # 틀린 비밀번호는 아무리 기다려도 로그인에 성공하지 않으므로(비동기 지연이
    # 아니라 논리적 실패) playwright_driver._wait_for_arrival 의 settle 창이
    # 매 케이스마다 기본값(10s) 만큼 헛되이 흘러간다 — 케이스 수만큼 곱해지면
    # 이 테스트 하나가 수십 초~수 분으로 늘어난다. 실물 페이지의 리다이렉트는
    # 이보다 훨씬 빨리 오므로(동기식) 짧은 값으로도 실패 분류라는 목적은
    # 그대로 지켜진다.
    return _run(BADLOGIN_PDF, "good", sut_base,
               tmp_path_factory.mktemp("product-badlogin"), step_timeout_ms=1500)


@pytest.fixture(scope="module")
def good_full_run(sut_base, tmp_path_factory):
    """필터 없이 문서 전체(로그인+상품등록)를 돈다 — 케이스 격리를 실제로 시험한다."""
    report, run_dir = run_pipeline(
        pdf_path=PRODUCT_PDF,
        base_url=f"{sut_base}/good",
        llm=MockLLM.for_document(LOGIN_PDF, PRODUCT_PDF),
        run_id="test-product-good-full",
        runs_root=tmp_path_factory.mktemp("product-good-full"),
    )
    return report, run_dir


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


class TestFullDocumentNoFilter:
    """`only` 필터 없이 문서 전체를 돌려도 오탐이 없다 — 케이스 격리의 증거.

    격리(nodes.run_cases 의 clear_cookies)가 없으면 로그인 화면의 정상 케이스가
    남긴 세션 쿠키 때문에 product-precondition-guard-001 이 스푸리어스하게
    FAIL 한다. 이 테스트는 그 시나리오를 그대로 재현해, 격리가 실제로 막는지
    확인한다.
    """

    def test_필터_없이_돌려도_오탐이_없다(self, good_full_run):
        report, _ = good_full_run
        failures = [v for v in report.cases if v.verdict == "FAIL"]
        assert not failures, (
            "필터 없이 전체 문서를 돌렸을 때 오탐이 났다 — 케이스 격리가 "
            "깨졌을 가능성이 크다:\n"
            + "\n".join(f"  {v.case_id}: {v.failure_detail}" for v in failures)
        )

    def test_로그인과_상품등록_케이스가_모두_들어있다(self, good_full_run):
        """0건이나 반쪽만 돌고 통과한 것을 '전부 통과' 로 착각하지 않게 한다."""
        report, _ = good_full_run
        screen_ids = {v.screen_id for v in report.cases}
        assert screen_ids == {"login", "product"}
        assert report.summary["total"] >= 15

    def test_가드_케이스가_실제로_실행됐다(self, good_full_run):
        report, _ = good_full_run
        guard = next(
            v for v in report.cases if "precondition-guard" in v.case_id)
        assert guard.verdict == "PASS", guard.failure_detail


class TestBrokenLogin:
    def test_전제_실패는_따로_분류된다(self, badlogin_run):
        report, _ = badlogin_run
        cats = {v.case_id: v.failure_category for v in report.cases
                if v.verdict == "FAIL"}
        normal = {c: k for c, k in cats.items() if "guard" not in c}
        assert normal, "전제 계정이 틀렸는데 FAIL 이 하나도 없다"
        assert all(k == "precondition_failed" for k in normal.values()), cats
