"""페이지명 머리말로 나뉜 화면 — 이름·ID 는 코드가 기획서에서 읽는다 (2026-11-06 실물).

화면 ID 개요 표가 없는 화면기획서에서 모델은 화면 이름을 바꿔 불렀고('SUPPORT' →
'고객 지원', 칸이 갈린 '장|바구니' → '바구니'), ID 를 겹쳐 지었다(product_detail
네 번). 겹친 ID 는 case_id·스크린샷 경로가 서로를 덮는다.
"""

from __future__ import annotations

from prova.s1_spec_extractor.extractor import extract_screen_spec, page_screen_id
from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage, ParsedTable


class _Fixed:
    def complete_json(self, *, system, user, schema, max_tokens=2048, temperature=0.0):
        return {"screen_id": "product_detail", "screen_name": "고객 지원", "url_path": "/support",
                "elements": [], "success_condition": "", "warnings": []}


def _doc(name_cells):
    return ParsedDocument(source="x", pages=[ParsedPage(page_no=1, tables=[ParsedTable(rows=[
        ["프로젝트", "OO 홈페이지 개발", "작성자", "홍길동"],
        list(name_cells),
        ["*성명", "성명을 입력하세요.", "", ""],
    ])])])


def test_화면_이름은_기획서의_페이지명이다():
    spec = extract_screen_spec(_doc(["페이지명", "SUPPORT", "페이지", "사용자"]), _Fixed())
    assert spec.screen_name == "SUPPORT"
    assert spec.screen_id == page_screen_id("SUPPORT") == "support"


def test_ID_는_페이지명에서_만들어_겹치지_않는다():
    a = page_screen_id("SHOP > Book List > 자세히보기")
    b = page_screen_id("SHOP > Gift Card > 자세히보기")
    assert a != b
    assert all(ch not in a for ch in '<>:"/\|?* ')  # 스크린샷 파일 이름에 들어간다
    assert a == "shop_book_list_자세히보기"


def test_화면_ID_개요_표가_있으면_건드리지_않는다():
    doc = ParsedDocument(source="x", pages=[ParsedPage(page_no=1, tables=[
        ParsedTable(rows=[["항목", "내용"], ["화면 ID", "login"]]),
        ParsedTable(rows=[["페이지명", "로그인", "페이지", "사용자"]]),
    ])])
    spec = extract_screen_spec(doc, _Fixed())
    assert spec.screen_name == "고객 지원"  # 이 경로는 예전 그대로 모델 값


def test_기획서에_없는_경로는_쓰지_않는다():
    """기획서에 URL 이 한 줄도 없었는데 모델이 '/support' 를 지었다. 그 경로로 열면
    없는 페이지라 '페이지 오류' 가 되고, 실제로는 멀쩡한 화면이 실패로 보인다."""
    spec = extract_screen_spec(_doc(["페이지명", "SUPPORT", "페이지", "사용자"]), _Fixed())
    assert spec.url_path == ""
    assert any("--screen-url" in w for w in spec.warnings)


def test_경로_없는_화면은_케이스를_만들지_않는다():
    from prova.s2_case_generator.generator import generate_cases

    spec = extract_screen_spec(_doc(["페이지명", "SUPPORT", "페이지", "사용자"]), _Fixed())
    assert generate_cases(spec) == []


def test_사용자가_준_경로를_화면_이름이나_ID_로_붙인다():
    from prova.models import SpecDocument
    from prova.nodes import apply_screen_urls

    a = extract_screen_spec(_doc(["페이지명", "SUPPORT", "페이지", "사용자"]), _Fixed())
    b = extract_screen_spec(_doc(["페이지명", "메인화면", "페이지", "사용자"]), _Fixed())
    doc = SpecDocument(source="x", screens=[a, b])
    apply_screen_urls(doc, {"support": "/board/support/view.do",
                            "메인 화면": "/index.do", "없는화면": "/x"})
    assert a.url_path == "/board/support/view.do"
    assert b.url_path == "/index.do"  # 띄어쓰기는 무시한다
    assert not any("--screen-url" in w for w in a.warnings)  # 붙였으면 경고를 거둔다
    assert any("없는화면" in w for w in doc.warnings)


class _FailsOn:
    """특정 화면 이름이 프롬프트에 있으면 잘림을 낸다."""

    def __init__(self, bad: str):
        self.bad = bad

    def complete_json(self, *, system, user, schema, max_tokens=2048, temperature=0.0):
        from prova.llm.base import OutputTruncated

        if self.bad in user:
            raise OutputTruncated(f"모델 출력이 max_tokens({max_tokens})에서 잘렸습니다.")
        return {"screen_id": "x", "screen_name": "x", "url_path": "/x",
                "elements": [], "success_condition": "", "warnings": []}


