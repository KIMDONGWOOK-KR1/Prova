"""pdf_parser 테스트 — 실제 기획서 PDF를 상대로 검증한다.

여기서 확인하려는 것: LLM에 넘길 텍스트에 '기획서가 담은 정보가 빠짐없이,
구조를 유지한 채' 들어 있는가. 특히 표의 열 이름이 살아 있어야 LLM이
어느 값이 검증 규칙인지 에러 메시지인지 판단할 수 있다.
"""

from pathlib import Path

import pytest

from prova.s1_spec_extractor.pdf_parser import ParsedPage, ParsedTable, parse_pdf
from prova.text_utils import contains_loose

SPEC_PDF = Path("fixtures/specs/login_spec.pdf")


@pytest.fixture(scope="module")
def doc():
    if not SPEC_PDF.exists():
        pytest.skip("먼저 `uv run python scripts/make_spec_pdf.py` 를 실행하세요")
    return parse_pdf(SPEC_PDF)


class TestParsedTable:
    def test_마크다운_변환에_구분선이_들어간다(self):
        t = ParsedTable(rows=[["항목", "내용"], ["화면 ID", "login"]])
        md = t.to_markdown()
        assert "| 항목 | 내용 |" in md
        assert "|---|---|" in md
        assert "| 화면 ID | login |" in md

    def test_열수가_다른_행은_빈칸으로_채운다(self):
        t = ParsedTable(rows=[["a", "b", "c"], ["1"]])
        assert "| 1 |  |  |" in t.to_markdown()

    def test_빈_표는_빈_문자열(self):
        assert ParsedTable().to_markdown() == ""


class TestParsePdf:
    def test_두_페이지를_읽는다(self, doc):
        assert len(doc.pages) == 2

    def test_요소정의_표의_열이름이_보존된다(self, doc):
        """이게 깨지면 LLM이 값의 의미를 판단할 근거를 잃는다."""
        headers = [t.header for t in doc.all_tables]
        element_table = next((h for h in headers if "요소 ID" in h), None)
        assert element_table is not None, f"요소 정의 표를 못 찾음. headers={headers}"
        for col in ["유형", "라벨", "필수", "입력 검증 규칙", "에러 메시지"]:
            assert col in element_table

    def test_본문에서_표가_제거된다(self, doc):
        """표 영역을 걸러내지 못하면 같은 내용이 두 번 들어가 프롬프트가 부풀고
        LLM이 열 대응을 헷갈린다."""
        body = "\n".join(p.body_text for p in doc.pages)
        assert "2. UI 요소 정의" in body                # 제목은 본문에 남는다
        # 표에만 등장하는 값들은 본문에서 빠져야 한다.
        # (에러 메시지 문구는 표와 §2-1 본문에 모두 나오므로 판별 기준이 못 된다)
        assert not contains_loose(body, "user@test.com")   # §5 테스트 계정 표
        assert not contains_loose(body, "Abcd123!")        # §5 테스트 계정 표
        assert not contains_loose(body, "login_btn")       # §2 요소 정의 표

    def test_비밀번호_규칙이_어딘가에_전부_들어있다(self, doc):
        text = doc.to_llm_text()
        for fragment in ["8자 이상", "대문자", "특수문자"]:
            assert contains_loose(text, fragment), f"'{fragment}' 누락"

    def test_에러메시지_문구가_보존된다(self, doc):
        text = doc.to_llm_text()
        assert contains_loose(text, "올바른 이메일 형식을 입력하세요.")
        assert contains_loose(
            text, "비밀번호는 8자 이상이며 대문자·특수문자를 각 1자 이상 포함해야 합니다."
        )
        assert contains_loose(text, "이메일 또는 비밀번호가 올바르지 않습니다.")

    def test_성공조건이_보존된다(self, doc):
        text = doc.to_llm_text()
        assert contains_loose(text, "/dashboard")
        assert contains_loose(text, "환영합니다")

    def test_cid_아티팩트가_남지_않는다(self, doc):
        """폰트 글리프 누락 자리표시자가 프롬프트에 섞이면 안 된다."""
        assert "cid:" not in doc.to_llm_text()

    def test_없는_파일은_명확한_에러(self):
        with pytest.raises(FileNotFoundError):
            parse_pdf("fixtures/specs/nope.pdf")


