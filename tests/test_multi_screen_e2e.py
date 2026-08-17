"""한 문서에 여러 화면 + 화면 사이 흐름 — 관통 테스트.

## 이 테스트가 지키는 것

두 가지다. 하나는 새 기능(다중 화면·흐름)이 동작하는지, **다른 하나는 화면당 PDF
하나였을 때의 판정이 그대로 유지되는지**다. 뒤쪽이 더 중요하다 — 문서를 합친 것만으로
화면별 결과가 달라지면 그건 확장이 아니라 후퇴다.

그래서 화면별 내역을 단일 문서 실행의 기대값과 대조한다.

    login   good 10/10  bad 4 PASS / 6 FAIL
    signup  good 17/17  bad 13 PASS / 4 FAIL
    search  good 10/10  bad 6 PASS / 4 FAIL

## 심어 둔 '화면 사이' 결함 2종

    E1  회원가입이 계정을 실제로 등록하지 않는다        -> 이어진 상태가 깨졌다
    E2  완료 화면의 '로그인하러 가기' 가 /search 를 가리킨다 -> 화면을 잇는 요소가 깨졌다

둘 다 **화면 하나만 보면 결함이 아니다.** 회원가입 화면의 케이스 17건은 입력 검증만
보므로 E1 과 무관하게 통과하고, E2 의 링크는 /signup 이 아니라 완료 화면에 있어서
화면 단위 케이스가 아예 닿지 않는다.

## 흐름이 둘인 이유

두 흐름이 같은 화면 쌍을 밟는데 확인하는 것이 다르다.

    signup_link_to_login  링크를 눌러 로그인 화면에 닿는가   -> E2 를 잡는다
    signup_then_login     주소로 가서 그 계정으로 되는가     -> E1 을 잡는다

하나로 합치면 앞의 결함(E2)이 먼저 스텝을 끊어 **뒤의 결함(E1)이 가려진다.** 스텝이
끊기면 이후 판정이 무의미하다는 규칙 때문이고, 그 규칙 자체는 옳다 — 대신 확인하려는
질문이 둘이면 케이스도 둘이어야 한다.

## 실행 순서에 대한 주의

SUT 의 계정 등록은 프로세스 상태다. good 을 한 번 돌리면 그 계정이 남으므로, 같은
SUT 에서 good 을 두 번째로 돌릴 때는 흐름이 '앞선 실행이 등록해 둔 계정' 으로 통과할
수 있다. 결함 탐지 방향(bad 가 실패하는가)은 이 영향을 받지 않는다 — bad 는 어떤
순서로 돌려도 등록하지 않는다. 그래서 수용 기준의 무게를 bad 쪽에 둔다.
"""

from __future__ import annotations

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline

# mock 은 화면 ID 로 응답을 고른다 — 순서대로 돌려주면 화면 분리가 뒤바뀌어도
# 테스트가 통과한다 (MockLLM.for_document 설명 참고).

SPEC_PDF = "fixtures/specs/multi_spec.pdf"

# 단일 문서로 돌렸을 때의 화면별 결과. 이 값이 유지돼야 확장이다.
EXPECTED_BY_SCREEN = {
    "good": {"login": (10, 0), "signup": (17, 0), "search": (10, 0)},
    "bad": {"login": (4, 6), "signup": (13, 4), "search": (6, 4)},
}

LINK_FLOW = "signup_link_to_login"   # 화면을 잇는 요소를 확인한다 (E2)
STATE_FLOW = "signup_then_login"     # 이어진 상태를 확인한다 (E1)


def _run(variant: str, sut_base: str, tmp_path):
    report, run_dir = run_pipeline(
        pdf_path=SPEC_PDF,
        base_url=f"{sut_base}/{variant}",
        llm=MockLLM.for_document(
            "fixtures/specs/login_spec.pdf",
            "fixtures/specs/signup_spec.pdf",
            "fixtures/specs/search_spec.pdf",
        ),
        run_id=f"test-multi-{variant}",
        runs_root=tmp_path,
    )
    return report, run_dir


