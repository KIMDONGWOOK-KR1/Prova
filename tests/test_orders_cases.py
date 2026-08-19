"""S2 — 주문 표에서 정렬·합계 케이스 생성 (스펙 §1-2·§3-4).

기획서가 '테스트 주문 데이터' 표를 제시해야만 정렬(sorted_desc)·합계
(sum_matches) 케이스를 만든다. 표가 없으면 만들지 않는 것이 원칙이고
(Scenario 때 세운 원칙의 연장), 데이터 없는 화면이 정상이므로 그때는 경고도
남기지 않는다. 반대로 표는 있는데 화면 요소가 뒷받침하지 못하면(날짜 열·
금액 열·합계 요소가 없다) 그건 기획서의 구멍이므로 경고를 남긴다.
"""

from prova.models import ScreenSpec, UIElement
from prova.s2_case_generator.generator import generate_cases

SEED_ROWS = [
    {"주문번호": "ORD-005", "주문일": "2026-08-15", "상품명": "노트북",
     "금액": "1,290,000", "상태": "배송중"},
    {"주문번호": "ORD-004", "주문일": "2026-08-12", "상품명": "마우스",
     "금액": "39,000", "상태": "배송완료"},
    {"주문번호": "ORD-003", "주문일": "2026-08-09", "상품명": "키보드",
     "금액": "89,000", "상태": "배송완료"},
    {"주문번호": "ORD-002", "주문일": "2026-08-03", "상품명": "모니터",
     "금액": "429,000", "상태": "취소"},
    {"주문번호": "ORD-001", "주문일": "2026-07-28", "상품명": "케이블",
     "금액": "12,000", "상태": "배송완료"},
]


def orders_elements() -> list[UIElement]:
    return [
        UIElement(element_id="order_list", type="list", label="주문 목록"),
        UIElement(element_id="order_date", type="text", label="주문일"),
        UIElement(element_id="order_amount", type="text", label="금액"),
        UIElement(element_id="order_total", type="text", label="합계"),
    ]


def orders_spec(seed_rows=None, elements=None) -> ScreenSpec:
    return ScreenSpec(
        screen_id="orders",
        screen_name="주문 조회",
        url_path="/orders",
        elements=elements if elements is not None else orders_elements(),
        success_condition="",
        seed_rows=seed_rows if seed_rows is not None else list(SEED_ROWS),
    )


class TestSeedRowCases:
    def test_정렬과_합계_케이스가_만들어진다(self):
        spec = orders_spec()
        cases = generate_cases(spec)

        sorted_cases = [c for c in cases if c.case_id.startswith("orders-sorted-")]
        sum_cases = [c for c in cases if c.case_id.startswith("orders-sum-")]
        assert len(sorted_cases) == 1
        assert len(sum_cases) == 1

        sorted_case = sorted_cases[0]
        assert sorted_case.expected.type == "sorted_desc"
        assert sorted_case.expected.order_target == "주문일"

        sum_case = sum_cases[0]
        assert sum_case.expected.type == "sum_matches"
        assert sum_case.expected.sum_row_target == "금액"
        assert sum_case.expected.sum_total_target == "합계"

    def test_날짜_열_자동판별은_주문번호가_아니라_주문일을_고른다(self):
        """ORD-005 는 날짜 정규식(YYYY-MM-DD)에 맞지 않는다 — 좋은 판별 근거다."""
        spec = orders_spec()
        cases = generate_cases(spec)
        sorted_case = next(c for c in cases if c.case_id.startswith("orders-sorted-"))
        assert sorted_case.expected.order_target != "주문번호"
        assert sorted_case.expected.order_target == "주문일"

    def test_seed_rows가_비면_케이스도_경고도_없다(self):
        """데이터 없는 화면이 정상이다 — 기획서가 데이터를 제시하지 않으면
        그 검증은 불가능하고, 그건 기획서의 한계이지 도구의 한계가 아니다."""
        spec = orders_spec(seed_rows=[])
        cases = generate_cases(spec)

        assert not any(c.case_id.startswith("orders-sorted-") for c in cases)
        assert not any(c.case_id.startswith("orders-sum-") for c in cases)
        assert spec.warnings == []

    def test_합계_요소가_없으면_합계_케이스만_빠지고_경고가_남는다(self):
        elements = [e for e in orders_elements() if e.label != "합계"]
        spec = orders_spec(elements=elements)
        cases = generate_cases(spec)

        assert any(c.case_id.startswith("orders-sorted-") for c in cases)
        assert not any(c.case_id.startswith("orders-sum-") for c in cases)
        assert any("합계" in w for w in spec.warnings)

    def test_날짜_열이_없으면_정렬_케이스만_빠지고_경고가_남는다(self):
        elements = [e for e in orders_elements() if e.label != "주문일"]
        spec = orders_spec(elements=elements)
        cases = generate_cases(spec)

        assert not any(c.case_id.startswith("orders-sorted-") for c in cases)
        assert any(c.case_id.startswith("orders-sum-") for c in cases)
        assert any("정렬" in w for w in spec.warnings)