def _multi_pdf(tmp_path, names):
    """페이지명 머리말만 있는 여러 쪽 PDF."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
    pdf = tmp_path / "multi.pdf"
    c = canvas.Canvas(str(pdf), pagesize=(500, 400))
    for name in names:
        c.setFont("HYSMyeongJo-Medium", 10)
        for x0, y0, x1, y1 in [(50, 350, 450, 350), (50, 320, 450, 320), (50, 290, 450, 290),
                               (50, 350, 50, 290), (150, 350, 150, 290), (450, 350, 450, 290)]:
            c.line(x0, y0, x1, y1)
        c.drawString(60, 330, "프로젝트")
        c.drawString(160, 330, "작성자 김")
        c.drawString(60, 300, "페이지명")
        c.drawString(160, 300, f"{name} 페이지 사용자")
        c.drawString(60, 200, f"{name} 본문")
        c.showPage()
    c.save()
    return pdf


def test_한_화면이_실패해도_나머지_화면은_남는다(tmp_path):
    """실물 21화면 중 한 화면(예시 사례가 다섯 번 반복되는 목록)이 모델 반복 루프로
    6144 토큰에서도 잘렸고, 그 예외가 문서 전체를 죽였다(2026-11-06)."""
    from prova.s1_spec_extractor.extractor import extract_document

    pdf = _multi_pdf(tmp_path, ["SUPPORT", "NEWS", "ABOUT"])
    doc = extract_document(pdf, _FailsOn("NEWS 본문"))
    assert [s.screen_name for s in doc.screens] == ["SUPPORT", "NEWS", "ABOUT"]
    works = doc.screens[1]
    assert works.elements == [] and works.url_path == ""
    assert any("추출에 실패" in w for w in works.warnings)
    assert any("NEWS" in w and "추출에 실패" in w for w in doc.warnings)


def test_모든_화면이_실패하면_예외를_올린다(tmp_path):
    import pytest
    from prova.llm.base import LLMError
    from prova.s1_spec_extractor.extractor import extract_document

    pdf = _multi_pdf(tmp_path, ["SUPPORT", "NEWS"])
    with pytest.raises(LLMError):
        extract_document(pdf, _FailsOn("본문"))


class _RootPath(_Fixed):
    def complete_json(self, **kw):
        out = super().complete_json(**kw)
        out["url_path"] = "/"
        return out


def test_구분_기호_슬래시를_경로로_보지_않는다():
    """'ABOUT / SHOP' 의 '/' 가 있다고 모델이 지은 루트 경로 '/' 를 기획서 값으로 받았다."""
    doc = _doc(["페이지명", "메인화면", "페이지", "사용자"])
    doc.pages[0].body_text = "헤더 - ABOUT / SHOP / NEWS 메뉴 구성"
    assert extract_screen_spec(doc, _RootPath()).url_path == ""


def test_경로라고_적힌_루트는_받는다():
    doc = _doc(["페이지명", "메인화면", "페이지", "사용자"])
    doc.pages[0].body_text = "화면 경로: /"
    assert extract_screen_spec(doc, _RootPath()).url_path == "/"


class _Captures(_Fixed):
    def __init__(self):
        self.users = []

    def complete_json(self, *, system, user, schema, max_tokens=2048, temperature=0.0):
        self.users.append(user)
        return super().complete_json(system=system, user=user, schema=schema)


def test_화면_그림_기획서에만_그림용_안내를_붙인다():
    """요소 표 없는 화면 그림에서 모델이 설명 제목('○○ 영역')만 뽑았다 (2026-11-06 실물)."""
    from prova.s1_spec_extractor.extractor import FIGURE_SPEC_HINT

    llm = _Captures()
    extract_screen_spec(_doc(["페이지명", "SUPPORT", "페이지", "사용자"]), llm)
    assert FIGURE_SPEC_HINT in llm.users[0]

    llm = _Captures()
    extract_screen_spec(ParsedDocument(source="x", pages=[ParsedPage(page_no=1, tables=[
        ParsedTable(rows=[["항목", "내용"], ["화면 ID", "login"]]),
        ParsedTable(rows=[["페이지명", "로그인", "페이지", "사용자"]]),
    ])]), llm)
    assert FIGURE_SPEC_HINT not in llm.users[0]  # 화면 ID 표가 있는 기획서는 예전 프롬프트


class _Regions(_Fixed):
    def complete_json(self, **kw):
        out = super().complete_json(**kw)
        out["elements"] = [
            {"element_id": "logo", "type": "link", "label": "회사 로고 영역"},
            {"element_id": "about", "type": "link", "label": "ABOUT"},
        ]
        return out


def test_화면_그림의_설명_제목은_요소에서_뺀다():
    spec = extract_screen_spec(_doc(["페이지명", "SUPPORT", "페이지", "사용자"]), _Regions())
    assert [e.label for e in spec.elements] == ["ABOUT"]
    assert any("설명 제목" in w for w in spec.warnings)


class _Banner(_Fixed):
    def complete_json(self, **kw):
        out = super().complete_json(**kw)
        out["elements"] = [
            {"element_id": "c", "type": "link", "label": "빠르고, 정확한 서비스"},
            {"element_id": "d", "type": "link", "label": "새로운 내일을 함께 합니다."},
            {"element_id": "m", "type": "link", "label": "Contact Us"},
        ]
        return out


def test_그림_속_문장은_링크가_아니라_표시_글자로_둔다():
    spec = extract_screen_spec(_doc(["페이지명", "SUPPORT", "페이지", "사용자"]), _Banner())
    assert [(e.label, e.type) for e in spec.elements] == [
        ("빠르고, 정확한 서비스", "text"), ("새로운 내일을 함께 합니다.", "text"),
        ("Contact Us", "link")]
