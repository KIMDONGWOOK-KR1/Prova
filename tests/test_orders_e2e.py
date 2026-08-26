"""주문조회 화면 관통 테스트 — 정렬·합계, 화면 스스로의 모순을 잡는다 (스펙 §1-2·§3-4).

## 이 테스트가 지키는 것

    1. good (기획서 준수 구현) -> 전 케이스 PASS. sorted_desc·sum_matches·
       filter 8종이 실제로 만들어져 PASS 했는지까지 본다 — 0건 통과를 100%
       통과로 착각하지 않는다(test_product_e2e.py 와 같은 원칙).
    2. bad  (O1 오래된순 정렬, O2 합계에서 마지막 표시행 누락, O3 필터가
       시작 경계일 제외, O4 필터 후 합계 미재계산) -> 그 결함의 케이스
       여섯만 FAIL, 오탐 0건. 가드·정상·labels·필터의 배제/빈 기간/빈 문구/
       빈 값 케이스는 심은 결함과 무관하므로 bad 에서도 PASS 해야 한다.
    3. 리포트 HTML 에 두 실패의 사유(깨진 날짜 쌍 / 두 합계값)가 실린다.

## 왜 orders_spec.md 가 두 화면(로그인 + 주문조회)을 담는가

product_spec.md 와 같은 이유다 — expand_precondition 이 전제가 가리키는
로그인 화면을 **같은 문서 안에서** 찾는다(s2_case_generator/precondition.py).
로그인 화면 자체의 케이스는 test_pipeline_e2e.py 가 이미 지키므로, 여기서는
`only="orders"` 로 걸러 주문조회 화면의 케이스만 본다.
"""

from __future__ import annotations

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline

LOGIN_PDF = "fixtures/specs/login_spec.pdf"
ORDERS_PDF = "fixtures/specs/orders_spec.pdf"


def _run(variant: str, sut_base: str, tmp_path):
    report, run_dir = run_pipeline(
        pdf_path=ORDERS_PDF,
        base_url=f"{sut_base}/{variant}",
        llm=MockLLM.for_document(LOGIN_PDF, ORDERS_PDF),
        run_id=f"test-orders-{variant}",
        runs_root=tmp_path,
        only="orders",
    )
    return report, run_dir


@pytest.fixture(scope="module")
def good_run(sut_base, tmp_path_factory):
    return _run("good", sut_base, tmp_path_factory.mktemp("orders-good"))


@pytest.fixture(scope="module")
def bad_run(sut_base, tmp_path_factory):
    return _run("bad", sut_base, tmp_path_factory.mktemp("orders-bad"))


def _case(report, needle: str):
    return next(v for v in report.cases if needle in v.case_id)


def _filter_cases_of(report):
    return [v for v in report.cases if "-filter-" in v.case_id]


def _filter_case(report, title_needle: str):
    """filter 케이스는 kind 가 전부 'filter' 라 제목으로 구분한다."""
    return next(v for v in _filter_cases_of(report) if title_needle in v.title)


