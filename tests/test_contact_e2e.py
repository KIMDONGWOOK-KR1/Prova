"""문의하기 화면 — 정규식 형식 규칙(`pattern`)을 처음 쓰는 화면.

## 이 화면이 새로 확인하는 것

기존 화면의 형식 검증은 전부 `format: email` 이었다. 이메일은 '@ 가 있고 점이
있으면' 통과라 느슨하다. `rule_expander` 는 `pattern`(정규식)도 지원하고 있었는데
**그 경로를 타는 기획서가 하나도 없었다** — 코드에 있고 아무도 쓰지 않는 기능은
동작한다는 증거가 없다(이 저장소가 반복해서 치른 값이다).

연락처를 `^010-\\d{4}-\\d{4}$` 로 고정해 그 경로를 처음 밟는다.

## 심어 둔 결함 셋 — 서로 다른 종류다

같은 종류를 또 심으면 화면을 늘린 만큼의 검증력을 얻지 못한다(회원가입에서 배운 것).

    H1  연락처 정규식 형식 검증 없음      <- 새 규칙 종류가 실제로 잡히는가
    H2  문의 내용 최소 길이 검증 없음     <- 한 요소의 규칙 중 일부만 빠진 모양
                                          (최대 길이는 구현돼 있다 — 닉네임 C3 의 거울상)
    H3  접수 문구가 기획서와 다름         <- 값이 아니라 문구가 어긋나는 종류

## H3 이 FAIL 2건인 이유

    valid-001      정상 케이스의 성공 문구가 안 뜬다
    scenario-...   기획서 예시 동작의 문구가 안 뜬다

중복이 아니다. 둘은 같은 문구를 다른 입력으로 확인한다 — 구현이 특정 입력에서만
문구를 바꾸면 한쪽만 잡힌다.

## icons 변형 — 2차 경로(VLM)를 재는 대상

`/icons/contact` 는 **검증 로직이 good 과 완전히 같고** 화면의 접근성 이름이
하나도 없다(라벨은 아이콘, 버튼은 아이콘, placeholder 없음). 1차 경로의 네 전략이
전부 막히므로 전 케이스가 탐지 실패로 떨어진다.

`nolabel` 변형은 버튼 **하나**만 아이콘이라 채점할 항목이 적었다. 이 변형은
입력·선택·여러 줄 입력·체크박스·버튼 다섯 종류를 한 화면에 모아, 2차 경로가
살려내야 할 항목을 훨씬 넓게 만든다.

**여기서 FAIL 이 나는 것이 정상이다.** 그 FAIL 이 '구현 결함' 이 아니라 '탐지
실패' 로 분류되는지가 이 변형이 지키는 것이다 — 도구가 못 찾은 것을 구현 결함으로
보고하면 없는 결함이 된다.
"""

from __future__ import annotations

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline

SPEC_PDF = "fixtures/specs/contact_spec.pdf"


def _run(variant: str, sut_base: str, tmp_path):
    report, _ = run_pipeline(
        pdf_path=SPEC_PDF,
        base_url=f"{sut_base}/{variant}",
        llm=MockLLM.for_spec(SPEC_PDF),
        run_id=f"test-contact-{variant}",
        runs_root=tmp_path,
    )
    return report


@pytest.fixture(scope="module")
def good_run(sut_base, tmp_path_factory):
    return _run("good", sut_base, tmp_path_factory.mktemp("contact-good"))


@pytest.fixture(scope="module")
def bad_run(sut_base, tmp_path_factory):
    return _run("bad", sut_base, tmp_path_factory.mktemp("contact-bad"))


@pytest.fixture(scope="module")
def icons_run(sut_base, tmp_path_factory):
    return _run("icons", sut_base, tmp_path_factory.mktemp("contact-icons"))


class TestGoodVariant:
    def test_전_케이스_통과(self, good_run):
        failures = [v for v in good_run.cases if v.verdict == "FAIL"]
        assert not failures, (
            "기획서 준수 구현에서 실패가 났다 — 오탐이다:\n"
            + "\n".join(f"  {v.title}: {v.failure_detail}" for v in failures)
        )

    def test_케이스_구성(self, good_run):
        """정상 1 + 규칙 위반 12 + 선택 목록 1 + 안내 문구 1 + 라벨 1 + 예시 1 = 17건."""
        assert good_run.summary["total"] == 17, [v.case_id for v in good_run.cases]

    def test_정규식_규칙이_케이스로_전개된다(self, good_run):
        """이 화면을 만든 이유다. 케이스가 안 생기면 규칙이 있으나 마나다."""
        assert any(v.violates == "pattern" for v in good_run.cases), \
            "pattern 규칙의 위반 케이스가 없다 — 규칙이 조용히 빠졌다"


class TestBadVariant:
    def test_심은_결함만_잡는다(self, bad_run):
        failed = {v.case_id for v in bad_run.cases if v.verdict == "FAIL"}
        rules = {v.violates for v in bad_run.cases if v.verdict == "FAIL" and v.violates}
        assert rules == {"pattern", "min_length"}, (
            "H1(정규식)·H2(최소 길이)만 규칙 위반으로 잡혀야 한다: " + str(sorted(rules))
        )
        assert len(failed) == 4, (
            "H1 + H2 + H3(문구, 2건) = 4건이어야 한다:\n"
            + "\n".join(f"  {v.title}" for v in bad_run.cases if v.verdict == "FAIL")
        )

    def test_최대_길이는_구현돼_있어_통과한다(self, bad_run):
        """한 요소의 규칙 중 일부만 빠진 모양. 규칙 단위로 갈라야 이게 보인다."""
        v = next(v for v in bad_run.cases if v.violates == "max_length")
        assert v.verdict == "PASS", "최대 길이는 bad 에도 구현돼 있다"

    def test_오탐이_없다(self, bad_run):
        """심은 결함과 무관한 케이스가 FAIL 하면 오탐이다."""
        assert bad_run.summary["pass"] == 13


class TestIconsVariant:
    """2차 경로(VLM)가 살려내야 할 화면. 1차만으로는 아무것도 못 찾는다."""

    def test_1차_경로만으로는_전부_실패한다(self, icons_run):
        assert icons_run.summary["pass"] == 0, (
            "접근성 이름이 하나도 없는데 통과한 케이스가 있다 — "
            "그 케이스는 아무것도 확인하지 않았을 가능성이 높다"
        )

    def test_구현_결함으로_보고하지_않는다(self, icons_run):
        """도구가 못 찾은 것을 '기획서와 다름' 으로 두면 없는 결함이 된다."""
        cats = [v.failure_category for v in icons_run.cases if v.verdict == "FAIL"]
        assert cats.count("element_not_found") >= 14, (
            "탐지 실패가 다른 분류로 새고 있다: " + str(sorted(set(cats)))
        )

    def test_검증_로직은_good_과_같다(self, icons_run, good_run):
        """변수는 '접근성 이름이 없다' 하나뿐이다 — 케이스 구성이 달라지면 안 된다."""
        assert icons_run.summary["total"] == good_run.summary["total"]