class TestDeclaredElementIds:
    """LLM 없이 표에서 읽어 낸 요소 ID 목록.

    이 목록의 용도는 두 가지다. 프롬프트에 넣어 LLM 이 행을 빠뜨리지 않게 하고,
    추출 결과와 대조해 빠진 요소를 경고한다. 실측에서 7B 가 7행 표의 버튼 행을
    빠뜨린 일이 있었고, 제출 버튼이 없으면 **구현이 옳아도 전 케이스가 실패로
    보고된다** — 경고 없이 나오면 가장 위험한 리포트가 된다.
    """

    def test_로그인_기획서의_요소_ID를_순서대로_읽는다(self, doc):
        assert doc.declared_element_ids() == ["email", "password", "login_btn"]

    def test_회원가입_기획서의_요소_ID를_순서대로_읽는다(self):
        pdf = Path("fixtures/specs/signup_spec.pdf")
        if not pdf.exists():
            pytest.skip("먼저 `uv run python scripts/make_spec_pdf.py` 를 실행하세요")
        assert parse_pdf(pdf).declared_element_ids() == [
            "email", "password", "password_confirm", "nickname",
            "signup_path", "agree_terms", "signup_btn", "to_login",
        ], "표가 페이지를 넘어가도 행을 빠뜨리지 않아야 한다"

    def test_ID_열이_없으면_빈_목록이다(self, tmp_path):
        """대조할 근거가 없으면 검사하지 않는 것이 맞다. 있는 것처럼 추측하면
        없는 누락을 경고하게 된다."""
        from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage

        doc = ParsedDocument(source="x", pages=[ParsedPage(
            page_no=1,
            tables=[ParsedTable(rows=[["상황", "처리"], ["비어 있음", "에러 노출"]])],
        )])
        assert doc.declared_element_ids() == []

    def test_요소_표와_다른_표를_섞어_보지_않는다(self):
        """'요소 ID' 와 '유형' 이 함께 있는 표만 요소 정의 표로 본다.
        하나만으로 판단하면 실패 조건 표를 요소 표로 착각한다."""
        from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage

        doc = ParsedDocument(source="x", pages=[ParsedPage(
            page_no=1,
            tables=[
                ParsedTable(rows=[["항목", "내용"], ["화면 ID", "login"]]),
                ParsedTable(rows=[["요소 ID", "유형"], ["email", "입력"]]),
            ],
        )])
        assert doc.declared_element_ids() == ["email"]


class TestDeclaredElementTypes:
    """요소 유형도 표에서 읽는다 — 확장 과정에서 네 번 같은 실패를 겪은 결론의 적용.

    유형이 틀리면 검증이 조용히 사라진다. 목록 요소를 text 로 읽으면 건수 검증이
    아예 만들어지지 않고(미탐), 입력란을 목록으로 읽으면 값을 채우지 않아 정상
    케이스까지 실패한다(오탐).
    """

    def test_로그인_기획서의_유형을_읽는다(self, doc):
        assert doc.declared_element_types() == {
            "이메일": "input", "비밀번호": "input", "로그인": "button"}

    def test_목록_유형을_읽는다(self):
        pdf = Path("fixtures/specs/search_spec.pdf")
        if not pdf.exists():
            pytest.skip("먼저 `uv run python scripts/make_spec_pdf.py` 를 실행하세요")
        assert parse_pdf(pdf).declared_element_types()["검색 결과 목록"] == "list"

    def test_모르는_표현은_매핑하지_않는다(self):
        """새 유형을 억지로 매핑하면 틀린 유형을 확신을 갖고 덮어쓴다.
        모르면 LLM 의 판단을 남겨 두는 편이 낫다."""
        from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage

        doc = ParsedDocument(source="x", pages=[ParsedPage(
            page_no=1,
            tables=[ParsedTable(rows=[
                ["요소 ID", "유형", "라벨"],
                ["a", "입력", "가"],
                ["b", "멀티셀렉트", "나"],
            ])],
        )])
        assert doc.declared_element_types() == {"가": "input"}


