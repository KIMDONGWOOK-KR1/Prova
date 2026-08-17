"""테스트·오프라인 개발용 mock VLM.

## 이 mock 이 증명하는 것과 증명하지 않는 것

증명하는 것: **배관.** 스크린샷을 찍고, 위치를 받고, 그 좌표를 눌러서, 케이스가 끝까지
진행되고 판정이 나오는가. 이 경로가 도는지는 GPU 없이 확인할 수 있어야 한다.

증명하지 않는 것: **VLM 의 정확도.** 이 mock 은 정답을 알고 있다 — 미리 등록해 둔
좌표를 돌려주거나, 페이지에서 CSS selector 로 요소를 찾아 그 위치를 준다. 실제 모델이
그 위치를 맞히는지는 전혀 다른 문제이고, 실물 모델로 따로 측정해야 한다.

**이 구분을 흐리면 안 된다.** mock 으로 초록불을 보고 '2차가 동작한다' 고 말하면,
정작 실물 모델이 요소를 못 찾을 때 그 사실이 어디서도 드러나지 않는다. 리포트에 어떤
백엔드로 실행했는지 남기는 이유가 그것이다(llm/mock_backend.py 와 같은 판단).

## 왜 CSS selector 로 찾는 방식을 두는가

좌표를 손으로 적어 두면 SUT 의 CSS 를 조금 고칠 때마다 그 숫자가 낡는다. 낡은 좌표는
'보정이 엉뚱한 곳을 눌렀다' 로 나타나서, 배관이 깨진 것인지 좌표가 낡은 것인지
구분하는 데 시간이 든다. selector 로 실측하면 그 문제가 없다.

이건 '완벽한 VLM' 을 시뮬레이션하는 것이다. 그 전제를 문서와 리포트에 명시한다.
"""

from __future__ import annotations

from prova.vlm.base import Located, VLMError


class MockVLM:
    """미리 등록한 좌표, 또는 페이지에서 실측한 좌표를 돌려준다."""

    name = "mock-vlm"

    def __init__(self, page=None) -> None:
        # page 를 주면 selector 로 실제 위치를 잰다 ('완벽한 VLM' 시뮬레이션).
        self._page = page
        # target -> (bbox, confidence). 등록해 둔 것이 먼저 쓰인다.
        self._answers: dict[str, tuple[tuple[float, float, float, float], float]] = {}
        # target -> CSS selector. page 가 있을 때 실측에 쓴다.
        self._selectors: dict[str, str] = {}
        self.calls: list[dict] = []

    def register(self, target: str, bbox: tuple[float, float, float, float],
                 confidence: float = 1.0) -> None:
        """이 라벨에는 이 좌표를 돌려준다. 실패·저신뢰 상황을 시험할 때 쓴다."""
        self._answers[target] = (bbox, confidence)

    def register_selector(self, target: str, selector: str) -> None:
        """이 라벨의 위치를 이 CSS selector 로 잰다."""
        self._selectors[target] = selector

    def locate(self, *, image_png: bytes, target: str, hint: str = "") -> Located:
        self.calls.append({"target": target, "hint": hint, "bytes": len(image_png)})

        if target in self._answers:
            bbox, confidence = self._answers[target]
            return Located(bbox=bbox, confidence=confidence)

        selector = self._selectors.get(target)
        if selector is None or self._page is None:
            raise VLMError(
                f"mock VLM 에 '{target}' 의 답이 등록되지 않았습니다. "
                f"등록된 것: {sorted(set(self._answers) | set(self._selectors))}"
            )
        return self._measure(selector)

    def _measure(self, selector: str) -> Located:
        """페이지에서 요소의 실제 위치를 재 0~1 상대값으로 바꾼다.

        뷰포트 크기로 나눈다. 스크린샷 픽셀이 아니라 뷰포트 기준이어야
        s3_grounder 가 곱해서 되돌릴 때 맞는다.
        """
        box = self._page.locator(selector).first.bounding_box()
        if box is None:
            raise VLMError(f"selector {selector!r} 로 위치를 잴 수 없습니다")
        size = self._page.viewport_size
        if not size:
            raise VLMError("뷰포트 크기를 알 수 없습니다")
        w, h = size["width"], size["height"]
        return Located(bbox=(
            box["x"] / w, box["y"] / h,
            (box["x"] + box["width"]) / w, (box["y"] + box["height"]) / h,
        ))
