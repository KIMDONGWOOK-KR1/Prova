"""입력-결과 예시 표를 고르는 기준 — 채울 수 있는 요소의 열이 있어야 한다.

## 왜 (2026-09-27 스파이크 3, 표를 보여 주는 화면)

열 제목이 요소 라벨이기만 하면 '입력 열' 로 봤다. 표시 전용 요소(텍스트)의 라벨이 걸린
데이터 표가 예시 표로 읽혔다 — the-internet 은 입력이 하나도 없는 '예시' 4건이 원래
화면에 있던 이름으로 통과했고(빈 통과), demoqa 는 나이 열(39·45)이 결과 건수가 되어
'직원 39명' 이 FAIL 했다(오탐). 뒤에 있던 진짜 예시 표(검색어 | 결과 건수)는 기대 문구
열이 없다는 이유로 조용히 버려졌다.
"""

from __future__ import annotations

from prova.models import Scenario, ScreenSpec, UIElement
from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage, ParsedTable
from prova.s2_case_generator.generator import generate_cases

ELEMENTS = [
    ["요소 ID", "유형", "라벨", "필수", "입력 검증 규칙", "안내 문구", "에러 메시지"],
    ["search", "입력", "검색어", "-", "-", "-", "-"],
    ["employee_list", "목록", "직원 목록", "-", "-", "-", "-"],
    ["first_name", "텍스트", "First Name", "-", "-", "-", "-"],
    ["salary", "텍스트", "Salary", "-", "-", "-", "-"],
]
DATA = [["First Name", "Last Name", "Age", "Salary"],
        ["Cierra", "Vega", "39", "10000"],
        ["Alden", "Cantrell", "45", "12000"]]
EXAMPLES = [["검색어", "결과 건수"], ["cierra", "1"], ["zzzz", "0"]]


def _doc(*tables):
    return ParsedDocument(source="x", pages=[ParsedPage(
        page_no=1, tables=[ParsedTable(rows=ELEMENTS), *(ParsedTable(rows=t) for t in tables)])])


class TestDeclaredScenarios:
    def test_표시_전용_라벨만_걸린_표는_예시_표가_아니다(self):
        assert _doc(DATA).declared_scenarios() == []

    def test_데이터_표_뒤의_진짜_예시_표를_읽는다(self):
        scenarios = _doc(DATA, EXAMPLES).declared_scenarios()
        assert [(s["given"], s["expect_count"]) for s in scenarios] == [
            ({"search": "cierra"}, 1), ({"search": "zzzz"}, 0)]

    def test_건수만_있어도_읽는다(self):
        scenarios = _doc(EXAMPLES).declared_scenarios()
        assert scenarios[0]["expect_text"] == ""
        assert scenarios[0]["expect_count"] == 1


def test_문구가_빈_시나리오는_건수_케이스만_만든다():
    spec = ScreenSpec(
        screen_id="dq", screen_name="직원 표", url_path="/webtables",
        elements=[UIElement(element_id="search", type="input", label="검색어"),
                  UIElement(element_id="employee_list", type="list", label="직원 목록"),
                  UIElement(element_id="btn", type="button", label="검색")],
        scenarios=[Scenario(given={"search": "cierra"}, expect_text="", expect_count=1)],
    )
    cases = [c for c in generate_cases(spec) if "cierra" in c.title]
    assert [c.expected.type for c in cases] == ["result_count"]
    assert "''" not in cases[0].title