class TestDeclaredDateFilter:
    """'날짜 필터' 절의 항목|값 표 — 케이스 생성의 결정적 근거 (specs/2026-08-24).

    화면 개요 표와 헤더('항목|값')가 같아 열 제목만으로는 구분할 수 없다.
    declared_precondition_account 처럼 절 제목 위치로 찾는다.
    """

    def test_orders_기획서의_날짜_필터_표를_읽는다(self):
        pdf = Path("fixtures/specs/orders_spec.pdf")
        if not pdf.exists():
            pytest.skip("먼저 `uv run python scripts/make_spec_pdf.py` 를 실행하세요")
        docs, _ = parse_pdf(pdf).split_screens()
        got = docs[-1].declared_date_filter()
        assert got == {
            "시작일 요소": "시작일", "종료일 요소": "종료일", "조회 버튼": "조회",
            "대상 목록": "주문 목록", "날짜 컬럼": "주문일",
            "빈 결과 문구": "기간 내 주문이 없습니다.",
            "기간 역전 문구": "종료일은 시작일보다 빠를 수 없습니다.",
        }

    def test_절이_없는_기획서는_None(self, doc):
        assert doc.declared_date_filter() is None


class TestDateElementType:
    """유형 '날짜' — 자동 채움에서 빠지는 입력 (specs/2026-08-24 날짜 필터).

    유형 '입력' 으로 두면 정상 케이스가 규칙 없는 이 필드에 자유 문자열
    견본값을 채우려 하는데, input[type=date] 는 ISO 날짜만 받아 fill 이
    깨진다. 날짜 입력의 값은 filter 케이스가 시드 표에서 계산해 넣는다.
    """

    def test_유형_날짜가_date_로_매핑된다(self):
        from prova.s1_spec_extractor.pdf_parser import ELEMENT_TYPE_WORDS
        assert ELEMENT_TYPE_WORDS["날짜"] == "date"

    def test_date_는_자동_채움_대상이_아니다(self):
        from prova.models import ScreenSpec, UIElement
        from prova.s2_case_generator.generator import _fillable_inputs
        spec = ScreenSpec(
            screen_id="s", screen_name="s", url_path="/s",
            elements=[UIElement(element_id="start_date", type="date", label="시작일")],
        )
        assert _fillable_inputs(spec) == []


