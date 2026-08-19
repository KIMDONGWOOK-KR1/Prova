"""리포트가 준비(setup)와 실행(test) 스텝을 구분해 보여주는가 (I4).

## 왜 필요했는가

models.py 의 StepResult.phase 는 "리포트가 구분해 보여준다" 고 약속했는데,
_steps_html·_shots_html 은 실제로는 phase 를 읽지 않고 seq 만 찍었다. 준비
스텝과 본 스텝은 둘 다 seq 가 1부터 다시 매겨지므로(nodes._run_case_steps
참고), 표만 보면 "스텝 3" 이 로그인 절차의 3번인지 상품 등록의 3번인지 알
수 없었다. 그 약속을 실제로 지키게 한다.
"""

from __future__ import annotations

from prova.models import StepResult, Verdict
from prova.s6_report.report_builder import _shots_html, _steps_html


def _verdict(step_results: list[StepResult]) -> Verdict:
    return Verdict(
        case_id="product-valid-001", title="정상 상품 등록", type="positive",
        screen_id="product", verdict="PASS", step_results=step_results,
    )


class TestStepsHtmlPhase:
    def test_준비_스텝은_준비로_표시된다(self):
        v = _verdict([
            StepResult(seq=1, action="navigate", target="/login", phase="setup"),
            StepResult(seq=4, action="click", target="로그인", phase="setup"),
        ])
        html = _steps_html(v)
        assert html.count("<td>준비</td>") == 2
        assert "실행" not in html or html.count("<td>실행</td>") == 0

    def test_실행_스텝은_실행으로_표시된다(self):
        v = _verdict([
            StepResult(seq=1, action="navigate", target="/product", phase="test"),
        ])
        html = _steps_html(v)
        assert "<td>실행</td>" in html

    def test_준비와_실행이_섞이면_단계별로_구분된다(self):
        """seq 가 1부터 겹쳐도(준비 1, 실행 1) 단계 열이 있어 헷갈리지 않는다."""
        v = _verdict([
            StepResult(seq=1, action="navigate", target="/login", phase="setup"),
            StepResult(seq=1, action="navigate", target="/product", phase="test"),
        ])
        html = _steps_html(v)
        assert html.count("<td>준비</td>") == 1
        assert html.count("<td>실행</td>") == 1

    def test_단계_열_헤더가_있다(self):
        v = _verdict([StepResult(seq=1, action="navigate", target="/x")])
        assert "<th>단계</th>" in _steps_html(v)


class TestShotsHtmlPhase:
    def test_준비_스텝_스크린샷은_준비_접두어가_붙는다(self):
        v = _verdict([
            StepResult(seq=1, action="navigate", target="/login", phase="setup",
                      screenshot="case/setup/step1.png"),
        ])
        html = _shots_html(v)
        assert "준비 step 1" in html

    def test_실행_스텝_스크린샷은_접두어가_없다(self):
        v = _verdict([
            StepResult(seq=1, action="navigate", target="/product", phase="test",
                      screenshot="case/step1.png"),
        ])
        html = _shots_html(v)
        assert ">step 1<" in html
        assert "준비 step 1" not in html
