"""비밀번호 찾기 화면 — '없어야 할 것이 없는가' 를 확인하는 첫 화면.

## 이 화면을 왜 마지막에 했나

명세서 §0-2 의 1차 범위에 네 화면이 있고 이게 네 번째다. 앞서 '기존 기계로 대부분 덮인다 —
이메일 형식 검증과 에러 문구 대조가 대부분이어서 로그인의 부분집합' 이라고 판단해 미뤘다.

그 판단은 반쯤 맞았다. 입력 검증은 실제로 로그인의 부분집합이다. 그런데 **이 화면에는
지금까지 없던 종류의 요구사항이 있다.**

## 새로운 것 — 방향이 반대인 요구사항

기획서 §5 가 보안 요구사항을 적는다.

    계정 존재 여부를 알려주지 않는다. 입력한 이메일이 등록되어 있든 없든 화면의
    반응은 완전히 같아야 한다.

등록 여부에 따라 다른 문구를 노출하면 공격자가 이 화면으로 어떤 이메일이 가입되어 있는지
확인할 수 있다(account enumeration). **실제 취약점이다.**

지금까지의 검증은 전부 '있어야 할 것이 있는가' 였다. 이건 반대다 —
**'없어야 할 것이 없는가'.** 그래서 `Scenario.expect_absent` 와 판정 유형
`text_absent` 를 새로 뒀다.

`expect_text` 로 표현할 수 없다. 성공 문구가 떠 있으면서 금지 문구도 함께 떠 있는 화면이
가능하고, 그 화면은 요구를 어긴다. 있어야 할 것과 없어야 할 것은 다른 확인이다.

## 심어 둔 결함

    F1  bad 는 미등록 이메일에 '등록되지 않은 이메일입니다.' 를 노출한다

검증 규칙(필수·형식)은 good/bad 가 동일하다. 변수를 하나로 두기 위해서다 — 규칙 검증까지
빼면 이 화면이 확인하려는 F1 이 다른 FAIL 에 섞인다.

## F1 이 FAIL 2건인 이유

    scenario-005  성공 문구가 안 뜬다        <- 기능 관점
    absent-005    금지 문구가 뜬다           <- 보안 관점

중복 보고가 아니다. 두 경로는 서로를 대신하지 못한다 — 구현이 성공 문구를 **함께** 노출하면
(즉 '보냈습니다' 와 '등록되지 않았습니다' 를 둘 다 띄우면) 앞의 경로는 통과하고 뒤의 경로만
잡는다. 검색 화면의 대소문자 결함과 같은 구조다.
"""

from __future__ import annotations

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline

SPEC_PDF = "fixtures/specs/find_account_spec.pdf"


def _run(variant: str, sut_base: str, tmp_path):
    report, run_dir = run_pipeline(
        pdf_path=SPEC_PDF,
        base_url=f"{sut_base}/{variant}",
        llm=MockLLM.for_spec(SPEC_PDF),
        run_id=f"test-find-{variant}",
        runs_root=tmp_path,
    )
    return report


@pytest.fixture(scope="module")
def good_run(sut_base, tmp_path_factory):
    return _run("good", sut_base, tmp_path_factory.mktemp("find-good"))


@pytest.fixture(scope="module")
def bad_run(sut_base, tmp_path_factory):
    return _run("bad", sut_base, tmp_path_factory.mktemp("find-bad"))


