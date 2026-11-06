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
            {"element_id": "biz", "type": "link", "label": "운영영역"},
        ]
        return out


def test_화면_그림의_설명_제목은_요소에서_뺀다():
    spec = extract_screen_spec(_doc(["페이지명", "SUPPORT", "페이지", "사용자"]), _Regions())
    # 붙여 쓴 '운영영역' 은 메뉴 이름일 수 있다 — 띄어 쓴 '○○ 영역' 만 설명 제목이다
    assert [e.label for e in spec.elements] == ["ABOUT", "운영영역"]
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


def _figure_doc():
    """화면 그림이 있는 화면기획서 — 그림에는 영어 선택지와 동의 문장이 보인다."""
    from prova.s1_spec_extractor.pdf_parser import figure_heading, panel_heading

    lines = [figure_heading(), "Alpha Box", "Beta Pole", "기타 문의",
             "*분류 | 분류를 선택해주세요.", "(필수) 개인정보 수집·이용에 동의합니다.", "등록",
             panel_heading(), "- Alpha Box/상자, 베타 폴, 기타문의 구분", "개인정보 수집·이용 동의"]
    doc = _doc(["페이지명", "SUPPORT", "페이지", "사용자"])
    doc.pages[0].body_lines = [(t, float(i)) for i, t in enumerate(lines)]
    doc.pages[0].body_text = "\n".join(lines)
    return doc


class _PanelValues(_Fixed):
    def complete_json(self, **kw):
        out = super().complete_json(**kw)
        out["elements"] = [
            {"element_id": "cat", "type": "select", "label": "분류",
             "options": ["Alpha Box/상자", "베타 폴", "기타문의"]},
            {"element_id": "agree", "type": "checkbox", "label": "개인정보 수집·이용 동의"},
            {"element_id": "ok", "type": "button", "label": "등록"},
        ]
        return out


def test_그림에_없는_선택지는_설명에서_옮긴_값이라_뺀다():
    spec = extract_screen_spec(_figure_doc(), _PanelValues())
    cat = next(e for e in spec.elements if e.element_id == "cat")
    assert cat.options == ["기타문의"]       # 띄어쓰기만 다른 것은 그림에 있다고 본다
    assert any("선택 항목" in w for w in spec.warnings)


def test_그림에_없는_이름은_라벨_확인에서_뺀다():
    spec = extract_screen_spec(_figure_doc(), _PanelValues())
    by_id = {e.element_id: e for e in spec.elements}
    assert by_id["agree"].figure_unseen is True     # 요소는 남는다 — 조작은 한다
    assert by_id["ok"].figure_unseen is False
    assert by_id["cat"].figure_unseen is False      # '*분류' 처럼 필수 표시가 붙어도 있다


def test_그림이_없는_화면은_건드리지_않는다():
    spec = extract_screen_spec(_doc(["페이지명", "SUPPORT", "페이지", "사용자"]), _PanelValues())
    cat = next(e for e in spec.elements if e.element_id == "cat")
    assert cat.options == ["Alpha Box/상자", "베타 폴", "기타문의"]
    assert not any(e.figure_unseen for e in spec.elements)


def test_그림에_없는_이름은_라벨_확인_케이스에_넣지_않는다():
    from prova.s2_case_generator.generator import generate_cases

    spec = extract_screen_spec(_figure_doc(), _PanelValues())
    spec.url_path = "/support"
    labels = [c for c in generate_cases(spec) if c.expected.type == "labels_findable"]
    assert len(labels) == 1
    assert "개인정보 수집·이용 동의" not in labels[0].expected.labels
    assert "분류" in labels[0].expected.labels and "등록" in labels[0].expected.labels


def _menu_doc(extra_after=()):
    """전체 메뉴 그림 — 세 열이 줄마다 섞여 읽힌다. 첫 열 이름 일부를 모델이 빠뜨린다."""
    from prova.s1_spec_extractor.pdf_parser import figure_heading, panel_heading

    lines = [figure_heading(), "1", "회사 | 제품 | 사례 | 문의", "2",
             "회사 소개 | Alpha Box | Alpha Box", "오시는 길",
             "소식 | Beta Pole | Beta Pole", "채용 | Gamma | Gamma",
             "새로운 내일을, 함께 | 기타", *extra_after,
             panel_heading(), "닫기 버튼 영역", "- 각 세부 메뉴 클릭 시 해당 페이지 이동"]
    doc = _doc(["페이지명", "전체메뉴", "페이지", "사용자"])
    doc.pages[0].tables[0].rows.pop()   # 입력 칸 행 없음 — 내비게이션 화면
    doc.pages[0].body_lines = [(t, float(i)) for i, t in enumerate(lines)]
    doc.pages[0].body_text = "\n".join(lines)
    return doc


class _MenuMissing(_Fixed):
    def __init__(self, elements=None):
        self.elements = elements

    def complete_json(self, **kw):
        out = super().complete_json(**kw)
        out["elements"] = self.elements or [
            {"element_id": f"m{i}", "type": "link", "label": name}
            for i, name in enumerate(["회사", "제품", "사례", "문의", "회사 소개",
                                      "Alpha Box", "Beta Pole", "Gamma", "기타"])]
        return out


def test_메뉴_화면에서_모델이_빠뜨린_그림_속_메뉴_이름을_링크로_채운다():
    spec = extract_screen_spec(_menu_doc(), _MenuMissing())
    added = [e.label for e in spec.elements][9:]
    assert added == ["오시는 길", "소식", "채용"]
    assert all(e.type == "link" for e in spec.elements)
    assert any("빠뜨린" in w for w in spec.warnings)


def test_메뉴가_아닌_칸과_같은_줄이거나_숫자가_든_이름은_채우지_않는다():
    # 제품 상세 그림: 번호 표시 옆 제목, 해상도 값 — 메뉴 줄 범위 안에 있어도 메뉴가 아니다
    doc = _menu_doc()
    lines = [t for t, _ in doc.pages[0].body_lines]
    at = lines.index("채용 | Gamma | Gamma")
    lines[at:at] = ["4 | 제품 사양", "Alpha Box | 1920 x 1080"]
    doc.pages[0].body_lines = [(t, float(i)) for i, t in enumerate(lines)]
    labels = [e.label for e in extract_screen_spec(doc, _MenuMissing()).elements]
    assert "제품 사양" not in labels and "1920 x 1080" not in labels
    assert "채용" in labels


def test_메뉴_줄_범위_밖의_글자와_문장은_채우지_않는다():
    spec = extract_screen_spec(_menu_doc(extra_after=("자료 필요",)), _MenuMissing())
    labels = [e.label for e in spec.elements]
    assert "자료 필요" not in labels                # 마지막 메뉴 줄보다 아래
    assert "1" not in labels and "2" not in labels    # 번호 표시
    assert "새로운 내일을, 함께" not in labels         # 문장


def test_입력란이_있는_화면이나_링크가_적은_화면은_채우지_않는다():
    form = [{"element_id": "q", "type": "input", "label": "회사"},
            *[{"element_id": f"m{i}", "type": "link", "label": n}
              for i, n in enumerate(["제품", "사례", "문의", "Alpha Box", "Gamma"])]]
    few = [{"element_id": f"m{i}", "type": "link", "label": n}
           for i, n in enumerate(["회사", "기타"])]
    for elements in (form, few):
        spec = extract_screen_spec(_menu_doc(), _MenuMissing(elements))
        assert len(spec.elements) == len(elements)
