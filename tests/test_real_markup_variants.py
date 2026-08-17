"""실물 웹앱의 흔한 마크업 세 가지 — 도구가 어떻게 반응하는가.

## 왜 이 파일이 있는가

`sut/` 는 우리가 만든 앱이다. 폼 하나에 `id` 가 기획서의 `element_id` 와 같고,
`novalidate` 가 붙어 있고, 성공하면 서버가 리다이렉트한다. **실물 앱은 그렇지 않다.**

세 변형으로 잰다. 셋 다 서버 검증 로직은 `good` 과 **완전히 같고** 마크업 변수 하나만
다르다 — `nolabel`·`slow` 와 같은 원칙이다.

    spa      성공해도 URL 이 바뀌지 않는다 (클라이언트 라우팅)
    hashed   id 가 CSS-in-JS 해시다 (React/Vue 에서 흔하다)
    native   novalidate 를 떼고 required 를 붙였다 (브라우저가 제출을 막는다)

## 재는 것이 '판정이 맞는가' 만은 아니다

세 변형 중 둘은 **FAIL 이 맞다.** 기획서가 `/dashboard` 로 이동한다고 적었고 필수 입력
문구를 노출한다고 적었으므로, 그렇게 하지 않는 구현은 기획서와 다르다.

그래서 이 파일이 주로 확인하는 것은 **사유가 개발자에게 쓸모 있는가** 다. 판정이 맞아도
사유가 엉뚱하면 개발자가 엉뚱한 코드를 고친다. 그리고 실제로 하나는 사유가 **거꾸로**
였다 — `native` 에서 '구현이 이 규칙을 강제하지 않는다' 고 했는데, 브라우저가 `required`
때문에 막은 것이므로 구현은 그 규칙을 강제한다.

## 측정해서 '고칠 것이 없다' 도 결과다

`hashed` 는 아무 영향이 없었다. 라벨 전략이 먼저 통하므로 `element_id` 로 만드는 CSS
selector 가 필요하지 않다. 가정이 맞았지만 **재 봤으니 이제 아는 것**이고, 나중에 탐지
전략 순서를 바꿀 때 이 테스트가 그 사실을 지킨다.
"""

from __future__ import annotations

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline

LOGIN_PDF = "fixtures/specs/login_spec.pdf"


def _run(variant: str, sut_base: str, tmp_path):
    report, _ = run_pipeline(
        pdf_path=LOGIN_PDF,
        base_url=f"{sut_base}/{variant}",
        llm=MockLLM.for_spec(LOGIN_PDF),
        run_id=f"test-markup-{variant}",
        runs_root=tmp_path,
    )
    return report


@pytest.fixture(scope="module")
def spa(sut_base, tmp_path_factory):
    return _run("spa", sut_base, tmp_path_factory.mktemp("spa"))


@pytest.fixture(scope="module")
def hashed(sut_base, tmp_path_factory):
    return _run("hashed", sut_base, tmp_path_factory.mktemp("hashed"))


@pytest.fixture(scope="module")
def native(sut_base, tmp_path_factory):
    return _run("native", sut_base, tmp_path_factory.mktemp("native"))


class TestHashedIds:
    """id 가 해시여도 라벨로 찾는다 — 전략 네 개 중 마지막만 막힌다."""

    def test_판정이_good과_같다(self, hashed):
        s = hashed.summary
        assert (s["pass"], s["fail"]) == (10, 0), "\n".join(
            f"  {v.title}: {v.failure_detail}"
            for v in hashed.cases if v.verdict == "FAIL"
        )

    def test_요소를_못_찾은_케이스가_없다(self, hashed):
        """element_id 전략에 의존했다면 여기서 element_not_found 가 쏟아진다."""
        assert not [v for v in hashed.cases
                    if v.failure_category == "element_not_found"]

    def test_selector로_찾는다(self, hashed):
        """2차 경로(이미지)로 넘어가지 않았다는 확인. 넘어갔다면 접근성 속성이
        아니라 좌표로 조작한 것이고, 그건 다른 상태다."""
        assert hashed.summary["healed"] == 0


