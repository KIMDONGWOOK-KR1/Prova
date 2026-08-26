"""화면 셋을 지나는 흐름 — 관통 테스트.

## 왜 셋이어야 하는가

`Flow` 는 처음부터 화면 목록(N개)이었고 생성기도 일반 순회였지만, **실제로 셋을
밟아 본 적이 없었다.** 픽스처에 3화면 흐름이 하나도 없었으므로 "지원한다" 는
읽어서 내린 결론이었을 뿐이다. 여기서 실제로 밟는다.

셋이 되면서 처음 갈라지는 것이 있다. 전이가 둘이므로 이동 방법이 전이마다 다를
수 있고, 중간 화면 도착 확인이 여러 번 생기고, **끊긴 지점이 어디인지가 처음으로
애매해질 수 있다.** 마지막이 애먼 소리를 듣지 않는다는 보장은 2화면에서만
확인돼 있었다.

## 밟는 길

    가입 → 로그인 → 상품 등록

세 번째 화면이 **로그인 가드로 막혀 있다.** SUT 의 `/good/product` 는
`session_good` 쿠키가 없으면 로그인 화면으로 되돌린다. 그래서 이 흐름은 앞의 두
화면이 실제로 이어졌을 때만 마지막에 닿는다 — 흐름이 흐름인지를 마지막 화면이
스스로 증명한다.

## 흐름이 둘인 이유

`bad` 에 심어 둔 '화면 사이' 결함이 둘이고, 하나가 다른 하나를 가린다.

    E1  회원가입이 계정을 실제로 등록하지 않는다              -> 이어진 상태가 깨졌다
    E2  완료 화면의 '로그인하러 가기' 가 /search 를 가리킨다  -> 잇는 요소가 깨졌다

하나의 흐름으로 합치면 E2 가 첫 전이에서 스텝을 끊어 **E1 에 도달하지 못한다.**
스텝이 끊기면 이후 판정이 무의미하다는 규칙 때문이고 그 규칙은 옳다 — 대신
확인하려는 질문이 둘이면 흐름도 둘이어야 한다.

    signup_link_to_product   링크를 눌러 로그인 화면에 닿는가  -> E2 를 잡는다
    signup_state_to_product  그 계정으로 상품 등록까지 가는가  -> E1 을 잡는다

## 끊긴 자리를 정확히 지목하는가

이 파일의 핵심 수용 기준이다. E1 은 가입 화면의 잘못인데 **로그인 단계에서**
드러나고, E2 는 완료 화면의 잘못인데 **로그인 도착 확인에서** 드러난다. 둘 다
마지막 화면(상품 등록)의 잘못이 아니다. 마지막이 지목되면 개발자가 엉뚱한 코드를
뒤진다. 2화면에서는 '마지막 바로 앞' 이 곧 '첫 화면' 이라 이 구분이 느슨했다.

## 실행 순서에 대한 주의

SUT 의 계정 등록은 프로세스 상태다. good 을 두 번째로 돌리면 앞선 실행이 등록해
둔 계정으로 통과할 수 있다. 결함 탐지 방향(bad 가 어디서 끊기는가)은 이 영향을
받지 않는다 — bad 는 어떤 순서로도 등록하지 않는다.
"""

from __future__ import annotations

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline

SPEC_PDF = "fixtures/specs/onboarding_spec.pdf"

# 같은 화면 셋을 밟지만 확인하는 것이 다르다 — 하나로 합치면 앞의 잘못이 먼저
# 스텝을 끊어 뒤의 잘못이 가려진다.
LINK_FLOW = "signup_link_to_product"    # 화면을 잇는 요소 (E2)
STATE_FLOW = "signup_state_to_product"  # 이어진 상태 (E1)


def _run(variant: str, sut_base: str, tmp_path):
    report, run_dir = run_pipeline(
        pdf_path=SPEC_PDF,
        base_url=f"{sut_base}/{variant}",
        # 화면 하나에 기획서 하나를 등록한다 — product_spec.pdf 는 로그인과 상품
        # 등록 두 화면을 담지만 mock 은 화면 하나로만 등록하므로, 로그인은
        # login_spec.pdf 로 따로 준다 (test_product_e2e 와 같은 조합이다).
        llm=MockLLM.for_document(
            "fixtures/specs/signup_spec.pdf",
            "fixtures/specs/login_spec.pdf",
            "fixtures/specs/product_spec.pdf",
        ),
        run_id=f"test-onboarding-{variant}",
        runs_root=tmp_path,
    )
    return report, run_dir


@pytest.fixture(scope="module")
def good_run(sut_base, tmp_path_factory):
    return _run("good", sut_base, tmp_path_factory.mktemp("onboarding-good"))


@pytest.fixture(scope="module")
def bad_run(sut_base, tmp_path_factory):
    return _run("bad", sut_base, tmp_path_factory.mktemp("onboarding-bad"))


#: 화면별 기획서 하나로 돌렸을 때의 결과. 문서를 합친 것만으로 화면별 판정이
#: 달라지면 그건 확장이 아니라 후퇴다 (test_multi_screen_e2e 와 같은 이유).
EXPECTED_BY_SCREEN = {
    "good": {"signup": (17, 0), "login": (10, 0), "product": (10, 0)},
    "bad": {"signup": (13, 4), "login": (4, 6), "product": (8, 2)},
}


def _flow(report, flow_id):
    return next(v for v in report.cases if v.flow_id == flow_id)


def _broken_step(flow):
    """끊긴 스텝. 없으면 None — 실패가 스텝이 아니라 기대에서 났다는 뜻이다."""
    return next((r for r in flow.step_results if r.status != "ok"), None)