@pytest.fixture(scope="module")
def good_run(sut_base, tmp_path_factory):
    return _run("good", sut_base, tmp_path_factory.mktemp("multi-good"))


@pytest.fixture(scope="module")
def bad_run(sut_base, tmp_path_factory):
    return _run("bad", sut_base, tmp_path_factory.mktemp("multi-bad"))


class TestScreenSplit:
    def test_세_화면의_케이스가_모두_생긴다(self, good_run):
        """화면 하나를 놓치면 그 화면은 검증되지 않은 채 리포트가 초록불이 된다."""
        report, _ = good_run
        assert set(report.summary["by_screen"]) == {"login", "signup", "search"}

    def test_케이스_총계(self, good_run):
        """login 10 + signup 17 + search 10 + 흐름 2 = 39."""
        report, _ = good_run
        assert report.summary["total"] == 39

    def test_화면별_결과가_단일_문서와_같다(self, good_run):
        report, _ = good_run
        got = {k: (n["pass"], n["fail"]) for k, n in report.summary["by_screen"].items()}
        assert got == EXPECTED_BY_SCREEN["good"]

    def test_스크린샷_경로가_화면별로_갈린다(self, good_run):
        """case_id 가 화면 ID 로 시작하므로 경로가 겹치지 않는다. 겹치면 증거가
        서로를 덮어쓰는데 리포트는 정상으로 보인다."""
        report, run_dir = good_run
        shots = [v.evidence.get("screenshot") for v in report.cases]
        assert len(set(s for s in shots if s)) == len([s for s in shots if s])


class TestGoodVariant:
    def test_전_케이스_통과(self, good_run):
        report, _ = good_run
        failures = [v for v in report.cases if v.verdict == "FAIL"]
        assert not failures, (
            "기획서 준수 구현에서 실패가 났다 — 오탐이다:\n"
            + "\n".join(f"  {v.title}: {v.failure_detail}" for v in failures)
        )

    def test_두_흐름_모두_통과한다(self, good_run):
        report, _ = good_run
        for flow_id in (LINK_FLOW, STATE_FLOW):
            flow = next(v for v in report.cases if v.flow_id == flow_id)
            assert flow.verdict == "PASS", f"{flow_id}: {flow.failure_detail}"

    def test_흐름_제목이_서로_다르다(self, good_run):
        """같은 화면 쌍을 밟는 두 흐름의 제목이 같으면 리포트에서 어느 쪽이
        실패했는지 구분할 수 없다."""
        report, _ = good_run
        titles = {v.title for v in report.cases if v.flow_id}
        assert len(titles) == 2, titles


