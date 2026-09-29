"""후보가 둘 이상이면 2차 경로로 넘기지 않는다.

1차 경로가 '같은 이름의 후보 2개' 로 실패했다면 화면 이미지도 둘 중 하나를 고를
근거가 없다. 2026-09-29 외부 화면 측정에서 모델은 그런 화면(parabank 회원가입 폼 +
로그인 패널의 Username)에서 **다른 쪽**을 가리켰고, 정체 대조는 이름이 같아 막지
못한다. '후보가 정확히 하나일 때만 답한다' 는 원칙이 2차 경로에서만 뚫려 있었다.

후보가 0개(라벨이 끊긴 아이콘 버튼)면 여전히 넘긴다 — 2차 경로의 존재 이유다.
"""

from __future__ import annotations

import pytest

from prova.models import UIElement
from prova.s3_grounder.dom_locator import Attempt, GroundingError, ambiguous_count
from prova.s4_executor.playwright_driver import ExecutionContext, _locate
from prova.vlm.base import Located

BUTTON = UIElement(element_id="b", type="button", label="검색")
FIELD = UIElement(element_id="f", type="input", label="Username")


class SpyVLM:
    """불렸는지만 센다. 부르면 버튼 하나의 자리를 돌려준다."""

    name = "spy"
    model = "spy"

    def __init__(self):
        self.calls = 0

    def locate(self, image_png, target, hint=""):
        self.calls += 1
        return Located(bbox=(0.0, 0.0, 0.1, 0.05), confidence=0.95)


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser.new_page(viewport={"width": 1280, "height": 800})
        browser.close()


def _ctx(page, tmp_path, vlm):
    return ExecutionContext(page=page, base_url="http://x", specs=[], run_dir=tmp_path,
                            case_id="c", vlm=vlm, max_heal=2)


def test_같은_이름_후보가_둘이면_부르지_않는다(page, tmp_path):
    page.set_content('<button aria-label="검색">1</button><button aria-label="검색">2</button>')
    vlm = SpyVLM()
    ctx = _ctx(page, tmp_path, vlm)
    with pytest.raises(GroundingError) as info:
        _locate(ctx, "검색", BUTTON)
    assert vlm.calls == 0
    assert ctx.heal_count == 0
    assert "여러 개" in info.value.reason


def test_건너뛴_사유가_남는다(page, tmp_path):
    page.set_content('<button aria-label="검색">1</button><button aria-label="검색">2</button>')
    with pytest.raises(GroundingError) as info:
        _locate(_ctx(page, tmp_path, SpyVLM()), "검색", BUTTON)
    skipped = [a for a in info.value.attempts if a.strategy == "vlm"]
    assert skipped and "후보 2개" in skipped[0].detail


def test_라벨로_이어진_입력란_둘도_부르지_않는다(page, tmp_path):
    """parabank 모양 — 같은 라벨의 입력란이 한 화면에 둘."""
    page.set_content(
        '<label for="a">Username</label><input id="a">'
        '<label for="b">Username</label><input id="b">')
    vlm = SpyVLM()
    with pytest.raises(GroundingError):
        _locate(_ctx(page, tmp_path, vlm), "Username", FIELD)
    assert vlm.calls == 0


def test_후보가_없으면_여전히_부른다(page, tmp_path):
    """아이콘만 있는 버튼 — 2차 경로의 존재 이유."""
    page.set_content('<button>🔍</button>')
    vlm = SpyVLM()
    location = _locate(_ctx(page, tmp_path, vlm), "검색", BUTTON)
    assert vlm.calls == 1
    assert location.method == "vlm"


def test_글자_일치가_여럿인_것은_후보가_아니다():
    """text 전략은 요소가 아니라 글자를 잡는다 — 제목과 버튼 글자가 같으면 2개가 된다.
    그것을 '후보 둘' 로 치면 라벨이 끊긴 화면에서 보정이 죽는다."""
    attempts = [Attempt("role", 0), Attempt("text", 3)]
    assert ambiguous_count(attempts) == 0


def test_요소_전략의_최대_개수를_돌려준다():
    attempts = [Attempt("label", 2), Attempt("placeholder", 0), Attempt("role", 3)]
    assert ambiguous_count(attempts) == 3