class TestForbiddenTextColumn:
    """'노출되면 안 되는 문구' 열 — 지금까지와 방향이 반대인 요구사항.

    비밀번호 찾기 화면에서 필요해졌다. 등록되지 않은 이메일에 '등록되지 않은
    이메일입니다' 를 노출하면 공격자가 계정 존재 여부를 알아낸다.

    건수 열은 값의 모양(전부 정수)으로 찾는데 이 열은 그럴 수 없다 — 값이 문구라서
    기대 문구 열과 모양이 같다. 그래서 헤더로 찾고, 그 판별이 정확해야 한다.
    두 열이 섞이면 성공 문구를 금지 문구로 읽어 **올바른 화면을 FAIL 로** 만든다.
    """

    def _doc(self, header: list[str], row: list[str]):
        from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage

        return ParsedDocument(source="x", pages=[ParsedPage(
            page_no=1,
            tables=[
                ParsedTable(rows=[["요소 ID", "유형", "라벨"],
                                  ["email", "입력", "이메일"]]),
                ParsedTable(rows=[header, row]),
            ],
        )])

    @pytest.mark.parametrize("header", [
        "노출되면 안 되는 문구",
        "노출되지 않아야 하는 문구",
        "금지 문구",
        "보이지 않아야 하는 문구",
    ])
    def test_다양한_헤더_표현을_받는다(self, header):
        """기획서마다 다르게 쓴다. 표현을 하나 놓칠 때마다 이 검증이 조용히 빠진다."""
        doc = self._doc(["이메일", "노출돼야 하는 문구", header],
                        ["a@b.com", "보냈습니다.", "등록되지 않았습니다."])
        got = doc.declared_scenarios()
        assert got == [{"given": {"email": "a@b.com"},
                        "expect_text": "보냈습니다.",
                        "expect_count": None,
                        "expect_absent": "등록되지 않았습니다."}]

    def test_기대_문구_열을_금지로_읽지_않는다(self):
        """**두 열이 섞이면 올바른 화면이 FAIL 이 된다.** 성공 문구를 '나타나면
        안 되는 것' 으로 읽으면 그 문구를 띄우는 정상 구현이 실패한다."""
        doc = self._doc(["이메일", "노출돼야 하는 문구"], ["a@b.com", "보냈습니다."])
        got = doc.declared_scenarios()
        assert got[0]["expect_text"] == "보냈습니다."
        assert got[0]["expect_absent"] is None

    def test_금지_열이_없으면_None이다(self):
        """기획서가 그 열을 안 쓰면 이 검증을 만들지 않는다 — 억측하지 않는다."""
        doc = self._doc(["이메일", "노출돼야 하는 문구", "비고"],
                        ["a@b.com", "보냈습니다.", "메일 발송 로그 확인"])
        assert doc.declared_scenarios()[0]["expect_absent"] is None

    def test_빈_칸은_None이다(self):
        """행마다 금지 문구가 있을 이유는 없다. 빈 문자열을 그대로 쓰면 '빈 문구가
        화면에 없는가' 를 확인하게 되고, 그건 항상 실패한다."""
        doc = self._doc(["이메일", "노출돼야 하는 문구", "노출되면 안 되는 문구"],
                        ["a@b.com", "보냈습니다.", ""])
        assert doc.declared_scenarios()[0]["expect_absent"] is None

    def test_건수_열과도_섞이지_않는다(self):
        doc = self._doc(["이메일", "노출돼야 하는 문구", "건수", "노출되면 안 되는 문구"],
                        ["a@b.com", "보냈습니다.", "0", "등록되지 않았습니다."])
        got = doc.declared_scenarios()[0]
        assert got["expect_text"] == "보냈습니다."
        assert got["expect_count"] == 0
        assert got["expect_absent"] == "등록되지 않았습니다."


class TestDeclaredScenarioCounts:
    """예시 표의 건수 열.

    열 제목이 아니라 값의 모양으로 찾는다. 기획서마다 '결과 건수'·'개수'·'건수'
    로 다르게 쓰는데, 표현을 하나 놓칠 때마다 건수 검증이 조용히 빠진다.
    """

    def test_검색_기획서의_건수를_읽는다(self):
        pdf = Path("fixtures/specs/search_spec.pdf")
        if not pdf.exists():
            pytest.skip("먼저 `uv run python scripts/make_spec_pdf.py` 를 실행하세요")
        scenarios = parse_pdf(pdf).declared_scenarios()
        assert [(s["given"]["query"], s["expect_count"]) for s in scenarios] == [
            ("notebook", 3), ("zzzz", 0)]

    def test_문구_열의_숫자를_건수로_읽지_않는다(self):
        """"검색 결과 3건" 은 정수가 아니므로 건수 열이 아니다. 여기서 숫자를
        뽑아내면 화면이 문구를 안 찍을 때 건수 검증이 사라진다."""
        from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage

        doc = ParsedDocument(source="x", pages=[ParsedPage(
            page_no=1,
            tables=[
                ParsedTable(rows=[["요소 ID", "유형", "라벨"], ["query", "입력", "검색어"]]),
                ParsedTable(rows=[["검색어", "노출돼야 하는 문구"],
                                  ["notebook", "검색 결과 3건"]]),
            ],
        )])
        assert doc.declared_scenarios() == [
            {"given": {"query": "notebook"}, "expect_text": "검색 결과 3건",
             "expect_count": None, "expect_absent": None}]

    def test_건수_열만_있고_문구_열이_없으면_시나리오가_아니다(self):
        """기대 문구가 없으면 대조할 문구 케이스를 만들 수 없다. 그 표는 예시
        시나리오 표가 아니므로 여기서 걸러진다."""
        from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage

        doc = ParsedDocument(source="x", pages=[ParsedPage(
            page_no=1,
            tables=[
                ParsedTable(rows=[["요소 ID", "유형", "라벨"], ["query", "입력", "검색어"]]),
                ParsedTable(rows=[["검색어", "결과 건수"], ["notebook", "3"]]),
            ],
        )])
        assert doc.declared_scenarios() == []


