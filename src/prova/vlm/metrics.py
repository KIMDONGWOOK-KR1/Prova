"""탐지 좌표를 채점하는 계산 — 이 파일만 헤드라인 숫자를 만든다.

## 왜 따로 두는가

명세서 §9 는 '탐지 성공률 ≥90%(IoU 기준)' 을 요구한다. 그 숫자를 만드는 계산이
측정 스크립트 안에 흩어져 있으면, 스크립트를 하나 더 쓸 때 계산이 한 벌 더 생긴다.
2026-08-17 점검에서 배운 것이 정확히 그 모양이었다 — 같은 판단이 두 곳에 있으면
한쪽만 고쳐지고, 두 숫자가 달라진 사실이 조용히 숨는다.

그래서 채점은 여기 한 번만 쓰고, 테스트로 고정한다. 보고서에 나갈 숫자를 만드는
계산에 테스트가 없으면 그 숫자를 믿을 근거가 없다.

## 좌표 규약

모든 함수는 `(x1, y1, x2, y2)` 0~1 상대값을 받는다. `Located.bbox` 와 같은 규약이고,
뷰포트 크기·devicePixelRatio 에 영향받지 않는다(vlm/base.py 참고).

## 두 기준을 함께 재는 이유

**IoU 와 적중은 서로 다른 것을 잰다.**

    IoU     상자가 얼마나 겹치는가       — 크기까지 맞혀야 높다
    적중    중심이 실제 요소 안에 드는가 — 위치만 맞으면 된다

2차 경로가 하는 일은 **좌표를 눌러 조작하는 것**이므로 실제 성패는 적중이다. 입력란을
'라벨까지 포함한 영역' 으로 잡으면 IoU 는 0.4 로 떨어지는데 클릭은 정확히 된다.

그런데 명세서가 요구한 지표는 IoU 다. 하나로 합치면 어느 쪽이든 사실을 지운다 —
IoU 만 쓰면 실제로 되는 것을 실패로 세고, 적중만 쓰면 명세서 지표에 답하지 않는다.
그래서 둘 다 재고 보고서에 나란히 적는다. 어느 기준으로 90% 를 말하는지는 읽는
사람이 알아야 한다.
"""

from __future__ import annotations

import math

Box = tuple[float, float, float, float]

#: 명세서 §9 의 'IoU 기준' 을 셀 때 쓰는 문턱값. 탐지 과제의 관례값이다.
DEFAULT_IOU_THRESHOLD = 0.5


def area(box: Box) -> float:
    """상자의 면적. 뒤집힌 상자(x2 < x1)는 0 이다 — 음수 면적을 만들지 않는다."""
    x1, y1, x2, y2 = box
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def iou(found: Box, truth: Box) -> float:
    """두 상자의 IoU. 겹치지 않거나 어느 쪽이 넓이 0 이면 0.0.

    넓이 0 을 0.0 으로 돌려주는 이유: 분모가 0 이 되는 경우를 예외로 만들면 채점
    루프가 한 항목 때문에 멈춘다. 모델이 뒤집힌 좌표를 내는 일은 실제로 있고
    (`Located.is_sane()` 가 그래서 있다), 그건 '못 맞혔다' 로 세는 것이 맞다.
    """
    ix1, iy1 = max(found[0], truth[0]), max(found[1], truth[1])
    ix2, iy2 = min(found[2], truth[2]), min(found[3], truth[3])
    inter = area((ix1, iy1, ix2, iy2))
    union = area(found) + area(truth) - inter
    if union <= 0.0:
        return 0.0
    return inter / union


def center(box: Box) -> tuple[float, float]:
    x1, y1, x2, y2 = box
    return (x1 + x2) / 2, (y1 + y2) / 2


def center_hit(found: Box, truth: Box) -> bool:
    """모델이 낸 상자의 중심이 실제 요소 안에 드는가 — 클릭이 성공하는 조건이다.

    경계에 정확히 걸리는 경우를 포함(<=)한다. 브라우저도 경계 픽셀을 요소로 본다.
    """
    cx, cy = center(found)
    return truth[0] <= cx <= truth[2] and truth[1] <= cy <= truth[3]


def center_error(found: Box, truth: Box) -> float:
    """중심이 실제 중심에서 얼마나 벗어났는가 — 요소 크기 대비 비율.

    절대 픽셀을 쓰지 않는 이유: 같은 20px 오차가 작은 아이콘 버튼에서는 치명적이고
    넓은 입력란에서는 아무 문제가 아니다. 크기로 나누면 두 요소를 같은 표에 놓고
    비교할 수 있다.

    **0.5 이하면 적중과 같은 뜻이다** (중심이 요소 안에 든다). 두 값을 서로 독립된
    증거처럼 나란히 쓰면 안 된다 — 이 값은 적중의 '얼마나' 를 말할 뿐이다.

    넓이 0 인 실제 상자에는 inf 를 돌려준다. 나눌 수 없는 것을 0 으로 두면
    '완벽하게 맞혔다' 로 보인다.
    """
    tw, th = truth[2] - truth[0], truth[3] - truth[1]
    if tw <= 0 or th <= 0:
        return math.inf
    cx, cy = center(found)
    tcx, tcy = center(truth)
    return max(abs(cx - tcx) / tw, abs(cy - tcy) / th)
