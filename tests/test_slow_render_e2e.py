"""결과가 늦게 나타나는 화면 — 도구가 못 기다린 것을 구현 결함으로 단정하지 않는다.

## 무엇을 막는가 — 실측으로 확인한 오탐

지금까지 SUT 는 동기식 폼 POST 라 응답 HTML 에 결과가 이미 들어 있었다. 그래서 스텝이
끝나면 곧바로 DOM 을 읽고 판정해도 통했다.

**실물 웹앱은 대개 그렇지 않다.** 제출하면 fetch 를 보내고, 응답이 오면 화면을 갈아
끼운다. 그 사이 화면에는 아무것도 없다.

`slow` 변형은 그 상황을 변수 하나만 바꿔 재현한다 — 검증 로직·문구·마크업이 `good` 과
완전히 같고, 서버가 보낸 결과를 브라우저가 400ms 뒤에 DOM 에 넣는다. 이 변형으로 재 보니
**오탐 7건**이 났고 사유가 이렇게 나왔다.

    기획서에 적힌 'password' 의 'require_uppercase' 검증 규칙이 구현에서
    확인되지 않았습니다. (에러가 전혀 노출되지 않음 — 구현이 이 규칙을 강제하지 않는다)

구현은 그 규칙을 강제한다. **도구가 못 기다린 것을 구현 결함으로 단정했다.**

## 이 파일이 지키는 세 성질

    1. slow 판정이 good 과 같아진다        오탐을 만들지 않는다
    2. bad 판정은 그대로다                 대기가 결함 탐지를 무르게 하지 않는다
    3. 기다린 사실이 근거에 남는다          편의가 사실을 지우지 않는다

**2번이 가장 중요하다.** 대기는 FAIL 을 PASS 로 바꿀 수 있고 그 반대는 없다. 그 방향성이
결함을 덮는 데 쓰이면 이 도구의 값이 사라진다.

## 왜 'DOM 이 안정될 때까지' 가 아닌가

그쪽이 판정과 독립적이라 더 깔끔해 보였다. 그런데 성립하지 않는다 — 400ms 뒤에 렌더하는
화면은 그 전 250ms 동안 아무 변화가 없고, 그 정적을 '안정됐다' 로 읽는다. **아직
시작하지 않은 것과 끝난 것을 구분할 수 없다.**
"""

from __future__ import annotations

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline

LOGIN_PDF = "fixtures/specs/login_spec.pdf"
SEARCH_PDF = "fixtures/specs/search_spec.pdf"

# 단일 문서 실행의 기대값. slow 는 good 과 같아야 한다.
EXPECTED = {
    ("login", "good"): (10, 0),
    ("login", "slow"): (10, 0),
    ("login", "bad"): (4, 6),
    ("search", "good"): (10, 0),
    ("search", "slow"): (10, 0),
    ("search", "bad"): (6, 4),
}


def _run(screen: str, variant: str, sut_base: str, tmp_path, **kwargs):
    pdf = LOGIN_PDF if screen == "login" else SEARCH_PDF
    report, _ = run_pipeline(
        pdf_path=pdf,
        base_url=f"{sut_base}/{variant}",
        llm=MockLLM.for_spec(pdf),
        run_id=f"test-slow-{screen}-{variant}",
        runs_root=tmp_path,
        **kwargs,
    )
    return report


@pytest.fixture(scope="module")
def slow_login(sut_base, tmp_path_factory):
    return _run("login", "slow", sut_base, tmp_path_factory.mktemp("slow-login"))


@pytest.fixture(scope="module")
def slow_search(sut_base, tmp_path_factory):
    return _run("search", "slow", sut_base, tmp_path_factory.mktemp("slow-search"))