def _doc(*pages):
    """페이지별 표 목록으로 ParsedDocument 를 만든다."""
    from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage

    return ParsedDocument(source="x", pages=[
        ParsedPage(page_no=i, tables=[ParsedTable(rows=rows) for rows in tables])
        for i, tables in enumerate(pages, 1)
    ])


def _overview(screen_id):
    return [["항목", "내용"], ["화면 ID", screen_id], ["화면 경로", f"/{screen_id}"]]


class TestSplitScreens:
    """한 문서에 여러 화면 — 경계는 화면 개요 표의 등장으로 정한다."""

    def test_개요_표가_없으면_한_화면이다(self):
        """화면당 PDF 하나였던 기존 기획서가 그대로 동작해야 한다."""
        doc = _doc([[["요소 ID", "유형"], ["email", "입력"]]])
        docs, warns = doc.split_screens()
        assert len(docs) == 1 and docs[0] is doc and warns == []

    def test_페이지마다_새_화면을_시작한다(self):
        doc = _doc([_overview("login")], [_overview("signup")])
        docs, warns = doc.split_screens()
        assert [d.declared_screen_meta()["screen_id"] for d in docs] == ["login", "signup"]
        assert warns == []

    def test_이어지는_페이지는_앞_화면에_붙는다(self):
        doc = _doc([_overview("login")], [], [_overview("signup")])
        docs, _ = doc.split_screens()
        assert [len(d.pages) for d in docs] == [2, 1]

    def test_표지_페이지는_첫_화면에_붙는다(self):
        """별도 문서로 떼면 요소가 없는 빈 '화면' 이 하나 생긴다. 버리면 앞머리에
        적힌 화면 공통 규칙이 조용히 사라진다."""
        doc = _doc([], [_overview("login")])
        docs, _ = doc.split_screens()
        assert len(docs) == 1
        assert [p.page_no for p in docs[0].pages] == [1, 2]

    def test_한_페이지에_두_화면이면_경고한다(self):
        """페이지 단위로는 가를 수 없다. 앞 화면에 몰아 넣으면 뒤 화면의 요소 표가
        앞 화면 것으로 추출되어 두 화면의 검증이 모두 조용히 어긋난다."""
        doc = _doc([_overview("login"), _overview("signup")])
        docs, warns = doc.split_screens()
        assert len(docs) == 1
        assert warns and "2개" in warns[0]


