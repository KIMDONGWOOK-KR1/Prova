"""probe_s1_robustness 의 판정 — 훼손이 일부러 지운 값은 줄어든 것이 정답이다.

'열 누락' 은 안내 문구 열을 지운 문서다. 안내 0 은 잃은 것이 아니라 정답이고,
안내가 나오면 없는 열에서 지어낸 것이다. 예전 기준은 둘을 거꾸로 판정했다 —
정답을 '조용한 실패' 로, 지어낸 것을 '영향 없음' 으로.
"""

from __future__ import annotations

import pytest

from conftest import load_script


@pytest.fixture(scope="module")
def probe():
    return load_script("scripts/probe_s1_robustness.py")


BASE = {"요소수": 3, "규칙수": 4, "placeholder수": 2, "경고": []}


def _r(**kw):
    return {**BASE, **kw}


def test_removed_value_at_zero_is_no_effect(probe):
    r = _r(placeholder수=0)
    assert probe._verdict(BASE, r, {"placeholder수"}) == "영향 없음"


def test_removed_value_present_is_invention(probe):
    r = _r(placeholder수=2)
    assert probe._verdict(BASE, r, {"placeholder수"}) == probe.INVENTED


def test_invention_is_reported_even_with_warnings(probe):
    # 경고가 있다고 지어낸 문구가 덜 위험해지지 않는다 — 경고는 다른 것에 관한 것일 수 있다
    r = _r(placeholder수=1, 경고=["무언가"])
    assert probe._verdict(BASE, r, {"placeholder수"}) == probe.INVENTED


def test_other_values_still_compared_to_baseline(probe):
    r = _r(placeholder수=0, 규칙수=3)
    assert probe._verdict(BASE, r, {"placeholder수"}) == probe.SILENT


def test_loss_without_warning_is_silent(probe):
    assert probe._verdict(BASE, _r(요소수=2), set()) == probe.SILENT


def test_loss_with_warning_is_noisy(probe):
    assert probe._verdict(BASE, _r(요소수=2, 경고=["w"]), set()) == "시끄러운 실패 (경고 있음)"


def test_unchanged_is_no_effect(probe):
    assert probe._verdict(BASE, _r(), set()) == "영향 없음"


def test_drop_column_declares_placeholder_removed(probe):
    removed = {name: rm for name, _fn, _note, rm in probe.DEGRADATIONS}
    assert removed["열 누락"] == {"placeholder수"}
    assert removed["원본"] == set()
