"""모델이 빠뜨린 요소를 기획서 표에서 직접 채운다 — 결정적 표 독해의 연장.

## 왜 필요한가 (2026-08-20 실측)

실모델 7B 관통에서 주문조회 화면의 요소 4개(order_list·order_date·order_amount·
order_total)가 **두 번 다 0개** 추출됐다. 로그인 3개·상품등록 4개는 성공했으므로
패턴이 분명하다 — **입력·버튼 요소는 옮기는데 표시 전용 요소(목록·텍스트)는
통째로 빠뜨린다.** 요소가 없으면 정렬·합계·건수 케이스가 생성되지 않아, 심은
결함 O1·O2 를 실행조차 못 했다.

그때 경고는 정확히 말하고 있었다 — "기획서 UI 요소 표에는 4개 요소가 있는데
추출된 것은 0개입니다." **파서가 표를 이미 읽고 있다는 뜻이다.** 대조까지만 하던
것을 백필로 올린다. 전제 계정·시드 표와 같은 원칙이다: 표에 그대로 적힌 사실은
LLM 에 맡기지 않는다.

## 채우지 않는 것

입력 검증 규칙 셀은 자유 서술("8자 이상, 대문자 1자 이상")이라 결정적으로 옮길
수 없다 — 그건 S1 에서 LLM 의 몫으로 남는다. 규칙이 적힌 요소를 백필하면
constraints 가 비었다는 사실을 경고로 알린다(위반 케이스가 생성되지 않으므로).
"""

from __future__ import annotations

from prova.models import ScreenSpec, UIElement
from prova.s1_spec_extractor.extractor import (
    _backfill_declared_elements,
    structural_warnings,
)
from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage, ParsedTable

ORDERS_TABLE = ParsedTable(rows=[
    ["요소 ID", "유형", "라벨", "필수", "입력 검증 규칙", "안내 문구", "에러 메시지"],
    ["order_list", "목록", "주문 목록", "-", "-", "-", "-"],
    ["order_date", "텍스트", "주문일", "-", "-", "-", "-"],
    ["order_amount", "텍스트", "금액", "-", "-", "-", "-"],
    ["order_total", "텍스트", "합계", "-", "-", "-", "-"],
])


def doc_with(table: ParsedTable) -> ParsedDocument:
    return ParsedDocument(source="x", pages=[ParsedPage(page_no=1, tables=[table])])


def spec_with(*elements: UIElement) -> ScreenSpec:
    return ScreenSpec(screen_id="orders", screen_name="주문 조회", url_path="/orders",
                      elements=list(elements))


