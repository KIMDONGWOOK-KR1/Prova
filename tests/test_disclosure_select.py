"""버튼 + 숨은 라디오 묶음 선택, 정의 목록 라벨, 안내 문구 이름 — 2026-11-06 실물 사이트.

문의 폼의 분류 선택이 이렇게 생겼다:

    <dl><dt><span>분류<i>필수</i></span></dt>
        <dd><div class="pick"><button>문의 분류를 선택해주세요.</button>
            <div style="display:none"><ul><li><input type=radio id=a><label for=a>A</label>…

`<select>` 도 role=combobox 도 아니고, 라벨은 `<dt>` 글자라 입력과 이어져 있지 않다.
기획서는 이 칸을 '문의 분류' 로 적었다(안내 문구에서 온 이름). 도구는 칸을 찾지 못해
문의 폼 케이스 12개가 전부 이 스텝에서 멈췄다.

## 지키는 것

- 앞의 전략으로 찾히는 요소는 그대로다 — 새 경로는 다 못 찾을 때만 본다.
- 여전히 정확히 하나일 때만 조작한다.
- 안내 문구는 '○○을/를 선택·입력' 꼴의 문구 전체와 맞아야 한다.
- 항목 확인(read_options)은 숨은 라디오의 라벨을 그대로 읽는다 — 느슨하게 맞추는 것은
  다른 칸을 검사하려고 채우는 값을 고를 때뿐이다.
"""

from __future__ import annotations

import pytest

from prova.models import TestStep, UIElement
from prova.s3_grounder.dom_locator import (
    GroundingError,
    _pick_option,
    check_findable,
    ground,
    prompt_variant,
    read_options,
    resolve_locator,
)
from prova.s4_executor.playwright_driver import ExecutionContext, execute_step


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        yield pg
        browser.close()


def _form(open_on_click: int = 1) -> str:
    """open_on_click 번째 클릭에서야 펼쳐진다 — 부드러운 스크롤로 첫 클릭이 빗나가는 사이트."""
    return f"""
<dl>
  <dt><span class="label">분류<i class="required">필수</i></span></dt>
  <dd><div class="pick">
    <button type="button" id="btn"><span>문의 분류를 선택해주세요.</span></button>
    <div class="opts" style="display:none"><ul>
      <li><input type="radio" name="cat" id="a" value="Alpha Box"><label for="a">Alpha Box</label></li>
      <li><input type="radio" name="cat" id="b" value="Beta"><label for="b">Beta</label></li>
      <li><input type="radio" name="cat" id="e" value="ETC"><label for="e">기타문의</label></li>
    </ul></div>
  </div></dd>
  <dt><span class="label">성명<i class="required">필수</i></span></dt>
  <dd><input type="text" id="name"></dd>
</dl>
<script>
  (() => {{  // set_content 는 같은 JS 전역을 쓴다 — 최상위 let 은 두 번째 문서에서 깨진다
    let clicks = 0;
    document.getElementById('btn').addEventListener('click', () => {{
      clicks += 1;
      if (clicks < {open_on_click}) return;
      const o = document.querySelector('.opts');
      o.style.display = o.style.display === 'none' ? 'block' : 'none';
    }});
  }})();
</script>"""


def _ctx(page, tmp_path):
    return ExecutionContext(page=page, base_url="http://x", specs=[], run_dir=tmp_path,
                            case_id="c", screenshot_every_step=False)


class TestPromptVariant:
    @pytest.mark.parametrize("name", ["문의 분류를 선택해주세요.", "문의분류를 선택하세요",
                                      "이메일을 입력하세요."])
    def test_안내_문구_꼴을_맞춘다(self, name):
        target = "이메일" if name.startswith("이메일") else "문의 분류"
        assert prompt_variant(target).search(name)

    @pytest.mark.parametrize("name", ["분류를 선택해주세요.", "문의 분류를 바꾸면 목록이 바뀝니다",
                                      "다른 문의 분류를 선택해주세요."])
    def test_다른_문장은_맞추지_않는다(self, name):
        assert not prompt_variant("문의 분류").search(name)


class TestPickOption:
    OPTS = ["Alpha Box", "Beta", "기타문의"]

    def test_정확히_같은_것이_먼저다(self):
        assert _pick_option(self.OPTS, "Beta") == 1

    def test_띄어쓰기만_다른_항목(self):
        assert _pick_option(self.OPTS, "기타 문의") == 2

    def test_두_표기를_함께_적은_기획서_값(self):
        assert _pick_option(self.OPTS, "Alpha Box/알파") == 0
        assert _pick_option(self.OPTS, "Alpha Box (알파)") == 0

    def test_없거나_여럿이면_고르지_않는다(self):
        assert _pick_option(self.OPTS, "Gamma") is None
        assert _pick_option(["A x", "A y"], "A/B") is None