class TestGood:
    def test_전부_통과한다(self, good_run):
        report, _ = good_run
        failures = [v for v in report.cases if v.verdict == "FAIL"]
        assert not failures, (
            "기획서 준수 구현에서 실패가 났다 — 오탐이다:\n"
            + "\n".join(f"  {v.case_id}: {v.failure_detail}" for v in failures)
        )
        assert report.summary["fail"] == 0

    def test_정렬_케이스가_만들어져_통과했다(self, good_run):
        """씨앗 표에서 정렬(sorted_desc) 케이스가 실제로 생성됐는지까지 본다 —
        생성되지 않았는데 실패가 0건이라 통과한 것으로 착각하지 않는다."""
        report, _ = good_run
        case = _case(report, "orders-sorted-")
        assert case.verdict == "PASS", case.failure_detail

    def test_합계_케이스가_만들어져_통과했다(self, good_run):
        report, _ = good_run
        case = _case(report, "orders-sum-")
        assert case.verdict == "PASS", case.failure_detail

    def test_가드_케이스가_통과했다(self, good_run):
        report, _ = good_run
        case = _case(report, "orders-precondition-guard-")
        assert case.verdict == "PASS", case.failure_detail

    def test_건수_케이스가_만들어져_통과했다(self, good_run):
        """씨앗 5행이 모두 렌더됐는지 직접 센다 — 정렬·합계만으로는 행이
        통째로 하나 빠져도 잡히지 않는다(I5)."""
        report, _ = good_run
        case = _case(report, "orders-seedcount-")
        assert case.verdict == "PASS", case.failure_detail

    def test_케이스가_생성됐다(self, good_run):
        report, _ = good_run
        assert report.summary["total"] > 0

    def test_전체_열다섯_건이다(self, good_run):
        """valid + labels + sorted + sum + seedcount + filter 9종 + guard = 15건.

        labels 케이스는 날짜 필터 요소(시작일·종료일·조회)가 §2 에 생기면서
        처음 만들어졌다 — 그 라벨들이 화면에서 찾아지는지 본다.
        """
        report, _ = good_run
        assert report.summary["total"] == 15, [c.case_id for c in report.cases]

    def test_필터_케이스_아홉_개가_만들어져_전부_통과했다(self, good_run):
        """입력↔재조회(fill·fill·click 후 판정)가 실제 브라우저에서 도는지의
        증명이 이 테스트다 — input[type=date] 에 ISO 문자열 fill, 스텝 실행
        후 상태에 컬렉션 판정. 여기 걸리면 S4/S5 가정이 깨진 것이다."""
        report, _ = good_run
        cases = _filter_cases_of(report)
        assert len(cases) == 9, [c.case_id for c in report.cases]
        fails = [c for c in cases if c.verdict != "PASS"]
        assert not fails, "\n".join(f"  {c.case_id}: {c.failure_detail}" for c in fails)


class TestBad:
    def test_심은_결함만_지목한다(self, bad_run):
        """O1~O5 의 케이스 일곱만 FAIL 이어야 한다 — 오탐 0건.

        무필터: 정렬(O1)·합계(O2). 필터: 건수·경계 포함(O3), 필터 후
        합계(O4), 필터 후 정렬(O1 이 필터 화면에도 남는다), 기간 역전(O5).
        기간 밖 배제·빈 기간 0건·빈 문구·빈 값 전체는 bad 도 올바르게
        구현했으므로 PASS 여야 한다 — 결함 하나당 그 규칙의 케이스가 잡는다.
        """
        report, _ = bad_run
        fails = {v.case_id for v in report.cases if v.verdict == "FAIL"}
        expected = {
            _case(report, "orders-sorted-").case_id,          # O1
            _case(report, "orders-sum-").case_id,             # O2
            _filter_case(report, "기간 내 주문").case_id,      # O3 — 건수
            _filter_case(report, "경계 포함").case_id,         # O3 — 경계일
            _filter_case(report, "합계가 표시된").case_id,     # O4
            _filter_case(report, "최신순으로 정렬").case_id,   # O1 (필터 후)
            _filter_case(report, "시작일이 종료일보다").case_id,  # O5 — 기간 역전
        }
        assert fails == expected, (
            f"오탐(심지 않은 결함): {fails - expected} / "
            f"미탐(놓친 결함): {expected - fails}"
        )

    def test_가드_케이스는_통과한다(self, bad_run):
        """로그인 가드는 O1·O2 와 무관한 결함이다 — bad 에도 온전히 구현돼 있다."""
        report, _ = bad_run
        case = _case(report, "orders-precondition-guard-")
        assert case.verdict == "PASS", case.failure_detail

    def test_정상_케이스는_통과한다(self, bad_run):
        """orders-valid-001 은 화면 진입만 확인한다 — 정렬·합계와 무관하므로
        O1·O2 가 있어도 통과해야 한다. 그렇지 않으면 이 화면의 무관한 케이스가
        오탐으로 걸린 것이다."""
        report, _ = bad_run
        case = _case(report, "orders-valid-")
        assert case.verdict == "PASS", case.failure_detail

    def test_건수_케이스는_통과한다(self, bad_run):
        """bad 도 5행을 전부 렌더한다 — O1(정렬 순서)·O2(합계 계산)는 건수와
        무관하므로 이 케이스는 bad 에서도 PASS 해야 한다(I5)."""
        report, _ = bad_run
        case = _case(report, "orders-seedcount-")
        assert case.verdict == "PASS", case.failure_detail

    def test_전체_열다섯_건_중_여덟만_통과한다(self, bad_run):
        """PASS 8건(valid·labels·seedcount·guard·필터 배제/빈 기간/빈 문구/
        빈 값), FAIL 7건(O1 둘·O2·O3 둘·O4·O5)."""
        report, _ = bad_run
        assert report.summary["total"] == 15, [c.case_id for c in report.cases]
        assert report.summary["pass"] == 8
        assert report.summary["fail"] == 7

    def test_정렬_실패_사유가_깨진_날짜_쌍을_말한다(self, bad_run):
        report, _ = bad_run
        case = _case(report, "orders-sorted-")
        assert case.verdict == "FAIL"
        # O1: 오래된순(오름차순) — 정렬이 깨진 인접 두 날짜가 사유에 남는다.
        assert "2026-07-28" in case.failure_detail
        assert "2026-08-03" in case.failure_detail

    def test_합계_실패_사유가_두_합계값을_말한다(self, bad_run):
        report, _ = bad_run
        case = _case(report, "orders-sum-")
        assert case.verdict == "FAIL"
        # O2: 화면이 보여주는 합계(569,000)와 행의 실제 합(1,859,000)이 다르다.
        detail = case.failure_detail.replace(",", "")
        assert "1859000" in detail
        assert "569000" in detail

    def test_리포트_HTML에_두_실패_사유가_실린다(self, bad_run):
        _, run_dir = bad_run
        html = (run_dir / "report.html").read_text(encoding="utf-8")
        assert "2026-07-28" in html and "2026-08-03" in html
        assert "1,859,000" in html or "1859000" in html.replace(",", "")
        assert "569,000" in html or "569000" in html.replace(",", "")