class TestDeclaredElementRows:
    def test_요소_표를_행_단위로_읽는다(self):
        rows = doc_with(ORDERS_TABLE).declared_element_rows()
        assert [r["element_id"] for r in rows] == [
            "order_list", "order_date", "order_amount", "order_total"]
        assert rows[0]["type"] == "list"
        assert rows[1]["type"] == "text"
        assert rows[0]["label"] == "주문 목록"

    def test_대시는_빈_값이다(self):
        """'-' 는 기획서의 '없음' 표기다. 그대로 옮기면 placeholder='-' 인
        요소가 생겨 안내 문구 대조 케이스가 '-' 를 찾다 실패한다."""
        row = doc_with(ORDERS_TABLE).declared_element_rows()[0]
        assert row["required"] is False
        assert row["placeholder"] == ""
        assert row["error_message"] == ""
        assert row["rules"] == ""

    def test_필수와_문구_열을_옮긴다(self):
        table = ParsedTable(rows=[
            ["요소 ID", "유형", "라벨", "필수", "입력 검증 규칙", "안내 문구", "에러 메시지"],
            ["email", "입력", "이메일", "필수", "이메일 형식(@ 포함)",
             "이메일을 입력하세요", "올바른 이메일 형식을 입력하세요."],
        ])
        row = doc_with(table).declared_element_rows()[0]
        assert row["required"] is True
        assert row["placeholder"] == "이메일을 입력하세요"
        assert row["error_message"] == "올바른 이메일 형식을 입력하세요."
        assert row["rules"] == "이메일 형식(@ 포함)"

    def test_모르는_유형은_None_이다(self):
        """'멀티셀렉트' 같은 새 표현을 억지로 매핑하면 틀린 유형을 확신을 갖고
        만들게 된다 — declared_element_types 와 같은 판단."""
        table = ParsedTable(rows=[
            ["요소 ID", "유형", "라벨"],
            ["a", "멀티셀렉트", "가"],
        ])
        assert doc_with(table).declared_element_rows()[0]["type"] is None

    def test_ID나_라벨이_비면_그_행은_버린다(self):
        table = ParsedTable(rows=[
            ["요소 ID", "유형", "라벨"],
            ["", "입력", "가"],
            ["b", "입력", ""],
            ["c", "입력", "다"],
        ])
        assert [r["element_id"] for r in doc_with(table).declared_element_rows()] == ["c"]

    def test_표가_없으면_빈_목록이다(self):
        doc = ParsedDocument(source="x", pages=[ParsedPage(page_no=1)])
        assert doc.declared_element_rows() == []

    def test_규칙_열이_없으면_rules_는_None_이다(self):
        """빈 문자열('규칙 열은 있는데 셀이 비었다')과 구분해야 한다.
        열이 없으면 '규칙이 없다' 를 표가 말해 준 것이 아니므로, 소비자가
        constraints 경고를 억제하는 근거로 쓰면 안 된다."""
        table = ParsedTable(rows=[
            ["요소 ID", "유형", "라벨"],
            ["a", "입력", "가"],
        ])
        assert doc_with(table).declared_element_rows()[0]["rules"] is None


