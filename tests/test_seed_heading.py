"""데이터 표의 절 제목 — '테스트 주문 데이터' 만이 아니라 '테스트 ○○ 데이터'.

## 왜 (2026-09-27 스파이크 3, 표를 보여 주는 화면)

절 제목을 글자 그대로 '테스트 주문 데이터' 로만 찾았다. 사용자 표(the-internet)·직원 표
(demoqa)·상품 목록(saucedemo) 기획서가 '테스트 데이터'·'테스트 상품 데이터' 로 적자 표가
**조용히** 무시됐다 — 목록의 건수를 확인하지 않았고, 그 사실을 알리는 경고도 없었다.
"""

from __future__ import annotations

import pytest

from prova.models import ScreenSpec, UIElement
from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage, ParsedTable
from prova.s2_case_generator.generator import generate_cases

ROWS = [["Last Name", "Due"], ["Smith", "$50.00"], ["Bach", "$51.00"]]


def _doc(heading: str) -> ParsedDocument:
    return ParsedDocument(source="x", pages=[ParsedPage(
        page_no=1, body_lines=[(heading, 10.0)],
        tables=[ParsedTable(rows=ROWS, top=30.0)])])


@pytest.mark.parametrize("heading", [
    "5. 테스트 주문 데이터", "4. 테스트 데이터", "5. 테스트 상품 데이터", "테스트 사용자 데이터",
])
def test_테스트_무엇_데이터_절을_읽는다(heading):
    assert [r["Last Name"] for r in _doc(heading).declared_seed_rows()] == ["Smith", "Bach"]


@pytest.mark.parametrize("heading", [
    "5. 입력 예시 데이터",          # 예시값 표 — 시드 표가 아니다
    "6. 테스트 계정",
    "테스트 데이터를 아래와 같이 둔다",  # 문장 속 낱말은 절 제목이 아니다
])
def test_다른_절은_시드_표가_아니다(heading):
    assert _doc(heading).declared_seed_rows() == []


def test_건수_케이스_제목에_주문이_박혀_있지_않다():
    spec = ScreenSpec(
        screen_id="ti", screen_name="사용자 표", url_path="/tables",
        elements=[UIElement(element_id="user_list", type="list", label="사용자 목록")],
        seed_rows=[{"Last Name": "Smith"}, {"Last Name": "Bach"}],
    )
    count = next(c for c in generate_cases(spec) if c.expected.type == "result_count")
    assert "주문" not in count.title and "2건" in count.title
