"""성공 조건을 못 읽었을 때 — 본문에서 다시 읽고, 그래도 없으면 '약한 확인' 으로 보인다.

## 왜 (2026-09-23 외부 사이트 실측)

saucedemo 기획서 본문에는 "`/inventory.html` 로 이동하고 "Products" 문구를 노출한다"
가 분명히 있었는데, 7B 가 success_condition 문장을 의역하면서 경로와 문구를 둘 다
빠뜨렸다. 그러면 정상 케이스의 기대가 비고, 판정은 '에러가 안 떴다' 만 보고 통과한다.
그날 로그인 버튼 대신 폼을 누르는 결함이 겹쳐 **로그인하지 않고 PASS** 했다.

1. 모델이 준 문장에서 경로·문구를 하나도 못 찾으면 기획서의 '성공 조건' 절 본문에서
   코드가 찾는다(표에 적힌 사실은 코드가 읽는다는 원칙의 연장). 채운 사실은 경고로.
2. 그래도 없으면 PASS 는 그대로 두되 '약한 확인' 으로 표시한다. 검색·주문조회처럼
   원래 목록을 보여 주는 화면은 건수·정렬 케이스가 실제 검증을 맡으므로, 판정을
   바꾸거나 매번 경고를 띄우는 것은 과하다.
"""

from __future__ import annotations

from prova.models import ScreenSpec, TestReport, Verdict
from prova.s1_spec_extractor.extractor import _apply_declared_success
from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage
from prova.s6_report.report_builder import render_html

LINES = [
    ("2. UI 요소 정의", 300.0),
    ("3. 성공 조건", 628.0),
    ("등록된 사용자 이름과 비밀번호를 입력하면 /inventory.html 로 이동하고", 653.0),
    ('"Products" 문구를 노출한다.', 674.0),
    ("4. 실패 조건", 701.0),
    ("비밀번호가 틀리면 /error 로 간다", 720.0),   # 다음 절 — 섞이면 안 된다
]


def _doc(lines=LINES):
    return ParsedDocument(source="x", pages=[ParsedPage(page_no=1, body_lines=list(lines))])


def _spec(success=""):
    return ScreenSpec(screen_id="sauce_login", screen_name="로그인", url_path="/",
                      success_condition=success)


class TestSectionText:
    def test_성공_조건_절만_읽는다(self):
        text = _doc().declared_success_text()
        assert "/inventory.html" in text and '"Products"' in text
        assert "/error" not in text

    def test_절이_없으면_None(self):
        assert _doc([("1. 화면 개요", 100.0)]).declared_success_text() is None


class TestBackfill:
    def test_모델_문장에_경로도_문구도_없으면_본문으로_채운다(self):
        spec = _spec("로그인에 성공하면 상품 목록 화면으로 이동한다")
        _apply_declared_success(spec, _doc())
        assert "/inventory.html" in spec.success_condition
        assert any("성공 조건을 기획서 본문에서 채웠습니다" in w for w in spec.warnings)

    def test_모델_문장이_쓸_만하면_건드리지_않는다(self):
        spec = _spec('/dashboard 로 이동하고 "환영합니다" 문구를 노출한다')
        _apply_declared_success(spec, _doc())
        assert spec.success_condition.startswith("/dashboard")
        assert spec.warnings == []

    def test_본문에도_없으면_그대로_둔다(self):
        spec = _spec("화면에 진입하면 주문 목록이 표시된다")
        _apply_declared_success(spec, _doc([("3. 성공 조건", 10.0),
                                            ("화면에 진입하면 주문 목록이 표시된다", 20.0)]))
        assert spec.success_condition == "화면에 진입하면 주문 목록이 표시된다"
        assert spec.warnings == []


class TestWeakPass:
    def _html(self):
        weak = Verdict(case_id="s-valid-001", title="정상 검색", type="positive",
                       screen_id="search", verdict="PASS",
                       evidence={"actual": "성공 조건이 명시되지 않아 '에러 없음' 으로 확인"})
        strong = Verdict(case_id="l-valid-001", title="정상 로그인", type="positive",
                         screen_id="login", verdict="PASS",
                         evidence={"actual": "경로 '/dashboard' 이동 확인"})
        report = TestReport(run_id="r", target_url="http://x", cases=[weak, strong],
                            summary={"total": 2, "pass": 2, "fail": 0, "pass_rate": 100.0})
        return render_html(report)

    def test_약한_확인_배지와_요약_한_줄(self):
        html = self._html()
        assert html.count("class='tag cat weak'>약한 확인<") == 1
        assert "'에러 없음'만 확인한 정상 케이스 1건" in html