class TestBadVariant:
    def test_화면별_결과가_단일_문서와_같다(self, bad_run):
        """흐름을 추가한 것이 화면별 판정을 건드리지 않아야 한다."""
        report, _ = bad_run
        got = {k: (n["pass"], n["fail"]) for k, n in report.summary["by_screen"].items()}
        assert got == EXPECTED_BY_SCREEN["bad"]

    def test_잘못된_링크를_잡는다(self, bad_run):
        """E2 — 화면을 잇는 요소. 주소로 이동하면 도구가 스스로 주소를 치므로
        이 결함에 도달할 경로가 아예 없다."""
        report, _ = bad_run
        flow = next(v for v in report.cases if v.flow_id == LINK_FLOW)
        assert flow.verdict == "FAIL"
        assert "login 도착" in flow.failure_detail, flow.failure_detail
        assert "/bad/search" in flow.failure_detail, "실제로 간 곳을 남겨야 한다"

    def test_이어지지_않은_상태를_잡는다(self, bad_run):
        """E1 — 화면별 케이스로는 도달할 경로가 없는 결함."""
        report, _ = bad_run
        flow = next(v for v in report.cases if v.flow_id == STATE_FLOW)
        assert flow.verdict == "FAIL"

    def test_흐름_실패를_화면_실패와_섞지_않는다(self, bad_run):
        """흐름 실패를 마지막 화면 칸에 합치면 그 화면에 결함이 하나 더 있는
        것처럼 읽힌다. 실제로는 고칠 곳이 다르다."""
        report, _ = bad_run
        assert report.summary["by_screen"]["login"]["fail"] == 6
        assert report.summary["by_flow"][LINK_FLOW]["fail"] == 1
        assert report.summary["by_flow"][STATE_FLOW]["fail"] == 1

    def test_실패_설명이_화면_사이를_가리킨다(self, bad_run):
        """마지막 화면 이름만 나오면 개발자가 로그인 코드를 뒤진다. 앞 화면이 남긴
        상태가 이어지지 않았을 가능성을 먼저 짚어야 한다."""
        report, _ = bad_run
        flow = next(v for v in report.cases if v.flow_id == STATE_FLOW)
        assert "화면 사이" in flow.failure_detail

    def test_오탐이_없다(self, bad_run):
        """심은 결함: 로그인 4종(6건) + 회원가입 4종 + 검색 3종(4건)
        + E1(계정 미등록) + E2(잘못된 링크) = 16건."""
        report, _ = bad_run
        assert report.summary["fail"] == 16, "\n".join(
            f"  {v.verdict} {v.title}" for v in report.cases
        )


class TestFlowSteps:
    """흐름 케이스의 스텝 구성 — 여기가 흐름 검증의 신뢰 근거다."""

    def test_주소로_이동하는_흐름은_두_번_navigate한다(self, good_run):
        report, _ = good_run
        flow = next(v for v in report.cases if v.flow_id == STATE_FLOW)
        paths = [r.target for r in flow.step_results if r.action == "navigate"]
        assert paths == ["/signup", "/login"]

    def test_링크로_이동하는_흐름은_한_번만_navigate한다(self, good_run):
        """두 번째 화면에 주소로 들어가면 링크가 검증되지 않는다."""
        report, _ = good_run
        flow = next(v for v in report.cases if v.flow_id == LINK_FLOW)
        paths = [r.target for r in flow.step_results if r.action == "navigate"]
        assert paths == ["/signup"]
        clicks = [r.target for r in flow.step_results if r.action == "click"]
        assert "로그인하러 가기" in clicks

    def test_중간_도착을_확인하는_스텝이_있다(self, good_run):
        """이 스텝이 없으면 앞 화면에서 끊겨도 마지막 화면이 지목된다."""
        report, _ = good_run
        flow = next(v for v in report.cases if v.flow_id == STATE_FLOW)
        asserts = [r for r in flow.step_results if r.action == "assert"]
        assert len(asserts) == 1
        assert "signup" in asserts[0].target

    def test_링크_흐름은_도착_확인이_둘이다(self, good_run):
        """앞 화면의 성공 확인 + 링크를 눌러 다음 화면에 닿았는지 확인."""
        report, _ = good_run
        flow = next(v for v in report.cases if v.flow_id == LINK_FLOW)
        targets = [r.target for r in flow.step_results if r.action == "assert"]
        assert targets == ["signup 성공", "login 도착"]

    def test_가입에_쓴_값으로_로그인한다(self, good_run):
        """라벨이 같으면 같은 값을 쓴다. 이어지지 않으면 흐름이 확인하는 것이
        '가입한 계정으로 로그인되는가' 가 아니게 된다."""
        report, _ = good_run
        flow = next(v for v in report.cases if v.flow_id == STATE_FLOW)
        emails = [r.target for r in flow.step_results
                  if r.action == "fill" and r.target == "이메일"]
        assert len(emails) == 2, "두 화면 모두 이메일을 채워야 한다"
