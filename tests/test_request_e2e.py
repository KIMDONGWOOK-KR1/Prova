"""자연어 요청 경로 관통 테스트 — 요청이 판정을 오염시키지 않는지 고정한다.

## 이 테스트가 지키는 것

자연어 층은 파이프라인에서 **미탐을 만들 수 있는 유일한 자리**다. 그래서 확인할
것은 "요청이 잘 먹히는가" 가 아니라 다음 세 가지다.

    1. 고른 케이스는 전체의 부분집합이다 — 없던 케이스가 생기지 않는다
    2. 고른 케이스의 판정은 전체 실행일 때와 같다 — 요청이 판정을 바꾸지 않는다
    3. 제외한 것이 리포트에 남는다 — '통과' 와 '안 봤다' 가 구분된다

2번이 핵심이다. 요청 해석이 케이스 선택을 넘어 판정에까지 영향을 주면, 리포트의
PASS 가 무엇을 뜻하는지 알 수 없게 된다.
"""

from __future__ import annotations

import json

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline

SPEC_PDF = "fixtures/specs/login_spec.pdf"

# 요청이 고를 케이스. 비밀번호 규칙 세 건만 고른 상황을 흉내낸다.
PICKED = [
    "login-password-min_length-005",
    "login-password-require_uppercase-006",
    "login-password-require_special-007",
]


def _llm(case_ids=None) -> MockLLM:
    llm = MockLLM.with_login_fixtures()
    if case_ids is not None:
        llm.register(
            "CaseSelection",
            {"case_ids": list(case_ids), "reason": "비밀번호 규칙 케이스만 골랐습니다"},
        )
    return llm


@pytest.fixture(scope="module")
def full_run(sut_base, tmp_path_factory):
    """요청 없이 전체를 실행한 기준선."""
    return run_pipeline(
        pdf_path=SPEC_PDF,
        base_url=f"{sut_base}/bad",
        llm=_llm(),
        run_id="req-full",
        runs_root=tmp_path_factory.mktemp("full"),
    )


@pytest.fixture(scope="module")
def request_run(sut_base, tmp_path_factory):
    """같은 대상을 자연어 요청으로 좁혀 실행."""
    return run_pipeline(
        pdf_path=SPEC_PDF,
        base_url=f"{sut_base}/bad",
        llm=_llm(PICKED),
        run_id="req-picked",
        runs_root=tmp_path_factory.mktemp("picked"),
        request="비밀번호 규칙이 제대로 걸리는지 확인해줘",
    )


class TestSubset:
    def test_고른_케이스는_전체의_부분집합이다(self, full_run, request_run):
        """자연어 층이 없던 케이스를 만들어내면 판정 전체가 거짓이 된다."""
        all_ids = {v.case_id for v in full_run[0].cases}
        picked_ids = {v.case_id for v in request_run[0].cases}
        assert picked_ids <= all_ids
        assert picked_ids == set(PICKED)

    def test_요청한_수만큼만_실행한다(self, request_run):
        report, _ = request_run
        assert report.summary["total"] == len(PICKED)


class TestVerdictUnchanged:
    def test_판정이_전체_실행과_같다(self, full_run, request_run):
        """요청은 무엇을 볼지만 정한다. 어떻게 판정할지는 건드리지 못한다."""
        full = {v.case_id: v.verdict for v in full_run[0].cases}
        picked = {v.case_id: v.verdict for v in request_run[0].cases}
        assert picked == {cid: full[cid] for cid in PICKED}

    def test_bad_변형에서_비밀번호_결함_세_건을_그대로_지목한다(self, request_run):
        report, _ = request_run
        assert report.summary["fail"] == 3


class TestSelectionRecorded:
    def test_리포트에_요청_원문과_근거가_남는다(self, request_run):
        sel = request_run[0].selection
        assert sel is not None
        assert sel.request == "비밀번호 규칙이 제대로 걸리는지 확인해줘"
        assert sel.reason
        assert sel.fallback is False

    def test_제외한_케이스가_리포트에_남는다(self, request_run):
        """'통과' 와 '아예 안 봤다' 를 구분할 수 있어야 한다."""
        sel = request_run[0].selection
        assert "login-email-format-003" in sel.excluded
        assert set(sel.selected) & set(sel.excluded) == set()

    def test_HTML_에_제외_목록이_보인다(self, request_run):
        html = (request_run[1] / "report.html").read_text(encoding="utf-8")
        assert "제외한 케이스" in html
        assert "login-email-format-003" in html

    def test_JSON_에도_선택_내역이_담긴다(self, request_run):
        data = json.loads((request_run[1] / "report.json").read_text(encoding="utf-8"))
        assert data["selection"]["request"]
        assert data["selection"]["excluded"]


class TestNoRequestUnchanged:
    def test_요청이_없으면_selection_이_없다(self, full_run):
        """기존 CLI 경로는 그대로여야 한다 — 리포트에 없던 절이 생기지 않는다."""
        sel = full_run[0].selection
        assert sel is None or not sel.request

    def test_요청이_없으면_HTML_에_요청_절이_없다(self, full_run):
        html = (full_run[1] / "report.html").read_text(encoding="utf-8")
        assert "자연어 요청으로 고른 실행" not in html


class TestNamedPartialWarning:
    """요청이 화면을 지목했는데 일부만 실행된 경우, 리포트가 그 사실을 짚는다.

    실측에서 "회원가입이 잘 되는지" 에 7B 가 17건 중 6건만 골랐고 프롬프트로는 안
    고쳐졌다. '11건 제외' 만 남으면 그 화면을 확인했다고 읽힌다 — 이 표시가 그 남은
    구멍의 방어선이다.
    """

    @pytest.fixture(scope="class")
    @staticmethod
    def named_partial_run(sut_base, tmp_path_factory):
        """'로그인' 을 이름으로 지목한 요청 + 사람이 3건만 승인한 실행."""
        return run_pipeline(
            pdf_path=SPEC_PDF,
            base_url=f"{sut_base}/bad",
            llm=_llm(),
            run_id="req-named-partial",
            runs_root=tmp_path_factory.mktemp("named"),
            request="로그인이 잘 되는지 확인해줘",
            case_ids=PICKED,
        )

    def test_selection_에_화면별_범위가_남는다(self, named_partial_run):
        sel = named_partial_run[0].selection
        login = next(c for c in sel.coverage if c.key == "login")
        assert login.named is True
        assert (login.selected, login.total) == (3, 10)

    def test_HTML_이_일부만_실행됨을_짚는다(self, named_partial_run):
        html = (named_partial_run[1] / "report.html").read_text(encoding="utf-8")
        assert "10건 중 3건만 실행됩니다" in html
        assert "화면 전체의 상태를 뜻하지 않습니다" in html

    def test_규칙_지목_요청에는_화면_경고가_없다(self, request_run):
        """'비밀번호 규칙' 처럼 규칙을 지목한 요청은 일부 실행이 의도다.
        그때도 경고하면 늑대 소리가 되어 진짜 경고가 묻힌다."""
        html = (request_run[1] / "report.html").read_text(encoding="utf-8")
        assert "건만 실행됩니다" not in html