class TestGoodVariant:
    def test_전_케이스_통과(self, good_run):
        failures = [v for v in good_run.cases if v.verdict == "FAIL"]
        assert not failures, (
            "기획서 준수 구현에서 실패가 났다 — 오탐이다:\n"
            + "\n".join(f"  {v.title}: {v.failure_detail}" for v in failures)
        )

    def test_케이스_구성(self, good_run):
        """정상 1 + 규칙 위반 2 + 예시 문구 2 + 금지 문구 2 + 안내 문구 1 + 라벨 1 = 9건."""
        report = good_run
        assert report.summary["total"] == 9
        absent = [v for v in report.cases if "-absent-" in v.case_id]
        assert len(absent) == 2, "예시 두 행에서 금지 문구 케이스가 각각 나와야 한다"

    def test_기획서_결함_경고가_없다(self, good_run):
        defects = [w for w in good_run.summary.get("spec_warnings", [])
                   if "제목 다듬기" not in w]
        assert defects == [], f"기획서 결함 경고: {defects}"

    def test_등록_여부와_무관하게_같은_문구다(self, good_run):
        """기획서 §5 의 요구사항 그 자체. 두 예시가 같은 기대 문구를 갖는다."""
        texts = {v.evidence["expected"] for v in good_run.cases
                 if "-scenario-" in v.case_id}
        assert len(texts) == 1, texts


class TestForbiddenText:
    """**이 파일의 핵심.** 방향이 반대인 확인이 실제로 동작하는가."""

    def test_금지_문구_노출을_잡는다(self, bad_run):
        """F1 — 이게 실패하면 새 판정 유형이 아무것도 안 하는 것이다."""
        case = next(v for v in bad_run.cases if v.case_id.endswith("absent-005"))
        assert case.verdict == "FAIL"
        assert "노출되면 안 되는 문구" in case.failure_detail
        assert "등록되지 않은 이메일입니다." in case.failure_detail

    def test_등록된_이메일에서는_통과한다(self, bad_run):
        """누출은 미등록 이메일에서만 일어난다. 등록된 이메일까지 실패하면
        판정이 '금지 문구가 있는가' 가 아니라 다른 것을 보고 있다는 뜻이다."""
        case = next(v for v in bad_run.cases if v.case_id.endswith("absent-004"))
        assert case.verdict == "PASS", case.failure_detail

    def test_good에서는_두_예시_모두_통과한다(self, good_run):
        absent = [v for v in good_run.cases if "-absent-" in v.case_id]
        assert all(v.verdict == "PASS" for v in absent)

    def test_사유가_노출된_문구를_말한다(self, bad_run):
        """'금지 문구가 있다' 만 말하면 개발자가 무엇을 지워야 할지 모른다."""
        case = next(v for v in bad_run.cases if v.case_id.endswith("absent-005"))
        assert "등록되지 않은" in case.failure_detail


class TestBadVariant:
    def test_결함_하나가_FAIL_두건이다(self, bad_run):
        """중복 보고가 아니다 — 구현이 성공 문구를 함께 노출하면 문구 경로는
        통과하고 금지 문구 경로만 잡는다. 두 경로는 서로를 대신하지 못한다."""
        report = bad_run
        assert (report.summary["pass"], report.summary["fail"]) == (7, 2), "\n".join(
            f"  {v.verdict} {v.title}" for v in report.cases
        )
        failed = {v.case_id.rsplit("-", 2)[-2] for v in report.cases
                  if v.verdict == "FAIL"}
        assert failed == {"scenario", "absent"}

    def test_입력_검증은_통과한다(self, bad_run):
        """good/bad 가 규칙 검증은 동일하다. 여기가 실패하면 변수가 둘이 된 것이고,
        그러면 F1 이 다른 FAIL 에 섞여 이 화면이 확인하려는 것을 못 본다."""
        rules = {v.violates: v.verdict for v in bad_run.cases if v.type == "negative"}
        assert rules == {"required": "PASS", "format": "PASS"}, rules

    def test_오탐이_없다(self, bad_run):
        """심은 결함은 F1 하나다."""
        assert bad_run.summary["fail"] == 2


class TestNoNavigation:
    """이 화면은 제출 후 이동하지 않는다 — 검색 화면과 같은 성질."""

    def test_같은_경로에_머문다(self, good_run):
        for v in good_run.cases:
            assert "/find-account" in v.evidence["url"], v.evidence["url"]
