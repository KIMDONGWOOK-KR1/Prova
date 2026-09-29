"""리포트가 2차 경로(화면 이미지로 찾기)를 켰는지 말한다.

'탐지 실패 3건' 만으로는 이미지로 찾아보고도 못 찾은 것인지, 아예 시도하지 않은
것인지 알 수 없다. 둘은 다음에 할 일이 다르다 — 앞은 라벨 연결을 고칠 일이고,
뒤는 2차 경로를 켜고 다시 돌려 볼 수 있는 일이다.

머리말 한 줄로 둔다. 꺼진 것이 기본이라 상자로 만들면 매번 뜬다.
"""

from __future__ import annotations

from prova.models import TestReport, Verdict
from prova.s6_report.report_builder import build_report, render_html


def _report(**kw) -> TestReport:
    verdicts = [Verdict(case_id="c1", title="t", screen_id="login", verdict="PASS")]
    return build_report(run_id="r", target_url="http://x/good",
                        verdicts=verdicts, backend="mock", **kw)


def test_켠_모델이_요약에_남는다():
    assert _report(vlm="qwen3.5-4b-awq").summary["vlm"] == "qwen3.5-4b-awq"


def test_끈_것도_사실이라_남는다():
    assert _report(vlm="").summary["vlm"] == ""


def test_켜면_머리말에_모델이_나온다():
    html = render_html(_report(vlm="qwen3.5-4b-awq"))
    assert "2차 경로 <code>켬 · qwen3.5-4b-awq</code>" in html


def test_끄면_머리말에_꺼짐이_나온다():
    assert "2차 경로 <code>꺼짐</code>" in render_html(_report(vlm=""))


def test_기록이_없는_옛_리포트는_줄이_없다():
    """이 칸이 생기기 전의 리포트를 '꺼짐' 으로 읽으면 모르는 것을 안다고 말하는 것이다."""
    report = _report(vlm="")
    del report.summary["vlm"]
    assert "2차 경로" not in render_html(report)
