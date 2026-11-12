"""실패 카드의 구조 — 기획서와 실제 화면을 나란히, 재현 절차는 문장으로 (2026-11-12).

표의 '기대'·'실제' 두 줄은 위아래로 읽어 견줘야 했고, 재현 절차는 개발자 용어가 섞인
열 칸짜리 표뿐이었다. 기획자가 개발사에 그대로 넘길 수 있는 모양으로 바꾼다. 단계 표는
조사하는 사람의 자료라 접어서 남긴다.
"""

from __future__ import annotations

from prova.models import StepResult, Verdict
from prova.s6_report.report_builder import _case_html


def _fail(category="assertion_mismatch", **kw) -> Verdict:
    return Verdict(
        case_id="c1", title="비밀번호 확인 일치", screen_id="signup", verdict="FAIL",
        failure_category=category, failure_detail="에러가 없었다",
        evidence={"expected": "오류 문구가 나타난다", "actual": "에러가 전혀 노출되지 않음",
                  "url": "http://x/bad/welcome"},
        step_results=[
            StepResult(seq=1, action="navigate", target="/login", phase="setup"),
            StepResult(seq=1, action="fill", target="이메일", value="a@b.c"),
            StepResult(seq=2, action="click", target="가입하기", status="error"),
        ], **kw)


def test_기획서와_실제_화면이_나란히_놓인다():
    html = _case_html(_fail(), True)
    want, got = html.index("<h4>기획서</h4>"), html.index("<h4>실제 화면</h4>")
    assert want < got
    assert "오류 문구가 나타난다" in html[want:got]
    assert "에러가 전혀 노출되지 않음" in html[got:]
    assert "http://x/bad/welcome" in html[got:]


def test_재현_절차가_따라_할_수_있는_문장이다():
    html = _case_html(_fail(), True)
    assert "<h4>재현 절차</h4>" in html
    assert "&#x27;이메일&#x27; 칸에 &#x27;a@b.c&#x27; 입력" in html
    # 전제를 세우는 스텝과 멈춘 스텝은 표시가 붙는다.
    assert "<span class='pre'>준비</span>" in html
    assert "여기서 멈춤" in html


def test_단계_표는_접혀_있지만_남아_있다():
    html = _case_html(_fail(), True)
    raw = html.index("<details class='raw'>")
    assert "<table class='steps'>" in html[raw:]
    assert "<details class='raw' open" not in html


def test_도구_쪽_실패는_결함과_다른_색으로_칠한다():
    """전부 빨강이면 기획자가 개발사에 잘못 따진다."""
    defect = _case_html(_fail(), True)
    infra = _case_html(_fail("element_not_found"), True)
    assert "class='reason defect'" in defect and "class='cmp FAIL defect'" in defect
    assert "class='reason infra'" in infra and "class='cmp FAIL infra'" in infra


def test_스텝이_없으면_재현_절차도_없다():
    v = _fail()
    v.step_results = []
    assert "재현 절차" not in _case_html(v, True)


# ── 머리말: 실행 조건을 이름·값 격자로 (2026-11-12) ────────────────────────────
# 한 줄로 이어 쓰면 아홉 가지가 가운뎃점으로 붙어 읽히지 않았다.

def _report(**kw):
    from prova.s6_report.report_builder import build_report
    report = build_report(run_id="run-1", target_url="http://x/good",
                          verdicts=[_fail()], backend="mock", **kw)
    report.spec_source = r"C:\work\specs\signup_spec.pdf"
    report.created_at = "2026-11-12T17:30:57+09:00"
    return report


def test_실행_조건이_한_칸씩_나뉜다():
    from prova.s6_report.report_builder import render_html
    html = render_html(_report(vlm="qwen · 4b"))
    assert "<div class='mi'>대상 <code>http://x/good</code></div>" in html
    # 값 안의 가운뎃점에서 칸이 갈라지지 않는다.
    assert "<div class='mi'>2차 경로 <code>켬 · qwen · 4b</code></div>" in html


def test_기획서는_파일_이름만_보이고_경로는_남는다():
    from prova.s6_report.report_builder import render_html
    html = render_html(_report())
    assert ">signup_spec.pdf</code>" in html
    assert r"title='C:\work\specs\signup_spec.pdf'" in html
    assert ">2026-11-12 17:30</code>" in html