class TestSpaRouting:
    """URL 이 안 바뀌면 FAIL 이 맞다 — 확인하는 것은 사유다."""

    def test_정상_로그인만_실패한다(self, spa):
        """규칙 검증은 good 과 같으므로 그 케이스들은 통과해야 한다. 성공 조건만
        걸리는 것이 맞다 — 하나가 여러 건으로 번지면 리포트가 규모를 왜곡한다."""
        failed = [v for v in spa.cases if v.verdict == "FAIL"]
        assert len(failed) == 1, [v.case_id for v in failed]
        assert failed[0].case_id.endswith("valid-001")

    def test_사유가_경로와_문구를_모두_말한다(self, spa):
        """**이 클래스의 핵심.** '경로 미이동' 만 말하면 개발자가 로그인 로직을
        뒤진다. '문구는 노출 확인' 이 함께 있어야 로그인은 되고 라우팅이 문제라는
        것을 안다."""
        case = next(v for v in spa.cases if v.verdict == "FAIL")
        detail = case.failure_detail
        assert "미이동" in detail
        assert "노출 확인" in detail, detail

    def test_실제로_간_곳을_남긴다(self, spa):
        case = next(v for v in spa.cases if v.verdict == "FAIL")
        assert "/spa/login" in case.failure_detail

    def test_분류가_구현_불일치다(self, spa):
        """element_not_found 로 분류되면 '도구가 못 찾았다' 로 읽힌다. 여기서는
        도구가 정확히 관찰했고 구현이 기획서와 다르다."""
        case = next(v for v in spa.cases if v.verdict == "FAIL")
        assert case.failure_category == "assertion_mismatch"


class TestNativeValidation:
    """**사유가 거꾸로였던 곳.**

    브라우저가 required 때문에 제출을 막으면 화면에 앱의 에러 문구가 없다. 도구는
    그걸 보고 '구현이 이 규칙을 강제하지 않는다' 고 단정했다 — 사실과 반대다.
    구현은 강제한다. 오히려 더 이르게 막는다. 방법이 기획서와 다를 뿐이다.

    검색 화면의 대소문자 결함과 같은 모양이다 — 검사 자체는 하는데 검사 방법이
    기획서와 다르다. 그건 '검증이 없다' 와 고칠 곳이 다르다.
    """

    def test_필수_입력_케이스만_실패한다(self, native):
        s = native.summary
        assert (s["pass"], s["fail"]) == (8, 2), "\n".join(
            f"  {v.title}: {v.failure_detail}"
            for v in native.cases if v.verdict == "FAIL"
        )
        assert {v.violates for v in native.cases if v.verdict == "FAIL"} == {"required"}

    def test_강제하지_않는다고_말하지_않는다(self, native):
        """이 문장이 남아 있으면 개발자가 이미 있는 검증을 또 추가한다."""
        for case in native.cases:
            if case.verdict == "FAIL":
                assert "강제하지 않는다" not in case.failure_detail, case.failure_detail

    def test_브라우저가_막았다고_말한다(self, native):
        for case in native.cases:
            if case.verdict == "FAIL":
                assert "브라우저 기본 검증" in case.failure_detail

    def test_고치는_방법을_알려준다(self, native):
        """'다르다' 만 말하면 개발자가 무엇을 해야 할지 모른다. 이 경우 선택지가
        둘이다 — 문구를 직접 노출하거나 기획서를 고치는 것."""
        case = next(v for v in native.cases if v.verdict == "FAIL")
        assert "novalidate" in case.failure_detail
        assert "기획서를 고쳐야" in case.failure_detail

    def test_판정은_FAIL로_남는다(self, native):
        """사유를 고친 것이 판정을 무르게 하면 안 된다. 기획서는 그 문구를
        노출한다고 적었고 구현은 노출하지 않는다 — 불일치는 실재한다."""
        assert native.summary["fail"] == 2


class TestGoodUnaffected:
    def test_good_판정이_그대로다(self, sut_base, tmp_path):
        """변형을 추가하려고 템플릿을 건드렸다. good 이 달라지면 확장이 아니라
        회귀다 (안내 문구 조건과 id·required 분기를 모두 손댔다)."""
        report = _run("good", sut_base, tmp_path)
        assert (report.summary["pass"], report.summary["fail"]) == (10, 0)

    def test_bad_판정이_그대로다(self, sut_base, tmp_path):
        report = _run("bad", sut_base, tmp_path)
        assert (report.summary["pass"], report.summary["fail"]) == (4, 6)

    def test_bad_사유가_바뀌지_않았다(self, sut_base, tmp_path):
        """bad 는 브라우저가 막지 않는다(novalidate 가 있다). 그러니 예전 사유가
        그대로 나와야 한다 — 새 분기가 엉뚱한 케이스를 잡으면 안 된다."""
        report = _run("bad", sut_base, tmp_path)
        assert not any("브라우저 기본 검증" in v.failure_detail
                       for v in report.cases if v.verdict == "FAIL")