# ---------------------------------------------------------------------------
# 순수 <table> 마크업 — 탐지 경로가 aria-label 없이도 닿는가
# ---------------------------------------------------------------------------
#
# table/badtable 변형은 good/bad 와 데이터·결함이 같고 마크업만 <table> 이다.
# 판정이 good/bad 와 같아야 한다 — 다르면 탐지 한계가 판정에 새는 것이다.


@pytest.fixture(scope="module")
def table_run(sut_base, tmp_path_factory):
    return _run("table", sut_base, tmp_path_factory.mktemp("orders-table"))


@pytest.fixture(scope="module")
def badtable_run(sut_base, tmp_path_factory):
    return _run("badtable", sut_base, tmp_path_factory.mktemp("orders-badtable"))


class TestTableMarkup:
    def test_표_마크업에서도_전부_통과한다(self, table_run):
        report, _ = table_run
        failures = [v for v in report.cases if v.verdict == "FAIL"]
        assert not failures, "\n".join(f"  {v.case_id}: {v.failure_detail}" for v in failures)
        assert report.summary["total"] == 15

    def test_표_마크업에서도_심은_결함만_지목한다(self, badtable_run):
        """bad 와 같은 일곱 케이스만 FAIL — 마크업이 판정에 새지 않는다."""
        report, _ = badtable_run
        fails = {v.case_id for v in report.cases if v.verdict == "FAIL"}
        expected = {
            _case(report, "orders-sorted-").case_id,
            _case(report, "orders-sum-").case_id,
            _filter_case(report, "기간 내 주문").case_id,
            _filter_case(report, "경계 포함").case_id,
            _filter_case(report, "합계가 표시된").case_id,
            _filter_case(report, "최신순으로 정렬").case_id,
            _filter_case(report, "시작일이 종료일보다").case_id,
        }
        assert fails == expected, (
            f"오탐: {fails - expected} / 미탐: {expected - fails}"
        )

    def test_표_경로로_찾은_사실이_사유에_남는다(self, badtable_run):
        """도구가 판단을 했으면 그 사실이 리포트에 남아야 한다 — 정렬 FAIL 사유에
        '표 머리글' 로 찾았다는 말이 있어야 한다."""
        report, _ = badtable_run
        case = _case(report, "orders-sorted-")
        assert "표 머리글" in (case.failure_detail or ""), case.failure_detail