class TestGround:
    def test_안내_문구로_선택_버튼을_찾는다(self, page):
        page.set_content(_form())
        hint = UIElement(element_id="cat", type="select", label="문의 분류")
        loc = ground(page, "문의 분류", hint)
        assert loc.strategy == "prompt_control"
        assert resolve_locator(page, loc, hint).get_attribute("id") == "btn"

    def test_정의_목록_라벨로_찾는다(self, page):
        page.set_content(_form())
        hint = UIElement(element_id="cat", type="select", label="분류")
        loc = ground(page, "분류", hint)
        assert loc.strategy == "dl_label"
        assert resolve_locator(page, loc, hint).get_attribute("id") == "btn"
        hint = UIElement(element_id="name", type="input", label="성명")
        assert resolve_locator(page, ground(page, "성명", hint), hint).get_attribute("id") == "name"

    def test_label_for_가_있으면_그것이_먼저다(self, page):
        page.set_content('<dl><dt>성명</dt><dd><input id="dd"></dd></dl>'
                         '<label for="lab">성명</label><input id="lab">')
        hint = UIElement(element_id="n", type="input", label="성명")
        assert resolve_locator(page, ground(page, "성명", hint), hint).get_attribute("id") == "lab"

    def test_정의_목록_라벨이_여럿이면_고르지_않는다(self, page):
        page.set_content('<dl><dt>성명 필수</dt><dd><input></dd><dt>성명 *</dt><dd><input></dd></dl>')
        with pytest.raises(GroundingError):
            ground(page, "성명", UIElement(element_id="n", type="input", label="성명"))

    def test_안내_문구가_둘이면_고르지_않는다(self, page):
        page.set_content('<button>분류를 선택해주세요.</button><button>분류를 선택하세요</button>')
        with pytest.raises(GroundingError):
            ground(page, "분류", UIElement(element_id="c", type="select", label="분류"))

    def test_라벨_확인(self, page):
        page.set_content(_form())
        elements = [UIElement(element_id="c1", type="select", label="문의 분류"),
                    UIElement(element_id="c2", type="select", label="분류")]
        got = check_findable(page, elements, ["문의 분류", "분류", "없는 칸"])
        assert got["문의 분류"] == ""
        assert got["분류"] == ""  # <dt>→<dd> 는 HTML 이 정한 짝이다 — 표 칸 라벨과 다르다
        assert got["없는 칸"] != ""


class TestReadOptions:
    def test_숨은_라디오의_라벨을_그대로_읽는다(self, page):
        page.set_content(_form())
        hint = UIElement(element_id="cat", type="select", label="문의 분류")
        assert read_options(page, "문의 분류", hint) == ["Alpha Box", "Beta", "기타문의"]


class TestSelectStep:
    def test_펼치고_항목을_고른다(self, page, tmp_path):
        page.set_content(_form())
        step = TestStep(seq=1, action="select", target="문의 분류", value="Beta")
        result = execute_step(_ctx(page, tmp_path), step)
        assert result.status == "ok", result.error_detail
        assert page.locator("#b").is_checked()

    def test_첫_클릭이_빗나가면_한_번_더_누른다(self, page, tmp_path):
        page.set_content(_form(open_on_click=2))
        step = TestStep(seq=1, action="select", target="문의 분류", value="기타 문의")
        result = execute_step(_ctx(page, tmp_path), step)
        assert result.status == "ok", result.error_detail
        assert page.locator("#e").is_checked()

    def test_빈_값이면_고르지_않는다(self, page, tmp_path):
        page.set_content(_form())
        step = TestStep(seq=1, action="select", target="문의 분류", value="")
        result = execute_step(_ctx(page, tmp_path), step)
        assert result.status == "ok", result.error_detail
        assert page.locator("input[name=cat]:checked").count() == 0

    def test_없는_항목이면_화면_항목과_함께_실패한다(self, page, tmp_path):
        page.set_content(_form())
        step = TestStep(seq=1, action="select", target="문의 분류", value="Gamma")
        result = execute_step(_ctx(page, tmp_path), step)
        assert result.status == "error"
        assert "Gamma" in (result.error_detail or "") and "Beta" in (result.error_detail or "")


_FILE_DL = """
<dl>
  <dt><span>첨부파일</span></dt>
  <dd><p><input type="text" id="shown" readonly placeholder="10mb 이하">
         <input type="file" id="f" style="display:none"></p>
      <label for="f">업로드</label></dd>
  <dt><label for="nm">성명<i>필수</i></label></dt>
  <dd><input id="nm"></dd>
</dl>"""


