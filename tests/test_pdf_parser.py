"""pdf_parser 테스트 — 실제 기획서 PDF를 상대로 검증한다.

여기서 확인하려는 것: LLM에 넘길 텍스트에 '기획서가 담은 정보가 빠짐없이,
구조를 유지한 채' 들어 있는가. 특히 표의 열 이름이 살아 있어야 LLM이
어느 값이 검증 규칙인지 에러 메시지인지 판단할 수 있다.
"""

from pathlib import Path

import pytest

from prova.s1_spec_extractor.pdf_parser import ParsedTable, parse_pdf
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
            "signup_path", "agree_terms", "signup_btn",
        ]

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
             "expect_count": None}]

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
