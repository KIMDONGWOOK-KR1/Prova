"""회원가입 화면 관통 테스트 — 2차 확장의 수용 기준.

## 로그인 화면과 무엇이 다른가

로그인은 요소 2개가 모두 텍스트 입력이고, 규칙이 값 하나만 보면 판정되는
것들이었다. 회원가입은 세 가지가 새로 들어온다.

    체크박스   fill() 이 통하지 않는다 -> check / uncheck 액션
    선택       고를 값이 constraints 가 아니라 options 에 있다
    교차 필드   '비밀번호 확인' 은 다른 요소의 값과 같아야 한다 (same_as)

세 번째가 가장 무겁다. 값 생성이 요소 단위로 끝나지 않고 의존 순서를 따라야
하고, 위반 케이스를 만들 때 그 의존을 다시 풀어야 '한 케이스는 한 규칙만
위반한다' 는 계약이 유지된다.

## 심어 둔 불일치는 로그인과 다른 종류를 골랐다 (sut/app.py 참고)

    C1  same_as   비밀번호 확인 일치 검증 미구현  (교차 필드)
    C2  required  약관 동의 필수 검증 미구현      (체크박스 상태)
    C3  max_length 닉네임 최대 길이 검증 누락    (한 요소의 규칙 중 일부만 구현)

같은 종류의 결함을 한 번 더 심으면 화면을 늘린 만큼의 검증력을 얻지 못한다.
"""

from __future__ import annotations

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline

SPEC_PDF = "fixtures/specs/signup_spec.pdf"

# 심어 둔 불일치를 (요소, 규칙) 쌍으로 적는다.
#
# 규칙 이름만으로는 부족하다. 회원가입 화면에는 required 규칙을 가진 요소가
# 6개이고, 그중 약관 동의 하나만 검증이 빠져 있다. 'required 가 FAIL' 로만
# 대조하면 나머지 5개가 PASS 인지 확인할 수 없어, 오탐 검증이 헐거워진다.
EXPECTED_BAD_FAILURES = {
    ("password_confirm", "same_as"),    # C1
    ("agree_terms", "required"),        # C2
    ("nickname", "max_length"),         # C3
}


def _run(variant: str, sut_base: str, tmp_path):
    report, run_dir = run_pipeline(
        pdf_path=SPEC_PDF,
        base_url=f"{sut_base}/{variant}",
        llm=MockLLM.for_spec(SPEC_PDF),
        run_id=f"test-signup-{variant}",
        runs_root=tmp_path,
    )
    return report, run_dir


def _failures(report) -> set[tuple[str, str]]:
    return {
        (v.target_element, v.violates)
        for v in report.cases
        if v.verdict == "FAIL" and v.type == "negative"
    }


@pytest.fixture(scope="module")
def good_run(sut_base, tmp_path_factory):
    return _run("good", sut_base, tmp_path_factory.mktemp("signup-good"))


@pytest.fixture(scope="module")
def bad_run(sut_base, tmp_path_factory):
    return _run("bad", sut_base, tmp_path_factory.mktemp("signup-bad"))


class TestGoodVariant:
    """기획서를 지킨 구현은 전부 통과해야 한다."""

    def test_전_케이스_통과(self, good_run):
        report, _ = good_run
        failures = [v for v in report.cases if v.verdict == "FAIL"]
        assert not failures, (
            "기획서 준수 구현에서 실패가 났다 — 오탐이다:\n"
            + "\n".join(
                f"  [{v.target_element}/{v.violates}] {v.failure_detail}"
                for v in failures
            )
        )
        assert report.summary["pass_rate"] == 100.0

    def test_케이스가_규칙_수만큼_생성됐다(self, good_run):
        """0건 통과를 100% 통과로 착각하지 않게 한다.

        정상 1건 + 위반 13건:
            email            required, format                                = 2
            password         required, min_length, upper, special             = 4
            password_confirm required, same_as                                = 2
            nickname         required, min_length, max_length                 = 3
            signup_path      required                                         = 1
            agree_terms      required                                         = 1
        """
        report, _ = good_run
        assert report.summary["total"] == 17
        assert sum(1 for v in report.cases if v.type == "negative") == 13

    def test_기획서_결함_경고가_없다(self, good_run):
        """same_as 참조 실패나 빈 선택 목록 같은 기획서 결함이 없어야 한다.
        경고가 있으면 케이스 값이 엉뚱하게 생성됐을 수 있다.

        제목 다듬기 경고는 제외한다 — mock 백엔드에 CaseTitles 응답이 없어서
        나는 것이고, 기획서 결함이 아니다. 그 경고가 남는 것 자체는 옳다
        (제목이 다듬어지지 않은 이유를 리포트에서 알 수 있어야 한다).
        """
        report, _ = good_run
        defects = [w for w in report.summary.get("spec_warnings", [])
                   if "제목 다듬기" not in w]
        assert defects == [], f"기획서 결함 경고: {defects}"

    def test_체크박스와_선택_요소를_찾았다(self, good_run):
        """새 요소 유형이 selector 탐지에 걸리는지 — 확장의 전제 조건."""
        report, _ = good_run
        actions = {
            (r.action, r.location.strategy)
            for v in report.cases for r in v.step_results if r.location
        }
        assert ("check", "label") in actions, "체크박스를 라벨로 찾지 못했다"
        assert ("select", "label") in actions, "선택 요소를 라벨로 찾지 못했다"
        assert ("uncheck", "label") in actions, "체크 해제 스텝이 없다"


