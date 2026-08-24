"""S2 — 주문 표에서 정렬·합계 케이스 생성 (스펙 §1-2·§3-4).

기획서가 '테스트 주문 데이터' 표를 제시해야만 정렬(sorted_desc)·합계
(sum_matches) 케이스를 만든다. 표가 없으면 만들지 않는 것이 원칙이고
(Scenario 때 세운 원칙의 연장), 데이터 없는 화면이 정상이므로 그때는 경고도
남기지 않는다. 반대로 표는 있는데 화면 요소가 뒷받침하지 못하면(날짜 열·
금액 열·합계 요소가 없다) 그건 기획서의 구멍이므로 경고를 남긴다.
"""

from prova.models import DateFilter, ScreenSpec, UIElement
from prova.s2_case_generator.generator import _filter_cases, generate_cases

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


class TestSeedColumnAmbiguity:
    """열 이름이 아니라 값의 모양으로 찾다 보니, 모양이 같은 열이 둘이면
    어느 것인지 코드가 정할 수 없다 (I1). 억측해 하나를 고르면 기획서가
    실제로 검증하려던 열이 아닌 다른 열을 검사하고도 통과라고 말할 수 있는
    조용한 오탐이 된다 — 그래서 아무것도 만들지 않고 둘 다 이름으로 알린다."""

    def test_날짜_모양_열이_두_개면_정렬_케이스를_만들지_않고_둘_다_알린다(self):
        seed_rows = [
            {**row, "배송일": row["주문일"]} for row in SEED_ROWS
        ]
        elements = orders_elements() + [
            UIElement(element_id="ship_date", type="text", label="배송일"),
        ]
        spec = orders_spec(seed_rows=seed_rows, elements=elements)
        cases = generate_cases(spec)

        assert not any(c.case_id.startswith("orders-sorted-") for c in cases)
        # 합계는 금액 열이 하나뿐이므로 영향받지 않는다 — 두 검증은 독립이다.
        assert any(c.case_id.startswith("orders-sum-") for c in cases)

        warning = next(w for w in spec.warnings if "정렬" in w or "sorted_desc" in w)
        assert "주문일" in warning and "배송일" in warning
        assert "여러 개" in warning

    def test_금액_모양_열이_두_개면_합계_케이스를_만들지_않고_둘_다_알린다(self):
        seed_rows = [
            {**row, "수량": "1"} for row in SEED_ROWS
        ]
        elements = orders_elements() + [
            UIElement(element_id="qty", type="text", label="수량"),
        ]
        spec = orders_spec(seed_rows=seed_rows, elements=elements)
        cases = generate_cases(spec)

        assert any(c.case_id.startswith("orders-sorted-") for c in cases)
        assert not any(c.case_id.startswith("orders-sum-") for c in cases)

        warning = next(w for w in spec.warnings if "합계" in w or "sum_matches" in w)
        assert "금액" in warning and "수량" in warning
        assert "여러 개" in warning


class TestSeedCountCase:
    """씨앗 행 수만큼 화면에 렌더됐는지 확인하는 케이스 (I5).

    정렬·합계는 화면이 스스로 모순인지만 보므로, 행이 통째로 하나 안
    렌더돼도(예: 마지막 행 누락) 둘 다 통과할 수 있다 — 건수를 직접 세는
    케이스가 있어야 그 누락이 걸린다."""

    def test_시드_건수_케이스가_만들어진다(self):
        spec = orders_spec()
        cases = generate_cases(spec)

        count_cases = [c for c in cases if c.case_id.startswith("orders-seedcount-")]
        assert len(count_cases) == 1
        case = count_cases[0]
        assert case.expected.type == "result_count"
        assert case.expected.count == len(SEED_ROWS)
        assert case.expected.count_target == "주문 목록"
        assert [s.action for s in case.steps] == ["navigate"]

    def test_목록_요소가_없으면_건수_케이스_대신_경고한다(self):
        elements = [e for e in orders_elements() if e.type != "list"]
        spec = orders_spec(elements=elements)
        cases = generate_cases(spec)

        assert not any(c.case_id.startswith("orders-seedcount-") for c in cases)
        assert any("목록" in w and "result_count" in w for w in spec.warnings)


def filter_spec(**overrides) -> ScreenSpec:
    """날짜 필터가 선언된 orders 스펙 (specs/2026-08-24)."""
    spec = orders_spec(**overrides)
    spec.elements += [
        UIElement(element_id="start_date", type="date", label="시작일"),
        UIElement(element_id="end_date", type="date", label="종료일"),
        UIElement(element_id="filter_btn", type="button", label="조회"),
    ]
    spec.date_filter = DateFilter(
        start_label="시작일", end_label="종료일", submit_label="조회",
        target_label="주문 목록", date_column="주문일",
        empty_message="기간 내 주문이 없습니다.",
    )
    return spec


