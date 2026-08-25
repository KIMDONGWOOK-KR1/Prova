"""병합 모드 관통 — multi 기획서 + 실물 Figma 응답 (specs/2026-08-25 2단계).

일치 시나리오(실물 응답)에서 good 은 전부 PASS 여야 하고, 발견 목록에는
'구현 결함' 이 아니라 '입력 사이의 사실' 만 실린다: 검색 화면이 디자인에
없다는 것, 디자인의 가입하기→로그인 흐름이 기획서 성공 조건(/welcome)과
모순이라는 것. 불일치 시나리오(손제작 응답)는 발견이 리포트에 실리고 어긋난
placeholder 가 판정에서 빠지는 것을 본다.
"""

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline

MULTI_PDF = "fixtures/specs/multi_spec.pdf"
REAL_FIGMA = "fixtures/figma/login_signup.json"
MISMATCH_FIGMA = "fixtures/figma/synthetic_mismatch.json"


def _run(variant, figma, sut_base, tmp_path):
    report, run_dir = run_pipeline(
        pdf_path=MULTI_PDF, base_url=f"{sut_base}/{variant}",
        llm=MockLLM.for_document(
            "fixtures/specs/login_spec.pdf",
            "fixtures/specs/signup_spec.pdf",
            "fixtures/specs/search_spec.pdf",
        ),
        run_id=f"test-merge-{variant}", runs_root=tmp_path,
        figma_json=figma,
    )
    return report, run_dir


@pytest.fixture(scope="module")
def good_run(sut_base, tmp_path_factory):
    return _run("good", REAL_FIGMA, sut_base, tmp_path_factory.mktemp("merge-good"))


class TestMergedGood:
    def test_전부_통과한다(self, good_run):
        report, _ = good_run
        fails = [v for v in report.cases if v.verdict == "FAIL"]
        assert not fails, "\n".join(f"{v.case_id}: {v.failure_detail}" for v in fails)

    def test_발견_목록이_입력_사이의_사실만_말한다(self, good_run):
        report, _ = good_run
        found = report.summary.get("design_mismatches") or []
        assert any("검색" in f for f in found)            # 기획서 단독 화면
        assert any("가입하기" in f for f in found)         # 흐름 모순 (/welcome)
        assert not any("가짜 입력란" in f for f in found)   # 1단계 경고는 경고대로

    def test_리포트에_불일치_상자가_실린다(self, good_run):
        _, run_dir = good_run
        html = (run_dir / "report.html").read_text(encoding="utf-8")
        assert "기획↔디자인 불일치" in html

    def test_규칙_케이스가_병합에서도_만들어졌다(self, good_run):
        report, _ = good_run
        assert any(v.type == "negative" for v in report.cases)

    def test_PDF_흐름은_병합에서도_돈다(self, good_run):
        report, _ = good_run
        flow_ids = {v.flow_id for v in report.cases if v.flow_id}
        assert "signup_then_login" in flow_ids


class TestMismatch:
    def test_어긋난_placeholder_는_판정에서_빠지고_발견으로_남는다(
            self, sut_base, tmp_path_factory):
        report, _ = _run("good", MISMATCH_FIGMA, sut_base,
                         tmp_path_factory.mktemp("merge-mm"))
        found = report.summary.get("design_mismatches") or []
        assert any("안내 문구" in f and "아이디를 입력하세요" in f for f in found)
        assert any("OTP" in f for f in found)
        assert any("비밀번호" in f and "디자인에 없" in f for f in found)
        # 어긋난 placeholder 로 FAIL 이 나면 안 된다 — 판정에서 뺐으니까
        ph = [v for v in report.cases
              if v.screen_id == "login" and "placeholders" in v.case_id]
        assert all(v.verdict == "PASS" for v in ph), \
            [(v.case_id, v.failure_detail) for v in ph]
