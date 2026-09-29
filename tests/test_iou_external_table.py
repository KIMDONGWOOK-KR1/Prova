"""외부 사이트 시험지(build_iou_external)의 정답표가 시험지로서 성립하는지.

화면을 열지 않고 표만 본다 — 외부 사이트는 바뀌므로 실제 selector 확인은
시험지를 굳힐 때(capture) 한다. 여기서 지키는 것은 표 자체의 모양이다.
"""

from __future__ import annotations

import pytest

from conftest import load_script
from prova.s3_grounder.dom_locator import VLM_HINTS


@pytest.fixture(scope="module")
def ext():
    return load_script("scripts/build_iou_external.py")


def test_화면마다_없는_요소를_묻는다(ext):
    """없는 것을 묻지 않으면 '있다고 지어내는가' 를 잴 수 없다 — 그게 2차 경로의 진짜 위험이다."""
    for s in ext.STATES:
        assert any(not t.present for t in s.targets), s.state_id


def test_화면마다_있는_요소를_묻는다(ext):
    for s in ext.STATES:
        assert any(t.present for t in s.targets), s.state_id


def test_요소_종류가_파이프라인_힌트_표에_있다(ext):
    """다른 말로 물으면 측정 조건이 실행 조건과 달라진다."""
    for s in ext.STATES:
        for t in s.targets:
            assert t.kind in VLM_HINTS, (s.state_id, t.name, t.kind)


def test_화면_이름이_겹치지_않는다(ext):
    ids = [s.state_id for s in ext.STATES]
    assert len(ids) == len(set(ids))


def test_우리_SUT_가_아니다(ext):
    """이 시험지의 뜻은 '우리가 안 만든 화면' 이다."""
    for s in ext.STATES:
        assert s.url.startswith("https://"), s.state_id
        assert "localhost" not in s.url


def test_보이는_화면_안_판정(ext):
    vp = {"width": 1280, "height": 800}
    assert ext.inside_viewport({"x": 10, "y": 10, "width": 100, "height": 30}, vp)
    assert not ext.inside_viewport({"x": 10, "y": 790, "width": 100, "height": 30}, vp)
    assert not ext.inside_viewport({"x": -5, "y": 10, "width": 100, "height": 30}, vp)


def test_목록은_보이는_부분으로_자른다(ext):
    vp = {"width": 1280, "height": 800}
    got = ext.clip_to_viewport({"x": 100, "y": 600, "width": 500, "height": 900}, vp)
    assert got == {"x": 100, "y": 600, "width": 500, "height": 200}
    assert ext.clip_to_viewport({"x": 100, "y": 900, "width": 50, "height": 50}, vp) is None
