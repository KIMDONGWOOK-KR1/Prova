"""비밀번호 변경 화면 — `require_lowercase` 와 `require_digit` 를 처음 쓰는 화면.

## 이 화면이 새로 확인하는 것

두 규칙은 `rule_expander` 가 처음부터 지원했는데 **쓰는 기획서가 하나도 없었다.**
가입 화면의 비밀번호 규칙이 8자·대문자·특수문자 셋뿐이어서다.

코드에 있고 아무도 쓰지 않는 기능은 동작한다는 증거가 없다 — 이 저장소가
반복해서 치른 값이다(있는 것과 동작하는 것은 다르다). 이 화면이 그 증거를 만든다.

## 한 요소에 규칙 다섯, 그중 둘만 빠뜨린다

새 비밀번호에 규칙이 다섯(길이·대문자·소문자·숫자·특수문자)인데 bad 는 소문자와
숫자만 빠뜨린다. 나머지 셋은 구현돼 있다.

'규칙 하나당 케이스 하나' 설계가 없으면 이 모양은 보이지 않는다 — 규칙을 묶어
한 케이스로 검사하면 길이가 먼저 걸려 에러가 뜨고, **소문자 검증이 없다는 사실이
가려진다.** 닉네임 최대 길이(C3)에서 배운 것과 같은 자리다.

    I1  소문자 포함 검증 없음            새 규칙 종류
    I2  숫자 포함 검증 없음              새 규칙 종류
    I3  새 비밀번호 확인 일치 검증 없음  대조군 (가입 C1 과 같은 종류)

## 현재 비밀번호 확인을 마지막에 하는 이유

새 비밀번호가 규칙을 어겼는데 '현재 비밀번호가 틀렸다' 가 먼저 뜨면, 고쳐야 할
곳을 사람이 잘못 찾는다. 기획서 §4 의 표 순서가 그래서 그렇게 돼 있다.
"""

from __future__ import annotations

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline

SPEC_PDF = "fixtures/specs/change_password_spec.pdf"


def _run(variant: str, sut_base: str, tmp_path):
    report, _ = run_pipeline(
        pdf_path=SPEC_PDF,
        base_url=f"{sut_base}/{variant}",
        llm=MockLLM.for_spec(SPEC_PDF),
        run_id=f"test-chgpw-{variant}",
        runs_root=tmp_path,
    )
    return report


@pytest.fixture(scope="module")
def good_run(sut_base, tmp_path_factory):
    return _run("good", sut_base, tmp_path_factory.mktemp("chgpw-good"))


@pytest.fixture(scope="module")
def bad_run(sut_base, tmp_path_factory):
    return _run("bad", sut_base, tmp_path_factory.mktemp("chgpw-bad"))


@pytest.fixture(scope="module")
def icons_run(sut_base, tmp_path_factory):
    return _run("icons", sut_base, tmp_path_factory.mktemp("chgpw-icons"))


class TestGoodVariant:
    def test_전_케이스_통과(self, good_run):
        failures = [v for v in good_run.cases if v.verdict == "FAIL"]
        assert not failures, (
            "기획서 준수 구현에서 실패가 났다 — 오탐이다:\n"
            + "\n".join(f"  {v.title}: {v.failure_detail}" for v in failures)
        )

    def test_새_규칙_둘이_케이스로_전개된다(self, good_run):
        """이 화면을 만든 이유다. 케이스가 안 생기면 규칙이 있으나 마나다."""
        rules = {v.violates for v in good_run.cases if v.violates}
        assert "require_lowercase" in rules, "소문자 규칙의 위반 케이스가 없다"
        assert "require_digit" in rules, "숫자 규칙의 위반 케이스가 없다"

    def test_한_요소의_규칙_다섯이_각각_갈린다(self, good_run):
        """묶어서 검사하면 빠진 규칙 하나가 다른 규칙에 가려진다."""
        new_pw = {v.violates for v in good_run.cases
                  if v.target_element == "new_password" and v.violates}
        assert new_pw == {"required", "min_length", "require_uppercase",
                          "require_lowercase", "require_digit", "require_special"}


class TestBadVariant:
    def test_빠뜨린_규칙_셋만_잡는다(self, bad_run):
        rules = {v.violates for v in bad_run.cases if v.verdict == "FAIL"}
        assert rules == {"require_lowercase", "require_digit", "same_as"}, (
            "I1·I2·I3 만 잡혀야 한다: " + str(sorted(rules))
        )

    def test_구현된_규칙은_통과한다(self, bad_run):
        """같은 요소의 길이·대문자·특수문자는 bad 에도 구현돼 있다."""
        for rule in ("min_length", "require_uppercase", "require_special"):
            v = next(v for v in bad_run.cases if v.violates == rule)
            assert v.verdict == "PASS", f"{rule} 은 bad 에도 구현돼 있다"

    def test_오탐이_없다(self, bad_run):
        assert bad_run.summary["fail"] == 3, "\n".join(
            f"  {v.verdict} {v.title}" for v in bad_run.cases)


class TestIconsVariant:
    """2차 경로(VLM)가 살려내야 할 화면."""

    def test_1차_경로만으로는_전부_실패한다(self, icons_run):
        assert icons_run.summary["pass"] == 0

    def test_구현_결함으로_보고하지_않는다(self, icons_run):
        cats = [v.failure_category for v in icons_run.cases if v.verdict == "FAIL"]
        assert cats.count("element_not_found") >= 10, (
            "탐지 실패가 다른 분류로 새고 있다: " + str(sorted(set(cats)))
        )

    def test_검증_로직은_good_과_같다(self, icons_run, good_run):
        assert icons_run.summary["total"] == good_run.summary["total"]
