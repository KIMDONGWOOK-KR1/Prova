"""검색 화면 관통 테스트 — 검증 축이 다른 화면의 수용 기준.

## 이 화면이 다른 이유

로그인·회원가입의 검증은 모두 **'값 자체가 규칙을 어겼는가'** 였다. 그래서 규칙에서
위반값을 만들어 낼 수 있었고, 그게 rule_expander 의 존재 이유였다.

검색은 **'정상 입력에 정해진 결과가 나오는가'** 다. '노트북을 검색하면 3건이 나온다'
는 값의 흠이 아니라 시스템 상태에 대한 기대이고, 규칙이 없으니 위반값을 만들 수도
없다. 그래서 기획서가 입력-결과 짝을 직접 제시하는 경로(ScreenSpec.scenarios)를
따로 뒀다.

## 심어 둔 불일치 (sut/app.py 참고)

    D1  대소문자 구분     기획서는 구분하지 않는다고 명시 -> 'notebook' 이 0건
    D2  0건 안내 누락     결과가 없을 때 아무 문구도 노출하지 않는다
    D3  최소 길이 미검증  규칙 기반 경로가 이 화면에서도 도는지 확인

**D1 이 이 화면을 추가한 이유다.** 검사 자체는 하는데 검사 방법이 기획서와 다른
결함이고, 위반값으로는 절대 잡을 수 없다. 기획서 예시만이 잡아낸다.
"""

from __future__ import annotations

import re

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline

SPEC_PDF = "fixtures/specs/search_spec.pdf"

# 규칙 위반 케이스 중 FAIL 이 기대되는 것 — D3 하나뿐이다.
EXPECTED_RULE_FAILURES = {("query", "min_length")}

# 기획서 예시(scenario) 케이스 중 FAIL 이 기대되는 입력값.
#
# case_id 가 아니라 입력값으로 적는다: 시나리오는 규칙 위반이 아니라서 violates 가
# 없고, 무엇을 넣었을 때 실패하는지가 결함을 가리키는 정보다.
EXPECTED_SCENARIO_FAILURES = {"notebook", "zzzz"}


def _run(variant: str, sut_base: str, tmp_path):
    report, run_dir = run_pipeline(
        pdf_path=SPEC_PDF,
        base_url=f"{sut_base}/{variant}",
        llm=MockLLM.for_spec(SPEC_PDF),
        run_id=f"test-search-{variant}",
        runs_root=tmp_path,
    )
    return report, run_dir


_QUERY_IN_TITLE = re.compile(r"query='([^']*)'")


def _query_of(verdict) -> str:
    """그 케이스가 검색창에 넣은 값.

    StepResult 는 입력값을 담지 않으므로(리포트 용량을 줄이려 target 만 남긴다)
    케이스 제목에서 읽는다. generator 가 시나리오 제목에 `query='...'` 형태로
    넣는다. 시나리오가 아닌 케이스에는 없으므로 빈 문자열이 된다.
    """
    match = _QUERY_IN_TITLE.search(verdict.title)
    return match.group(1) if match else ""


@pytest.fixture(scope="module")
def good_run(sut_base, tmp_path_factory):
    return _run("good", sut_base, tmp_path_factory.mktemp("search-good"))


@pytest.fixture(scope="module")
def bad_run(sut_base, tmp_path_factory):
    return _run("bad", sut_base, tmp_path_factory.mktemp("search-bad"))