class TestDeclaredFlows:
    def test_흐름_표를_읽는다(self):
        doc = _doc([[["흐름 ID", "화면 순서"], ["signup_then_login", "signup → login"]]])
        assert doc.declared_flows() == [
            {"flow_id": "signup_then_login", "screen_ids": ["signup", "login"],
             "via": [], "expect_text": ""}]

    def test_이동_방법_열을_읽는다(self):
        """이 열이 없으면 도구가 주소를 직접 쳐서 들어가므로, 화면을 잇는 요소가
        아예 검증되지 않는다."""
        doc = _doc([[["흐름 ID", "화면 순서", "이동 방법"],
                     ["f", "signup → login", "로그인하러 가기"]]])
        assert doc.declared_flows()[0]["via"] == ["로그인하러 가기"]

    def test_이동_방법의_공백을_지우지_않는다(self):
        """화면 ID 와 달리 여기 오는 값은 화면에 보이는 라벨이고 공백이 라벨의
        일부다. 지우면 S3 가 요소를 못 찾는다."""
        doc = _doc([[["흐름 ID", "화면 순서", "이동 방법"],
                     ["f", "a → b", "로그인하러 가기"]]])
        assert doc.declared_flows()[0]["via"] == ["로그인하러 가기"]

    def test_하이픈은_해당_없음으로_본다(self):
        """'-' 를 라벨로 받으면 S3 가 화면에서 '-' 를 찾다 실패해, 이동 방법을
        안 적은 흐름이 전부 끊긴다."""
        doc = _doc([[["흐름 ID", "화면 순서", "이동 방법"], ["f", "a → b", "-"]]])
        assert doc.declared_flows()[0]["via"] == []

    def test_앞_전이가_하이픈이면_자리를_비워_둔다(self):
        """3화면 이상에서만 드러나는 어긋남이다.

        전이가 하나뿐이면 '-' 를 지워도 무해하지만, 전이가 둘이면 자리까지
        지워져서 **뒤 전이의 라벨이 앞 전이에 붙는다.** 기획서는 'a→b 는 주소로,
        b→c 는 링크로' 라고 적었는데 도구는 a→b 에서 링크를 누른다 — 적힌 것과
        다른 것이 돌면서 아무도 모른다.
        """
        doc = _doc([[["흐름 ID", "화면 순서", "이동 방법"],
                     ["f", "a → b → c", "- → 로그인하러 가기"]]])
        assert doc.declared_flows()[0]["via"] == ["", "로그인하러 가기"]

    def test_뒤쪽_하이픈은_자리를_남기지_않는다(self):
        """뒤가 비면 생성기가 범위를 벗어나 주소 이동으로 처리한다 — 자리를
        남길 필요가 없고, 남기지 않아야 전이가 하나뿐인 흐름의 값이 그대로다."""
        doc = _doc([[["흐름 ID", "화면 순서", "이동 방법"],
                     ["f", "a → b → c", "로그인하러 가기 → -"]]])
        assert doc.declared_flows()[0]["via"] == ["로그인하러 가기"]

    def test_이동_방법을_확인_문구로_착각하지_않는다(self):
        doc = _doc([[["흐름 ID", "화면 순서", "이동 방법", "확인 문구"],
                     ["f", "a → b", "링크", "환영합니다"]]])
        flow = doc.declared_flows()[0]
        assert flow["via"] == ["링크"] and flow["expect_text"] == "환영합니다"

    def test_확인_문구_열이_있으면_읽는다(self):
        doc = _doc([[["흐름 ID", "화면 순서", "확인 문구"],
                     ["a_b", "a -> b", "환영합니다"]]])
        assert doc.declared_flows()[0]["expect_text"] == "환영합니다"

    def test_화면이_하나면_흐름이_아니다(self):
        """한 화면만 밟는 것은 그 화면의 정상 케이스와 같다. 흐름으로 또 만들면
        같은 것을 두 번 검증하고, 실패가 두 곳에 뜬다."""
        doc = _doc([[["흐름 ID", "화면 순서"], ["only", "login"]]])
        assert doc.declared_flows() == []

    def test_구분자가_달라도_읽는다(self):
        """화살표 표현이 기획서마다 다르고 PDF 변환에서 모양이 바뀌기도 한다.
        하나를 놓치면 흐름이 화면 하나로 읽혀 조용히 사라진다."""
        for sep in ("→", "->", ">", ","):
            doc = _doc([[["흐름 ID", "화면 순서"], ["f", f"a {sep} b"]]])
            assert doc.declared_flows()[0]["screen_ids"] == ["a", "b"], sep

    def test_흐름_표가_없으면_빈_목록이다(self):
        doc = _doc([_overview("login")])
        assert doc.declared_flows() == []