class TestFilterCases:
    """기간 조회 케이스 — 시드 표 기반 + 자기일관성 (specs/2026-08-24).

    기간은 고유 날짜의 양끝을 하나씩 남기고 잡는다 — 양끝 밖에 각 1건 이상이
    남아 '걸러졌는가' 를 셀 수 있고, 경계가 실제 주문일이라 경계 포함이
    검증된다. 필터 절은 있는데 계산 근거가 무너지면 전부 경고한다.
    """

    def test_기간은_고유_날짜의_양끝을_하나씩_남기고_잡는다(self):
        cases = _filter_cases(filter_spec(), start_seq=10)
        fills = [s for s in cases[0].steps if s.action == "fill"]
        assert [s.value for s in fills] == ["2026-08-03", "2026-08-12"]

    def test_케이스_여덟_개가_생성된다(self):
        cases = _filter_cases(filter_spec(), start_seq=10)
        assert len(cases) == 8
        assert all("-filter-" in c.case_id for c in cases)

    def test_건수는_기간_내_시드_행_수다(self):
        count = _filter_cases(filter_spec(), start_seq=10)[0]
        assert count.expected.type == "result_count"
        assert count.expected.count == 3
        assert count.expected.count_target == "주문 목록"
        assert [s.action for s in count.steps] == ["navigate", "fill", "fill", "click"]

    def test_경계_포함과_기간_밖_배제를_시드의_고유값으로_확인한다(self):
        cases = _filter_cases(filter_spec(), start_seq=10)
        visible, absent = cases[1], cases[2]
        assert visible.expected.type == "text_visible"
        assert visible.expected.value == "ORD-002"  # 시작 경계일 행
        assert absent.expected.type == "text_absent"
        assert absent.expected.value == "ORD-005"  # 기간 밖 최신 행

    def test_합계와_정렬은_필터_스텝_뒤에_같은_판정을_다시_건다(self):
        cases = _filter_cases(filter_spec(), start_seq=10)
        assert cases[3].expected.type == "sum_matches"
        assert cases[3].expected.sum_row_target == "금액"
        assert cases[3].expected.sum_total_target == "합계"
        assert cases[4].expected.type == "sorted_desc"
        assert cases[4].expected.order_target == "주문일"
        assert [s.action for s in cases[4].steps] == ["navigate", "fill", "fill", "click"]

    def test_빈_기간은_최대_날짜_다음날부터다(self):
        empty = _filter_cases(filter_spec(), start_seq=10)[5]
        fills = [s.value for s in empty.steps if s.action == "fill"]
        assert fills == ["2026-08-16", "2026-08-17"]
        assert empty.expected.type == "result_count"
        assert empty.expected.count == 0

    def test_빈_문구_케이스는_기획서가_문구를_정했을_때만(self):
        spec = filter_spec()
        message = _filter_cases(spec, start_seq=10)[6]
        assert message.expected.type == "text_visible"
        assert message.expected.value == "기간 내 주문이 없습니다."
        spec.date_filter.empty_message = None
        assert len(_filter_cases(spec, start_seq=10)) == 7

    def test_빈_값_조회는_전체_건수다(self):
        full = _filter_cases(filter_spec(), start_seq=10)[-1]
        assert [s.action for s in full.steps] == ["navigate", "click"]
        assert full.expected.type == "result_count"
        assert full.expected.count == 5

    def test_필터가_없으면_케이스도_경고도_없다(self):
        spec = orders_spec()
        assert _filter_cases(spec, start_seq=10) == []
        assert spec.warnings == []

    def test_시드가_없으면_경고하고_만들지_않는다(self):
        spec = filter_spec(seed_rows=[])
        assert _filter_cases(spec, start_seq=10) == []
        assert any("기간 조회" in w for w in spec.warnings)

    def test_날짜를_읽지_못하면_경고하고_만들지_않는다(self):
        spec = filter_spec(seed_rows=[dict(r, 주문일="언젠가") for r in SEED_ROWS])
        assert _filter_cases(spec, start_seq=10) == []
        assert any("날짜로 읽지 못해" in w for w in spec.warnings)

    def test_고유_날짜가_3개_미만이면_경고하고_만들지_않는다(self):
        spec = filter_spec(seed_rows=[dict(r) for r in SEED_ROWS[:2]])
        assert _filter_cases(spec, start_seq=10) == []
        assert any("고유 날짜" in w for w in spec.warnings)

    def test_generate_cases_에_통합된다(self):
        cases = generate_cases(filter_spec())
        assert len([c for c in cases if "-filter-" in c.case_id]) == 8
