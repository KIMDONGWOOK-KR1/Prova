"""기획서가 적은 요소 유형대로 구현됐는가 — 실제 브라우저 페이지로 확인한다.

## 왜 이 검사가 필요한가

기획서의 '유형' 열은 지금까지 **우리 쪽에서만** 쓰였다. 체크박스면 check() 를 부르고
선택이면 select_option() 을 부르는 식으로 액션을 고르는 데만 썼다. 구현이 그 유형을
지켰는지는 아무도 확인하지 않았다.

그래서 이런 불일치가 통과했다.

    기획서   '로그인하러 가기'  유형: 링크
    구현     <button onclick="location.href=...">로그인하러 가기</button>

S3 는 role 로 못 찾아도 텍스트 일치로 찾아내 눌러 준다. 눌러지니까 아무 말 없이
지나가고, 기획서가 유형을 적어 둔 것이 검증에 아무 영향을 주지 않는다.

링크와 버튼의 차이는 사용자에게 실제로 드러난다 — 링크는 새 탭으로 열 수 있고 주소를
복사할 수 있고 스크린리더가 '링크' 로 읽는다. 기획-구현 불일치다.

## 왜 버튼·링크만 대조하는가

role 매핑을 신뢰할 수 있는 유형만 본다. 입력란은 넣을 수 없다 —
input[type=password] 는 ARIA 에서 textbox role 을 갖지 않으므로, 대조하면 비밀번호
칸마다 '유형 불일치' 가 떠서 전부 오탐이 된다. 확인할 수 없는 것을 확인한다고
주장하지 않는다.
"""

from __future__ import annotations

import pytest

from prova.models import UIElement
from prova.s3_grounder.dom_locator import GroundingError, SpecTypeMismatch, ground


@pytest.fixture(scope="module")
def page():
    """빈 페이지 하나. 테스트마다 set_content 로 마크업을 바꿔 쓴다."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        yield pg
        browser.close()


def link(label: str = "로그인하러 가기") -> UIElement:
    return UIElement(element_id="to_login", type="link", label=label)


def button(label: str = "가입하기") -> UIElement:
    return UIElement(element_id="submit", type="button", label=label)


class TestLinkDeclaredAsLink:
    def test_링크로_구현되면_통과한다(self, page):
        page.set_content('<a href="/login">로그인하러 가기</a>')
        location = ground(page, "로그인하러 가기", link())
        assert location.strategy == "role"

    def test_버튼으로_구현되면_불일치다(self, page):
        """텍스트 일치로 찾히므로 막지 않으면 아무 말 없이 눌러 준다."""
        page.set_content('<button onclick="void 0">로그인하러 가기</button>')
        with pytest.raises(SpecTypeMismatch) as exc:
            ground(page, "로그인하러 가기", link())
        assert "링크" in str(exc.value), "기획서가 쓴 낱말로 말해야 한다"
        assert "링크" in exc.value.reason

    def test_그냥_텍스트면_불일치다(self, page):
        """div 에 글자만 있는 경우. 클릭은 되지만 링크가 아니다."""
        page.set_content("<div>로그인하러 가기</div>")
        with pytest.raises(SpecTypeMismatch):
            ground(page, "로그인하러 가기", link())

    def test_없으면_유형_불일치가_아니라_탐지_실패다(self, page):
        """둘은 개발자가 할 일이 다르다 — 하나는 요소를 만들어야 하고, 하나는
        요소의 종류를 바꿔야 한다. 같은 실패로 묶으면 엉뚱한 곳을 고친다."""
        page.set_content("<div>다른 글자</div>")
        with pytest.raises(GroundingError):
            ground(page, "로그인하러 가기", link())


class TestButtonDeclaredAsButton:
    def test_버튼으로_구현되면_통과한다(self, page):
        page.set_content("<button>가입하기</button>")
        assert ground(page, "가입하기", button()).strategy == "role"

    def test_링크로_구현되면_불일치다(self, page):
        """반대 방향도 잡는다. 폼을 제출해야 하는 자리에 링크를 두면 키보드
        동작과 기본 동작이 달라진다."""
        page.set_content('<a href="#">가입하기</a>')
        with pytest.raises(SpecTypeMismatch):
            ground(page, "가입하기", button())

    def test_실제_SUT의_버튼은_통과한다(self, page, sut_base):
        """오탐 확인. 지금 SUT 의 버튼은 모두 <button> 이므로 이 검사가 기존
        케이스를 깨뜨리지 않아야 한다."""
        for path, label in (("/good/login", "로그인"),
                            ("/good/signup", "가입하기"),
                            ("/good/search", "검색")):
            page.goto(f"{sut_base}{path}")
            ground(page, label, button(label))


class TestUncheckedTypes:
    """대조하지 않는 유형은 유형 때문에 실패하지 않아야 한다."""

    def test_비밀번호_입력란은_대조하지_않는다(self, page):
        """input[type=password] 는 textbox role 을 갖지 않는다. 대조하면 비밀번호
        칸마다 불일치가 떠서 전부 오탐이 된다."""
        page.set_content(
            '<label for="pw">비밀번호</label><input id="pw" type="password">')
        element = UIElement(element_id="pw", type="input", label="비밀번호")
        assert ground(page, "비밀번호", element) is not None

    def test_힌트가_없으면_대조하지_않는다(self, page):
        """기획서가 유형을 적지 않았으면 대조할 근거가 없다. 없는 것을 요구하면
        기획서를 억지로 고치게 된다."""
        page.set_content("<div>아무 글자</div>")
        assert ground(page, "아무 글자", None) is not None