class TestBackfill:
    def test_모델이_빠뜨린_요소를_표에서_채운다(self):
        """실측 그대로의 상황 — 주문조회 요소 4개가 전부 빠졌다."""
        spec = spec_with()
        _backfill_declared_elements(spec, doc_with(ORDERS_TABLE))
        assert [e.element_id for e in spec.elements] == [
            "order_list", "order_date", "order_amount", "order_total"]
        assert spec.elements[0].type == "list"
        assert spec.elements[0].label == "주문 목록"

    def test_채운_사실을_경고로_남긴다(self):
        """도구가 판단을 했으면 그 사실이 남아야 한다. 조용히 채우면 모델이
        잘 추출하고 있다고 믿게 된다."""
        spec = spec_with()
        _backfill_declared_elements(spec, doc_with(ORDERS_TABLE))
        assert any("표에서 직접 채웠습니다" in w for w in spec.warnings)

    def test_채우면_누락_경고가_사라진다(self):
        spec = spec_with()
        _backfill_declared_elements(spec, doc_with(ORDERS_TABLE))
        assert not any("빠진 요소" in w
                       for w in structural_warnings(spec, doc_with(ORDERS_TABLE)))

    def test_이미_있는_요소는_건드리지_않는다(self):
        """모델이 표보다 풍부하게 읽었을 수 있다(본문에서 읽은 constraints 등).
        백필은 빈자리만 채운다."""
        extracted = UIElement(element_id="order_list", type="list", label="주문 목록")
        spec = spec_with(extracted)
        _backfill_declared_elements(spec, doc_with(ORDERS_TABLE))
        assert spec.elements[0] is extracted
        assert [e.element_id for e in spec.elements] == [
            "order_list", "order_date", "order_amount", "order_total"]

    def test_유형을_모르는_행은_채우지_않는다(self):
        """틀린 유형으로 채우면 목록 요소가 입력란처럼 조작되거나(오탐) 그
        반대가 된다(미탐). 못 채운 요소는 기존 누락 경고가 그대로 알린다."""
        table = ParsedTable(rows=[
            ["요소 ID", "유형", "라벨"],
            ["a", "멀티셀렉트", "가"],
        ])
        spec = spec_with()
        _backfill_declared_elements(spec, doc_with(table))
        assert spec.elements == []
        assert any("빠진 요소" in w for w in structural_warnings(spec, doc_with(table)))

    def test_필수와_문구도_함께_채운다(self):
        table = ParsedTable(rows=[
            ["요소 ID", "유형", "라벨", "필수", "입력 검증 규칙", "안내 문구", "에러 메시지"],
            ["email", "입력", "이메일", "필수", "", "이메일을 입력하세요", "형식 오류."],
        ])
        spec = spec_with()
        _backfill_declared_elements(spec, doc_with(table))
        el = spec.elements[0]
        assert el.required is True
        assert el.placeholder == "이메일을 입력하세요"
        assert el.error_message == "형식 오류."

    def test_규칙이_적힌_요소를_채우면_규칙_공백을_경고한다(self):
        """규칙 셀은 자유 서술이라 결정적으로 못 옮긴다. 채워진 요소의 위반
        케이스가 생성되지 않는다는 사실은 미탐이므로 보이게 만든다."""
        table = ParsedTable(rows=[
            ["요소 ID", "유형", "라벨", "필수", "입력 검증 규칙", "안내 문구", "에러 메시지"],
            ["password", "입력", "비밀번호", "필수", "8자 이상", "-", "-"],
        ])
        spec = spec_with()
        _backfill_declared_elements(spec, doc_with(table))
        assert spec.elements[0].constraints == {}
        assert any("위반 케이스" in w and "비밀번호" in w for w in spec.warnings)

    def test_규칙이_없는_요소는_규칙_경고를_내지_않는다(self):
        """주문조회처럼 표시 전용 요소만 채우는 경우까지 경고하면 늑대 소리가
        된다 — 진짜 경고가 묻힌다."""
        spec = spec_with()
        _backfill_declared_elements(spec, doc_with(ORDERS_TABLE))
        assert not any("위반 케이스" in w for w in spec.warnings)

    def test_같은_라벨의_요소가_이미_있으면_채우지_않는다(self):
        """모델이 요소를 빠뜨린 게 아니라 ID 를 지어낸 경우다 — 실측에서
        screen_id 를 지어낸 전례가 있는 실패 모양. id 만 대조해 채우면 같은
        라벨의 요소가 둘이 되어, 그라운딩의 '정확히 1개' 원칙과 충돌하고
        케이스가 중복 생성된다."""
        invented = UIElement(element_id="orders_list", type="list", label="주문 목록")
        spec = spec_with(invented)
        _backfill_declared_elements(spec, doc_with(ORDERS_TABLE))
        ids = [e.element_id for e in spec.elements]
        assert "order_list" not in ids, "라벨이 겹치면 쌍둥이를 만들면 안 된다"
        assert ids[0] == "orders_list"
        assert any("orders_list" in w and "주문 목록" in w for w in spec.warnings), (
            "ID 가 다르게 추출됐을 가능성을 사람에게 알려야 한다"
        )
        # 라벨이 겹치지 않는 나머지는 정상적으로 채운다
        assert {"order_date", "order_amount", "order_total"} <= set(ids)


class TestSingleSourceColumns:
    """열 찾기 규칙은 한 곳(_ELEMENT_COLUMNS)이다 (2026-08-22).

    그 전에는 독해 함수 여섯 개가 각자 열을 찾았고 실제로 어긋나 있었다 — 안내
    문구 열을 백필은 "안내" 로, declared_placeholders 는 "안내 or placeholder" 로
    찾아, 헤더가 'Placeholder' 인 기획서에서 백필된 요소가 곧바로 '모델이 틀렸다'
    경고를 받았다. 두 독해가 같은 표에서 같은 답을 내는지 못 박는다.
    """

    TABLE = ParsedTable(rows=[
        ["요소 ID", "유형", "라벨", "Placeholder"],
        ["email", "입력", "이메일", "이메일을 입력하세요"],
    ])

    def test_영문_헤더도_두_독해가_같은_안내_문구를_읽는다(self):
        doc = doc_with(self.TABLE)
        rows = {r["label"]: r["placeholder"] for r in doc.declared_element_rows()}
        assert rows == doc.declared_placeholders() == {"이메일": "이메일을 입력하세요"}

    def test_유형과_라벨_대응도_행_독해와_같다(self):
        doc = doc_with(self.TABLE)
        assert doc.declared_element_types() == {"이메일": "input"}
        assert doc.declared_label_to_id() == {"이메일": "email"}
