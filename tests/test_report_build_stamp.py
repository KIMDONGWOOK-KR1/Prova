"""리포트가 '무엇을 상대로 쟀는지' 를 말한다 — 대상 빌드 확인 결과.

며칠 뒤에 리포트만 남았을 때, 거기 적힌 FAIL 이 구현의 결함인지 **낡은 대상을
잰 것**인지 물을 수 있어야 한다. 어긋남은 실행을 막으므로 리포트에 남는 값은
'일치' 아니면 '확인 불가' 둘뿐인데, 그 둘의 구별이 바로 그 질문의 답이다 —
확인 불가는 '낡았을 가능성을 배제하지 못했다' 는 뜻이다.

경고 상자로 만들지 않는다. 실물 대상에는 도장이 없는 것이 정상이라 매번 뜨는
상자가 되고, 매번 뜨는 경고는 읽히지 않는다. 머리말 한 줄이면 충분하다.
"""

from __future__ import annotations

import pytest

from prova.models import TestReport, Verdict
from prova.s6_report.report_builder import build_report, render_html


def _verdicts() -> list[Verdict]:
    return [Verdict(case_id="c1", title="t", screen_id="login", verdict="PASS")]


def _report(sut_build: str | None) -> TestReport:
    kwargs = {"sut_build": sut_build} if sut_build is not None else {}
    return build_report(run_id="r", target_url="http://x/good",
                        verdicts=_verdicts(), backend="mock", **kwargs)


class TestSummary:
    def test_확인_결과가_요약에_남는다(self):
        assert _report("match").summary["sut_build"] == "match"

    def test_도장이_없었다는_것도_사실이라_남는다(self):
        assert _report("absent").summary["sut_build"] == "absent"

    def test_확인하지_않았으면_칸을_만들지_않는다(self):
        """확인을 건너뛴 실행(서버 경로 등)까지 칸을 달면, 기존에 요약을
        dict 로 비교하던 소비자가 깨진다. 'absent' 와도 다른 사실이다."""
        assert "sut_build" not in _report(None).summary


class TestHtml:
    def test_일치는_머리말에_한_줄로_나온다(self):
        html = render_html(_report("match"))
        assert "대상 빌드" in html and "일치" in html

    def test_도장이_없으면_확인_불가라고_적는다(self):
        html = render_html(_report("absent"))
        assert "확인 불가" in html

    def test_닿지_않았어도_확인_불가다(self):
        assert "확인 불가" in render_html(_report("unreachable"))

    def test_확인하지_않았으면_줄이_없다(self):
        assert "대상 빌드" not in render_html(_report(None))
