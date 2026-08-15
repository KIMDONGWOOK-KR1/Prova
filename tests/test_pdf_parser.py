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