class TestDeclaredRequiredMessage:
    """필수 입력 문구도 실패 조건 표에 그대로 적혀 있다.

    화면을 한 문서에 모으자 7B 가 이 값을 few-shot 예시의 문구로 채웠고, 그것이
    오탐으로 이어졌다 — 구현이 올바른 문구를 노출하는데 기대 문구가 달라 FAIL 이 된다.
    """

    def test_실패_조건_표에서_읽는다(self):
        doc = _doc([[["상황", "처리"],
                     ["검색어가 비어 있음", '"검색어를 입력하세요." 노출'],
                     ["길이 규칙 위반", '"2자 이상 입력하세요." 노출']]])
        assert doc.declared_required_message() == "검색어를 입력하세요."

    def test_후보가_여럿이면_판별을_포기한다(self):
        """어느 것이 화면 공통 문구인지 알 수 없다. 억측한 문구는 오탐이 된다."""
        doc = _doc([[["상황", "처리"],
                     ["이메일이 비어 있음", '"이메일을 입력하세요." 노출'],
                     ["비밀번호가 비어 있음", '"비밀번호를 입력하세요." 노출']]])
        assert doc.declared_required_message() is None

    def test_실제_기획서_세_화면(self):
        for stem, want in (("login", "필수 입력 항목입니다."),
                           ("signup", "필수 입력 항목입니다."),
                           ("search", "검색어를 입력하세요.")):
            pdf = Path(f"fixtures/specs/{stem}_spec.pdf")
            if not pdf.exists():
                pytest.skip("먼저 `uv run python scripts/make_spec_pdf.py` 를 실행하세요")
            assert parse_pdf(pdf).declared_required_message() == want, stem

    def test_개요_표를_실패_조건_표로_착각하지_않는다(self):
        """둘 다 2열이므로 열 제목으로 갈라야 한다 — 개요는 '항목|내용' 이다."""
        doc = _doc([_overview("login")])
        assert doc.declared_required_message() is None

    def test_선택_미이행은_공통_문구로_보지_않는다(self):
        """'가입 경로를 선택하지 않음' 은 요소 하나의 상태에 대한 문구다. 공통
        문구 후보에 넣으면 회원가입 기획서에서 후보가 셋이 되어 판별을 포기한다."""
        doc = _doc([[["상황", "처리"],
                     ["필수 입력값이 비어 있음", '"필수 입력 항목입니다." 노출'],
                     ["가입 경로를 선택하지 않음", '"가입 경로를 선택하세요." 노출'],
                     ["약관에 동의하지 않음", '"약관에 동의해야 합니다." 노출']]])
        assert doc.declared_required_message() == "필수 입력 항목입니다."


