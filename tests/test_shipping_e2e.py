"""배송지 등록 화면 — **선택 항목(필수가 아닌 요소)** 이 처음 들어가는 화면.

## 이 화면이 새로 확인하는 것

지금까지 기획서에 적힌 요소는 전부 필수였다. 그래서 **'필수가 아닌 요소에
required 위반 케이스를 만들지 않는가'** 를 한 번도 확인하지 못했다.

만들면 멀쩡한 구현이 FAIL 한다 — 비워 두고 저장하는 것이 정상 동작이기 때문이다.
그건 없는 결함을 보고하는 것이고, 이 도구에서 가장 나쁜 실패다.

상세 주소와 배송 요청사항이 그 요소다. 아파트가 아닌 주소에는 동·호수가 없고,
요청사항이 없는 주문이 더 많다.

## 심어 둔 결함 셋

    J1  우편번호 숫자 검증 없음   자릿수는 보면서 숫자 여부를 안 본다
    J2  주소 최소 길이 검증 없음
    J3  저장 문구가 기획서와 다름

J1 이 특히 이 화면의 모양이다. `numeric` 과 `min_length`·`max_length` 가 한
요소에 함께 걸려 있고 그중 하나만 빠졌다 — 규칙을 묶어 검사하면 자릿수가 먼저
걸려 **숫자 검증이 없다는 사실이 가려진다.**
"""

from __future__ import annotations

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline

SPEC_PDF = "fixtures/specs/shipping_spec.pdf"

#: 기획서 §2 가 '선택' 으로 적은 요소.
OPTIONAL = ("detail_address", "request_msg")


def _run(variant: str, sut_base: str, tmp_path):
    report, _ = run_pipeline(
        pdf_path=SPEC_PDF,
        base_url=f"{sut_base}/{variant}",
        llm=MockLLM.for_spec(SPEC_PDF),
        run_id=f"test-shipping-{variant}",
        runs_root=tmp_path,
    )
    return report


@pytest.fixture(scope="module")
def good_run(sut_base, tmp_path_factory):
    return _run("good", sut_base, tmp_path_factory.mktemp("shipping-good"))


@pytest.fixture(scope="module")
def bad_run(sut_base, tmp_path_factory):
    return _run("bad", sut_base, tmp_path_factory.mktemp("shipping-bad"))


@pytest.fixture(scope="module")
def icons_run(sut_base, tmp_path_factory):
    return _run("icons", sut_base, tmp_path_factory.mktemp("shipping-icons"))


class TestOptionalElements:
    """이 화면을 만든 이유. 선택 항목을 필수처럼 다루면 오탐이 난다."""

    def test_선택_항목에는_필수_위반_케이스를_만들지_않는다(self, good_run):
        wrong = [v.case_id for v in good_run.cases
                 if v.violates == "required" and v.target_element in OPTIONAL]
        assert not wrong, (
            "선택 항목에 required 케이스가 생겼다 — 비워 두고 저장하는 것이 "
            "정상 동작이므로 이 케이스는 멀쩡한 구현을 FAIL 시킨다: " + str(wrong)
        )

    def test_필수_항목에는_만든다(self, good_run):
        """위 테스트가 '아무 케이스도 안 만든다' 로 통과하지 않게 대조군을 둔다."""
        made = {v.target_element for v in good_run.cases if v.violates == "required"}
        assert made == {"recipient", "postcode", "address"}

    def test_선택_항목도_라벨은_확인한다(self, good_run):
        """필수가 아니어도 화면에 있어야 한다 — 검증을 통째로 빼지 않는다."""
        v = next(v for v in good_run.cases if "-labels-" in v.case_id)
        assert v.verdict == "PASS"


class TestGoodVariant:
    def test_전_케이스_통과(self, good_run):
        failures = [v for v in good_run.cases if v.verdict == "FAIL"]
        assert not failures, (
            "기획서 준수 구현에서 실패가 났다 — 오탐이다:\n"
            + "\n".join(f"  {v.title}: {v.failure_detail}" for v in failures)
        )


class TestBadVariant:
    def test_심은_결함만_잡는다(self, bad_run):
        rules = {v.violates for v in bad_run.cases if v.verdict == "FAIL" and v.violates}
        assert rules == {"numeric", "min_length"}, (
            "J1(숫자)·J2(주소 길이)만 규칙 위반으로 잡혀야 한다: " + str(sorted(rules))
        )
        assert bad_run.summary["fail"] == 4, (
            "J1 + J2 + J3(문구, 2건) = 4건이어야 한다:\n"
            + "\n".join(f"  {v.title}" for v in bad_run.cases if v.verdict == "FAIL")
        )

    def test_자릿수는_구현돼_있어_통과한다(self, bad_run):
        """숫자 여부만 빠졌다. 규칙을 묶어 검사하면 이게 안 보인다."""
        for rule in ("min_length", "max_length"):
            v = next(v for v in bad_run.cases
                     if v.violates == rule and v.target_element == "postcode")
            assert v.verdict == "PASS", f"우편번호 {rule} 은 bad 에도 구현돼 있다"


class TestIconsVariant:
    def test_1차_경로만으로는_전부_실패한다(self, icons_run):
        assert icons_run.summary["pass"] == 0

    def test_구현_결함으로_보고하지_않는다(self, icons_run):
        cats = [v.failure_category for v in icons_run.cases if v.verdict == "FAIL"]
        assert cats.count("element_not_found") >= 10, (
            "탐지 실패가 다른 분류로 새고 있다: " + str(sorted(set(cats)))
        )