class TestBadVariant:
    """의도적 불일치를 정확히 짚어내야 한다."""

    def test_심어둔_불일치를_모두_잡는다(self, bad_run):
        report, _ = bad_run
        missed = EXPECTED_BAD_FAILURES - _failures(report)
        assert not missed, f"놓친 불일치(미탐): {missed}"

    def test_오탐이_없다(self, bad_run):
        """심지 않은 항목이 FAIL 로 나오면 안 된다. 오탐은 미탐보다 치명적이다."""
        report, _ = bad_run
        false_positives = _failures(report) - EXPECTED_BAD_FAILURES
        assert not false_positives, f"오탐: {false_positives}"

    def test_구현된_필수검증은_통과한다(self, bad_run):
        """bad 에도 텍스트 입력·선택의 필수 검증은 있다. 같은 리포트 안에
        '구현된 규칙은 PASS, 누락된 규칙은 FAIL' 이 함께 나와야 판정을 신뢰할 수
        있다. 특히 required 규칙 6건 중 5건이 PASS 여야 한다 — 하나만 빠졌다는
        사실을 요소 단위로 짚어내는 것이 이 확장의 핵심이다."""
        report, _ = bad_run
        required = [v for v in report.cases if v.violates == "required"]
        assert len(required) == 6
        passed = {v.target_element for v in required if v.verdict == "PASS"}
        assert passed == {"email", "password", "password_confirm",
                          "nickname", "signup_path"}

    def test_정상_가입은_통과한다(self, bad_run):
        """검증 로직이 빠졌어도 정상 경로는 동작한다. 이게 FAIL 이면
        테스트 데이터나 탐지 문제이지 불일치 탐지가 아니다."""
        report, _ = bad_run
        positive = next(v for v in report.cases if v.type == "positive")
        assert positive.verdict == "PASS", positive.failure_detail

    def test_닉네임_하한은_통과하고_상한만_실패한다(self, bad_run):
        """C3 의 핵심. 한 요소의 규칙 중 일부만 구현된 경우를 규칙 단위로
        분리해 짚어내는지 확인한다. min/max 를 한 케이스로 묶었다면 min 쪽이
        걸려 에러가 뜨고, max 검증이 없다는 사실은 가려진다."""
        report, _ = bad_run
        by_rule = {
            v.violates: v.verdict
            for v in report.cases if v.target_element == "nickname"
        }
        assert by_rule["min_length"] == "PASS"
        assert by_rule["max_length"] == "FAIL"

    def test_실패에_요소와_규칙이_함께_붙는다(self, bad_run):
        """개발자가 어느 요소의 어느 검증을 추가해야 하는지 알 수 있어야 한다."""
        report, _ = bad_run
        for v in (c for c in report.cases
                  if c.verdict == "FAIL" and c.type == "negative"):
            assert v.violates, f"{v.case_id}: 위반 규칙이 없다"
            assert v.target_element, f"{v.case_id}: 대상 요소가 없다"
            assert v.failure_category, f"{v.case_id}: 실패 분류가 없다"


class TestCrossFieldRule:
    """same_as — 값 하나만 보고는 판정할 수 없는 규칙."""

    def test_위반값은_참조값과_다르다(self, good_run):
        report, _ = good_run
        case = next(v for v in report.cases if v.violates == "same_as")
        values = {
            r.target: r for r in case.step_results if r.action == "fill"
        }
        assert "비밀번호" in values and "비밀번호 확인" in values

    def test_비밀번호_위반_케이스에서는_확인값도_함께_바뀐다(self, good_run):
        """이게 '한 케이스는 한 규칙만 위반한다' 계약을 지키는 지점이다.

        비밀번호에 위반값을 넣고 비밀번호 확인을 원래 값으로 두면 일치 규칙까지
        함께 깨져, FAIL 원인이 '비밀번호 규칙 미구현' 인지 '일치 검증 미구현'
        인지 갈리지 않는다. good 구현에서 기대 문구가 비밀번호 규칙 문구로
        나오는 것이 그 증거다 (일치 문구가 나왔다면 값이 어긋난 것이다)."""
        report, _ = good_run
        case = next(v for v in report.cases
                    if v.violates == "require_uppercase")
        assert case.verdict == "PASS", case.failure_detail
        assert "대문자" in case.evidence["expected"]