class TestDocument:
    def test_세_화면이_추출된다(self, good_run):
        report, _ = good_run
        assert set(report.summary["by_screen"]) == {"signup", "login", "product"}

    def test_흐름_케이스가_둘_생긴다(self, good_run):
        report, _ = good_run
        assert sorted(v.flow_id for v in report.cases if v.flow_id) == sorted(
            [LINK_FLOW, STATE_FLOW])

    def test_화면별_결과가_단일_문서와_같다(self, good_run):
        """흐름을 얹은 것이 화면별 판정을 건드리지 않아야 한다."""
        report, _ = good_run
        got = {k: (n["pass"], n["fail"]) for k, n in report.summary["by_screen"].items()}
        assert got == EXPECTED_BY_SCREEN["good"]

    def test_두_흐름의_제목이_다르다(self, good_run):
        """같은 화면 셋을 밟는 두 흐름의 제목이 같으면 리포트에서 어느 쪽이
        실패했는지 구분할 수 없다."""
        report, _ = good_run
        titles = {v.title for v in report.cases if v.flow_id}
        assert len(titles) == 2, titles


class TestGoodVariant:
    def test_두_흐름_모두_통과한다(self, good_run):
        """세 화면이 실제로 이어지면 로그인 가드로 막힌 화면까지 닿는다."""
        report, _ = good_run
        for flow_id in (LINK_FLOW, STATE_FLOW):
            flow = _flow(report, flow_id)
            assert flow.verdict == "PASS", f"{flow_id}: {flow.failure_detail}"

    def test_전이마다_이동_방법이_다르다(self, good_run):
        """첫 전이는 완료 화면의 링크를 눌러서, 둘째 전이는 주소로. 링크를 누르는
        전이가 없으면 화면을 잇는 요소가 아예 검증되지 않는다."""
        report, _ = good_run
        flow = _flow(report, LINK_FLOW)
        paths = [r.target for r in flow.step_results if r.action == "navigate"]
        clicks = [r.target for r in flow.step_results if r.action == "click"]
        assert paths == ["/signup", "/product"]
        assert "로그인하러 가기" in clicks

    def test_주소로만_옮기는_흐름은_세_번_navigate한다(self, good_run):
        report, _ = good_run
        flow = _flow(report, STATE_FLOW)
        paths = [r.target for r in flow.step_results if r.action == "navigate"]
        assert paths == ["/signup", "/login", "/product"]

    def test_중간_화면_둘_다_도착을_확인한다(self, good_run):
        """화면이 셋이면 앞에서 끊길 위험도 둘이다."""
        report, _ = good_run
        flow = _flow(report, STATE_FLOW)
        targets = [r.target for r in flow.step_results
                   if r.action == "assert" and r.target.endswith("성공")]
        assert targets == ["signup 성공", "login 성공"]

    def test_오탐이_없다(self, good_run):
        report, _ = good_run
        failures = [v for v in report.cases if v.verdict == "FAIL"]
        assert not failures, (
            "기획서 준수 구현에서 실패가 났다 — 오탐이다:\n"
            + "\n".join(f"  {v.title}: {v.failure_detail}" for v in failures)
        )


class TestBadVariant:
    def test_두_흐름_모두_실패한다(self, bad_run):
        report, _ = bad_run
        for flow_id in (LINK_FLOW, STATE_FLOW):
            assert _flow(report, flow_id).verdict == "FAIL", flow_id

    def test_잘못된_링크는_로그인_도착에서_끊긴다(self, bad_run):
        """E2 — 완료 화면의 링크가 /search 를 가리킨다. 끊긴 자리가 첫 전이여야
        하고, 실제로 간 곳이 근거에 남아야 고칠 곳을 안다."""
        report, _ = bad_run
        step = _broken_step(_flow(report, LINK_FLOW))
        assert step is not None and step.target == "login 도착", step
        assert "/bad/search" in (step.error_detail or ""), step.error_detail

    def test_이어지지_않은_상태는_로그인_단계에서_끊긴다(self, bad_run):
        """E1 — 가입이 계정을 등록하지 않았다. 잘못은 가입 화면에 있지만 드러나는
        자리는 로그인이고, **마지막 화면인 상품 등록이 아니다.** 마지막이 지목되면
        개발자가 상품 등록 코드를 뒤진다."""
        report, _ = bad_run
        step = _broken_step(_flow(report, STATE_FLOW))
        assert step is not None and step.target == "login 성공", step

    def test_상품_등록_화면까지_가지_않는다(self, bad_run):
        """앞에서 끊겼으면 뒤 화면은 밟지 않는다. 밟은 척하면 '상품 등록은
        확인했다' 는 거짓 초록불이 리포트에 남는다."""
        report, _ = bad_run
        for flow_id in (LINK_FLOW, STATE_FLOW):
            flow = _flow(report, flow_id)
            filled = [r.target for r in flow.step_results
                      if r.action == "fill" and r.status == "ok"]
            assert "상품명" not in filled, flow_id

    def test_화면별_결과가_단일_문서와_같다(self, bad_run):
        report, _ = bad_run
        got = {k: (n["pass"], n["fail"]) for k, n in report.summary["by_screen"].items()}
        assert got == EXPECTED_BY_SCREEN["bad"]

    def test_흐름_실패를_화면_실패와_섞지_않는다(self, bad_run):
        """흐름 실패를 마지막 화면 칸에 합치면 그 화면에 결함이 하나 더 있는
        것처럼 읽힌다. 실제로는 고칠 곳이 다르다."""
        report, _ = bad_run
        assert report.summary["by_flow"][LINK_FLOW]["fail"] == 1
        assert report.summary["by_flow"][STATE_FLOW]["fail"] == 1