class TestDefinitionListOrder:
    def test_연결된_라벨이_필수_표시만_다르면_그_라벨이다(self, page):
        page.set_content(_FILE_DL)
        hint = UIElement(element_id="nm", type="input", label="성명")
        loc = ground(page, "성명", hint)
        assert loc.strategy == "label"
        assert resolve_locator(page, loc, hint).get_attribute("id") == "nm"

    def test_파일_칸은_숨은_파일_입력을_가리킨다(self, page):
        page.set_content(_FILE_DL)
        hint = UIElement(element_id="f", type="input", label="첨부파일")
        loc = ground(page, "첨부파일", hint)
        assert loc.strategy == "dl_label"  # 글자(<dt>)가 아니다
        assert resolve_locator(page, loc, hint).get_attribute("id") == "f"

    def test_파일_칸은_빈_값이면_건드리지_않고_글자면_도구_한계로_알린다(self, page, tmp_path):
        page.set_content(_FILE_DL)
        from prova.models import ScreenSpec
        spec = ScreenSpec(screen_id="s", screen_name="s", url_path="/s", elements=[
            UIElement(element_id="f", type="input", label="첨부파일")], success_condition="")
        ctx = ExecutionContext(page=page, base_url="http://x", specs=[spec], run_dir=tmp_path,
                               case_id="c", screenshot_every_step=False)
        ok = execute_step(ctx, TestStep(seq=1, action="fill", target="첨부파일", value=""))
        assert ok.status == "ok", ok.error_detail
        bad = execute_step(ctx, TestStep(seq=2, action="fill", target="첨부파일", value="abc"))
        assert bad.status == "error" and bad.error_code == "input_error"
        assert "파일 첨부 칸" in (bad.error_detail or "")


class TestFileFieldCases:
    def test_파일_칸에는_글자_규칙_위반을_만들지_않고_값을_비운다(self):
        from prova.s2_case_generator.rule_expander import (
            is_file_field, valid_value_for, violations_for_element)
        el = UIElement(element_id="f", type="input", label="첨부파일",
                       constraints={"max_length": 300, "format": "file"})
        assert is_file_field(el)
        assert valid_value_for(el) == ""
        assert violations_for_element(el) == []
        assert not is_file_field(UIElement(element_id="n", type="input", label="성명",
                                           constraints={"max_length": 30}))


def test_비워_둘_파일_칸은_스텝을_만들지_않는다():
    from prova.models import ScreenSpec
    from prova.s2_case_generator.generator import generate_cases

    spec = ScreenSpec(screen_id="s", screen_name="s", url_path="/s", success_condition="", elements=[
        UIElement(element_id="n", type="input", label="성명", required=True),
        UIElement(element_id="f", type="input", label="파일 첨부", constraints={"format": "file"}),
        UIElement(element_id="b", type="button", label="보내기"),
    ])
    for case in generate_cases(spec):
        assert all(step.target != "파일 첨부" for step in case.steps), case.case_id


def test_안내_문구는_필수_표시가_붙은_라벨에서도_읽는다(page):
    from prova.s3_grounder.dom_locator import read_placeholders

    page.set_content('<label for="n">성명<i>필수</i></label><input id="n" placeholder="이름 입력">'
                     '<dl><dt>메모</dt><dd><textarea placeholder="메모 입력"></textarea></dd></dl>')
    assert read_placeholders(page, ["성명", "메모", "없음"]) == {"성명": "이름 입력",
                                                              "메모": "메모 입력"}


def test_입력란_없는_화면은_링크도_라벨_확인에_넣는다():
    from prova.models import ScreenSpec
    from prova.s2_case_generator.generator import _label_case

    nav = ScreenSpec(screen_id="home", screen_name="홈", url_path="/", success_condition="",
                     elements=[UIElement(element_id="a", type="link", label="소개"),
                               UIElement(element_id="b", type="link", label="문의"),
                               UIElement(element_id="t", type="button", label="맨 위로")])
    (case,) = _label_case(nav)
    assert {"소개", "문의"} <= set(case.expected.labels)

    form = ScreenSpec(screen_id="f", screen_name="가입", url_path="/f", success_condition="",
                      elements=[UIElement(element_id="n", type="input", label="이름"),
                                UIElement(element_id="go", type="link", label="로그인하러 가기"),
                                UIElement(element_id="s", type="button", label="가입")])
    (case,) = _label_case(form)
    assert "로그인하러 가기" not in case.expected.labels  # 폼 화면은 예전 그대로


def test_아이콘_묘사_이름은_라벨_확인에서_뺀다():
    from prova.models import ScreenSpec
    from prova.s2_case_generator.generator import _label_case

    nav = ScreenSpec(screen_id="home", screen_name="홈", url_path="/", success_condition="",
                     elements=[UIElement(element_id="m", type="button", label="햄버거 메뉴"),
                               UIElement(element_id="a", type="link", label="소개")])
    (case,) = _label_case(nav)
    assert case.expected.labels == ["소개"]