class TestSplitTableMerge:
    """페이지 경계에서 잘린 표 잇기 — 뒷조각이 조용히 사라지던 구멍 (2026-08-25).

    날짜 필터 작업에서 실제로 겪었다: §2 에 행이 늘자 §5 시드 표가 페이지를
    넘어갔고 declared_seed_rows 가 앞 조각(4행)만 읽었다. 요소 표는 같은 사고
    후 병합 장치가 있었지만(_element_table), 절 제목 기반 탐색은 없었다.

    연속 조각 판별은 엄격하다 — 다음 페이지의 첫 표 + 헤더 동일 + 그 위에
    본문 줄 없음. 헤더만 보면 전제 계정 표와 테스트 계정 표(둘 다
    '이메일|비밀번호')처럼 다른 절의 표를 삼킨다.
    """

    HEADER = ["주문번호", "주문일", "금액"]

    def _page(self, no, body_lines, tables):
        return ParsedPage(
            page_no=no,
            body_text=" ".join(t for t, _ in body_lines),
            body_lines=body_lines,
            tables=tables,
        )

    def _doc(self, pages):
        from prova.s1_spec_extractor.pdf_parser import ParsedDocument
        return ParsedDocument(source="x", pages=pages)

    def _anchor_page(self, rows):
        return self._page(1, [("5. 테스트 주문 데이터", 10.0)],
                          [ParsedTable(rows=[self.HEADER] + rows, top=30.0)])

    def test_다음_페이지로_넘어간_행을_이어_붙인다(self):
        doc = self._doc([
            self._anchor_page([["ORD-2", "2026-08-02", "200"]]),
            self._page(2, [], [ParsedTable(
                rows=[self.HEADER, ["ORD-1", "2026-08-01", "100"]], top=5.0)]),
        ])
        rows = doc.declared_seed_rows()
        assert [r["주문번호"] for r in rows] == ["ORD-2", "ORD-1"]

    def test_세_페이지_연쇄도_잇는다(self):
        doc = self._doc([
            self._anchor_page([["ORD-3", "2026-08-03", "300"]]),
            self._page(2, [], [ParsedTable(
                rows=[self.HEADER, ["ORD-2", "2026-08-02", "200"]], top=5.0)]),
            self._page(3, [], [ParsedTable(
                rows=[self.HEADER, ["ORD-1", "2026-08-01", "100"]], top=5.0)]),
        ])
        assert len(doc.declared_seed_rows()) == 3

    def test_위에_본문이_있는_표는_다른_절의_표다(self):
        """전제 계정/테스트 계정처럼 헤더가 같은 다른 절의 표를 삼키면 없는
        행을 만들어낸다 — 절 제목이 위에 있으면 연속이 아니다."""
        doc = self._doc([
            self._anchor_page([["ORD-2", "2026-08-02", "200"]]),
            self._page(2, [("6. 지난 주문 보관", 10.0)], [ParsedTable(
                rows=[self.HEADER, ["OLD-1", "2025-01-01", "999"]], top=30.0)]),
        ])
        assert [r["주문번호"] for r in doc.declared_seed_rows()] == ["ORD-2"]

    def test_헤더가_다르면_잇지_않는다(self):
        doc = self._doc([
            self._anchor_page([["ORD-2", "2026-08-02", "200"]]),
            self._page(2, [], [ParsedTable(
                rows=[["이메일", "비밀번호"], ["a@b.c", "pw"]], top=5.0)]),
        ])
        assert len(doc.declared_seed_rows()) == 1

    def test_앵커가_페이지_마지막_표가_아니면_잇지_않는다(self):
        """분할은 페이지 끝에서만 일어난다 — 앵커 뒤에 같은 페이지의 다른 표가
        있으면 그 페이지에서 표가 잘리지 않았다는 뜻이다."""
        doc = self._doc([
            self._page(1, [("5. 테스트 주문 데이터", 10.0)], [
                ParsedTable(rows=[self.HEADER, ["ORD-2", "2026-08-02", "200"]], top=30.0),
                ParsedTable(rows=[["항목", "값"], ["비고", "-"]], top=90.0),
            ]),
            self._page(2, [], [ParsedTable(
                rows=[self.HEADER, ["ORD-1", "2026-08-01", "100"]], top=5.0)]),
        ])
        assert len(doc.declared_seed_rows()) == 1

    def test_날짜_필터_표도_잘리면_잇는다(self):
        filter_header = ["항목", "값"]
        doc = self._doc([
            self._page(1, [("6. 날짜 필터", 10.0)], [ParsedTable(
                rows=[filter_header, ["시작일 요소", "시작일"],
                      ["종료일 요소", "종료일"], ["조회 버튼", "조회"],
                      ["대상 목록", "주문 목록"]], top=30.0)]),
            self._page(2, [], [ParsedTable(
                rows=[filter_header, ["날짜 컬럼", "주문일"]], top=5.0)]),
        ])
        got = doc.declared_date_filter()
        assert got is not None and got["날짜 컬럼"] == "주문일"

    def test_잘린_조각이_예시_표로_오독되지_않는다(self):
        """시드 표 열 제목(주문일·금액)은 요소 라벨과 겹친다 — 연속 조각이
        정체성 검사를 빠져나가면 존재하지 않는 시나리오가 만들어진다."""
        from prova.s1_spec_extractor.pdf_parser import ParsedDocument
        element_table = ParsedTable(rows=[
            ["요소 ID", "유형", "라벨"],
            ["order_date", "텍스트", "주문일"],
            ["order_amount", "텍스트", "금액"],
        ], top=20.0)
        doc = ParsedDocument(source="x", pages=[
            self._page(1, [("2. UI 요소 정의", 10.0), ("5. 테스트 주문 데이터", 60.0)], [
                element_table,
                ParsedTable(rows=[self.HEADER, ["ORD-2", "2026-08-02", "200"]], top=80.0),
            ]),
            self._page(2, [], [ParsedTable(
                rows=[self.HEADER, ["ORD-1", "2026-08-01", "100"]], top=5.0)]),
        ])
        assert len(doc.declared_seed_rows()) == 2
        assert doc.declared_scenarios() == []
