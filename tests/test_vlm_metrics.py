"""탐지 채점 계산을 고정한다.

이 계산이 중간보고에 나가는 '탐지 성공률' 을 만든다. 눈으로 읽어서 맞아 보이는 것과
맞는 것은 다르므로, 손으로 계산할 수 있는 값들로 못을 박는다.
"""

from __future__ import annotations

import math

import pytest

from prova.vlm.metrics import (
    DEFAULT_IOU_THRESHOLD,
    area,
    center,
    center_error,
    center_hit,
    iou,
)

# 왼쪽 위 1/4 을 차지하는 상자. 손계산이 쉬운 값으로 골랐다.
UNIT = (0.0, 0.0, 0.5, 0.5)


class TestIoU:
    def test_같은_상자는_1이다(self):
        assert iou(UNIT, UNIT) == 1.0

    def test_겹치지_않으면_0이다(self):
        assert iou((0.6, 0.6, 0.9, 0.9), UNIT) == 0.0

    def test_변만_닿으면_0이다(self):
        # 겹치는 면적이 없다. 경계가 닿는 것을 겹침으로 세면 IoU 가 부풀려진다.
        assert iou((0.5, 0.0, 1.0, 0.5), UNIT) == 0.0

    def test_절반_겹침을_손계산과_맞춘다(self):
        # 교집합 0.25*0.5=0.125, 합집합 0.25+0.25-0.125=0.375 -> 1/3
        assert iou((0.25, 0.0, 0.75, 0.5), UNIT) == 0.125 / 0.375

    def test_한쪽이_다른쪽을_품으면_면적비다(self):
        # 큰 상자 1.0, 작은 상자 0.25 -> 0.25
        assert iou((0.0, 0.0, 1.0, 1.0), UNIT) == 0.25

    def test_뒤집힌_상자는_0이다(self):
        # 모델이 x2 < x1 을 내는 일이 실제로 있다. 예외를 던지지 않고 0 으로 센다.
        assert iou((0.5, 0.5, 0.1, 0.1), UNIT) == 0.0

    def test_넓이가_0이면_0이다(self):
        # 분모가 0 이 되는 경로. 여기서 멈추면 채점 한 바퀴가 통째로 죽는다.
        assert iou((0.2, 0.2, 0.2, 0.2), (0.2, 0.2, 0.2, 0.2)) == 0.0

    def test_문턱값은_탐지_관례값이다(self):
        assert DEFAULT_IOU_THRESHOLD == 0.5


class TestArea:
    def test_뒤집힌_상자의_면적은_0이다(self):
        # 음수 면적을 만들면 합집합이 줄어들어 IoU 가 1 을 넘을 수 있다.
        assert area((0.8, 0.8, 0.2, 0.2)) == 0.0


class TestCenter:
    def test_중심을_계산한다(self):
        assert center(UNIT) == (0.25, 0.25)

    def test_중심이_안에_들면_적중이다(self):
        assert center_hit((0.2, 0.2, 0.3, 0.3), UNIT) is True

    def test_중심이_밖이면_적중이_아니다(self):
        assert center_hit((0.6, 0.6, 0.8, 0.8), UNIT) is False

    def test_경계에_걸리면_적중이다(self):
        # 실제 요소의 오른쪽 변에 중심이 정확히 놓인 경우. 브라우저도 이 픽셀을
        # 요소로 보므로 클릭이 된다.
        assert center_hit((0.5, 0.25, 0.5, 0.25), UNIT) is True

    def test_두_지표가_갈리는_실제_모양을_고정한다(self):
        # 납작한 입력란을 모델이 라벨까지 포함해 위아래로 넓게 잡은 경우.
        # **적중인데 IoU 는 문턱값 아래다** — 클릭은 되는데 명세서 기준으로는
        # 실패로 세어진다. 두 지표를 함께 재는 이유가 정확히 이 경우이므로,
        # 그 갈림이 실제로 일어난다는 사실을 테스트로 고정해 둔다.
        field = (0.1, 0.30, 0.5, 0.35)
        found = (0.1, 0.25, 0.5, 0.36)
        assert center_hit(found, field) is True
        assert iou(found, field) == pytest.approx(0.02 / 0.044)
        assert iou(found, field) < DEFAULT_IOU_THRESHOLD


class TestCenterError:
    def test_정확히_맞히면_0이다(self):
        assert center_error(UNIT, UNIT) == 0.0

    def test_요소_크기로_나눈다(self):
        # x 중심이 0.25 -> 0.375 로 0.125 이동, 폭 0.5 -> 0.25
        assert center_error((0.125, 0.0, 0.625, 0.5), UNIT) == 0.25

    def test_0_5가_적중의_경계다(self):
        # 이 값이 적중 여부와 같은 것을 말한다는 사실을 고정한다.
        edge = (0.5, 0.25, 0.5, 0.25)
        assert center_error(edge, UNIT) == 0.5
        assert center_hit(edge, UNIT) is True

    def test_0_5를_넘으면_적중이_아니다(self):
        out = (0.51, 0.25, 0.51, 0.25)
        assert center_error(out, UNIT) > 0.5
        assert center_hit(out, UNIT) is False

    def test_넓이가_0인_실제상자는_inf다(self):
        # 0 으로 두면 '완벽하게 맞혔다' 로 보인다. 나눌 수 없다는 사실을 남긴다.
        assert math.isinf(center_error(UNIT, (0.2, 0.2, 0.2, 0.2)))