class TestNoFalsePositives:
    """slow 는 검증 로직이 good 과 같다 — 판정도 같아야 한다."""

    def test_로그인_판정이_good과_같다(self, slow_login):
        s = slow_login.summary
        assert (s["pass"], s["fail"]) == EXPECTED[("login", "slow")], "\n".join(
            f"  {v.title}: {v.failure_detail}"
            for v in slow_login.cases if v.verdict == "FAIL"
        )

    def test_검색_판정이_good과_같다(self, slow_search):
        s = slow_search.summary
        assert (s["pass"], s["fail"]) == EXPECTED[("search", "slow")], "\n".join(
            f"  {v.title}: {v.failure_detail}"
            for v in slow_search.cases if v.verdict == "FAIL"
        )

    def test_없는_결함을_단정하지_않는다(self, slow_login):
        """실패 사유가 '구현이 이 규칙을 강제하지 않는다' 였다. 그건 단정이고
        틀린 단정이었다 — 구현은 강제한다."""
        wrong = [v for v in slow_login.cases
                 if v.verdict == "FAIL" and "강제하지 않는다" in v.failure_detail]
        assert not wrong, [v.case_id for v in wrong]


class TestEvidenceKept:
    """기다렸다는 사실이 남아야 한다 — 편의가 사실을 지우지 않는다."""

    def test_기다린_케이스가_있다(self, slow_login):
        """하나도 없으면 이 파일이 아무것도 확인하지 않는다는 뜻이다 —
        렌더 지연이 실제로 판정에 영향을 주는 구간에 있는지 보증한다."""
        waited = [v for v in slow_login.cases if v.evidence.get("settled_ms")]
        assert waited, "지연이 판정에 닿지 않았다면 이 시험은 무의미하다"

    def test_기다린_시간을_남긴다(self, slow_login):
        """'이 화면은 결과를 늦게 보여준다' 는 사실이다. 지우면 리포트를 읽는
        사람이 통과의 성질을 알 수 없다."""
        waited = [v.evidence["settled_ms"] for v in slow_login.cases
                  if v.evidence.get("settled_ms")]
        assert all(ms > 0 for ms in waited)
        # SUT 의 지연은 400ms 다. 그보다 훨씬 큰 값이 나오면 대기가 지연 때문이
        # 아니라 다른 이유로 걸린 것이고, 그건 다른 문제다.
        assert max(waited) <= 1500, waited

    def test_good은_기다리지_않는다(self, sut_base, tmp_path):
        """동기식 화면에 대기 비용을 물리면 안 된다. 첫 판정에서 통과하면
        기다리지 않는다."""
        report = _run("login", "good", sut_base, tmp_path)
        assert report.summary["fail"] == 0
        assert not [v for v in report.cases if v.evidence.get("settled_ms")]


class TestDefectDetectionUnchanged:
    """**이 파일에서 가장 중요한 확인.**

    대기는 FAIL 을 PASS 로 바꿀 수 있고 그 반대는 없다. 그 방향성이 결함을 덮는 데
    쓰이면 이 도구의 값이 사라진다.
    """

    def test_bad_로그인_판정이_그대로다(self, sut_base, tmp_path):
        report = _run("login", "bad", sut_base, tmp_path)
        s = report.summary
        assert (s["pass"], s["fail"]) == EXPECTED[("login", "bad")]

    def test_bad_검색_판정이_그대로다(self, sut_base, tmp_path):
        report = _run("search", "bad", sut_base, tmp_path)
        s = report.summary
        assert (s["pass"], s["fail"]) == EXPECTED[("search", "bad")]

    def test_기다려도_통과하지_못하면_FAIL로_남는다(self, sut_base, tmp_path):
        """상한을 넘으면 마지막 판정을 그대로 보고한다. 통과할 때까지 무한정
        기다리면 진짜 결함이 전부 사라진다."""
        report = _run("login", "bad", sut_base, tmp_path)
        failed = [v for v in report.cases if v.verdict == "FAIL"]
        assert failed
        assert not any(v.evidence.get("settled_ms") for v in failed), (
            "실패한 케이스에 settled_ms 가 있으면 '기다려서 통과했다' 는 뜻이다"
        )


class TestWaitDisabled:
    def test_대기를_끄면_오탐이_돌아온다(self, sut_base, tmp_path):
        """대기가 실제로 오탐을 막고 있다는 증거다. 이 확인이 없으면 slow 가
        통과하는 이유가 대기 때문인지 다른 이유인지 알 수 없다."""
        report = _run("login", "slow", sut_base, tmp_path, settle_timeout_ms=0)
        assert report.summary["fail"] > 0, (
            "대기를 껐는데도 통과한다면 이 지연이 판정에 닿지 않는다는 뜻이고, "
            "그러면 slow 변형이 아무것도 시험하지 않는다"
        )