class TestGoodVariant:
    def test_전_케이스_통과(self, good_run):
        report, _ = good_run
        failures = [v for v in report.cases if v.verdict == "FAIL"]
        assert not failures, (
            "기획서 준수 구현에서 실패가 났다 — 오탐이다:\n"
            + "\n".join(f"  {v.title}: {v.failure_detail}" for v in failures)
        )
        assert report.summary["pass_rate"] == 100.0

    def test_케이스_구성(self, good_run):
        """정상 1 + 규칙 위반 3(required·min·max) + 기획서 예시 2 = 6건.

        기획서 예시가 positive 로 집계되는 것이 맞다 — 규칙을 어긴 값이 아니라
        정상 입력에 대한 정해진 결과를 확인하기 때문이다. negative 로 두면 S5 의
        판정이 뒤집혀 '에러가 떠야 PASS' 가 되어버린다.
        """
        report, _ = good_run
        assert report.summary["total"] == 6
        assert sum(1 for v in report.cases if v.type == "negative") == 3
        assert sum(1 for v in report.cases if v.type == "positive") == 3

    def test_기획서_결함_경고가_없다(self, good_run):
        report, _ = good_run
        defects = [w for w in report.summary.get("spec_warnings", [])
                   if "제목 다듬기" not in w]
        assert defects == [], f"기획서 결함 경고: {defects}"

    def test_결과_건수_문구를_확인한다(self, good_run):
        """검색 화면의 검증은 '건수 문구가 떴는가' 다. DOM 에서 항목을 세지 않는다 —
        기획서가 건수를 문구로 노출한다고 적었으므로 문구 비교로 충분하고, 그게
        실물 마크업에 덜 의존한다."""
        report, _ = good_run
        case = next(v for v in report.cases if "notebook" in v.title)
        assert case.verdict == "PASS", case.failure_detail
        assert "검색 결과 3건" in case.evidence["expected"]


class TestBadVariant:
    def test_규칙_위반_결함을_잡는다(self, bad_run):
        """D3 — 규칙 기반 경로가 이 화면에서도 도는지."""
        report, _ = bad_run
        failed = {(v.target_element, v.violates)
                  for v in report.cases if v.verdict == "FAIL" and v.type == "negative"}
        assert failed == EXPECTED_RULE_FAILURES

    def test_기획서_예시_결함을_잡는다(self, bad_run):
        """D1·D2 — 위반값으로는 절대 잡을 수 없는 결함.

        D1(대소문자 구분)은 값에 흠이 없다. 'notebook' 은 모든 입력 규칙을
        만족하는 정상 입력이고, 구현도 검사를 하기는 한다 — 다만 기획서와 다른
        방법으로 한다. 규칙에서 위반값을 만드는 방식으로는 이 결함에 도달할
        경로가 없다.
        """
        report, _ = bad_run
        failed = {
            _query_of(v)
            for v in report.cases
            if v.verdict == "FAIL" and v.type == "positive"
        }
        assert failed == EXPECTED_SCENARIO_FAILURES

    def test_오탐이_없다(self, bad_run):
        report, _ = bad_run
        assert report.summary["fail"] == 3, (
            "심은 결함은 3개다:\n"
            + "\n".join(f"  {v.verdict} {v.title}" for v in report.cases)
        )

    def test_정상_검색은_통과한다(self, bad_run):
        """'Notebook'(대문자)은 bad 에서도 3건이 나온다. 검색 자체는 동작한다는
        뜻이고, 그래야 D1 의 FAIL 이 '검색이 아예 안 된다' 가 아니라
        '대소문자 처리가 기획서와 다르다' 로 읽힌다."""
        report, _ = bad_run
        case = next(v for v in report.cases if v.case_id.endswith("valid-001"))
        assert case.verdict == "PASS", case.failure_detail

    def test_구현된_규칙은_통과한다(self, bad_run):
        report, _ = bad_run
        by_rule = {v.violates: v.verdict
                   for v in report.cases if v.type == "negative"}
        assert by_rule["required"] == "PASS"
        assert by_rule["max_length"] == "PASS"
        assert by_rule["min_length"] == "FAIL"


class TestNoNavigationScreen:
    """검색은 제출 후 이동하지 않는다 — 지금까지의 화면과 다른 점."""

    def test_같은_경로에_머문다(self, good_run):
        report, _ = good_run
        for v in report.cases:
            assert "/search" in v.evidence["url"], v.evidence["url"]

    def test_검색어가_URL에_남는다(self, good_run):
        """method=get 이라 검색어가 URL 에 들어간다. 결과를 공유·재현할 수 있어야
        하는 화면이라 그게 맞다. 개인정보가 아니라 검색어이므로 문제되지 않는다."""
        report, _ = good_run
        case = next(v for v in report.cases if "notebook" in v.title)
        assert "query=" in case.evidence["url"]
