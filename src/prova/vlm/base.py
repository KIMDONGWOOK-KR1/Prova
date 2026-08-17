"""VLM 백엔드 추상화 — 화면 이미지에서 요소의 위치를 찾는 능력.

## 왜 이 단계가 필요한가

S3 는 접근성 속성으로 요소를 찾는다(라벨 -> placeholder -> role -> 텍스트). 그게
구현 세부와 가장 느슨하게 결합돼 있어서다. 그런데 실물 화면이 라벨을 `<label for>` 로
연결하지 않거나 목록에 접근성 이름을 안 주면 그 경로가 전부 막힌다.

건수 검증에서 이미 그 경계를 만났다 — 목록에 `aria-label` 이 없으면 세지 못하고,
'결과가 0건이거나 접근성 이름이 없다' 로만 보고할 수 있었다. 사람은 그 화면을 보고
어디를 눌러야 할지 안다. 그 능력을 도구에 주는 것이 이 단계다.

## 인터페이스를 locate 하나로 둔 이유

LLM 쪽과 같은 판단이다(llm/base.py 참고). 백엔드는 '이미지와 찾을 것을 주면 위치를
돌려준다' 는 저수준 능력 하나만 제공하고, 프롬프트와 좌표 해석은 s3_grounder 가
소유한다. 그래야 프롬프트가 한 곳에만 있고 백엔드는 통신 방식만 다르다.

## 좌표를 0~1 상대값으로 받는 이유

모델마다 좌표 규약이 다르다. Qwen2.5-VL 은 리사이즈된 이미지 기준 절대 픽셀을 내고,
어떤 모델은 0~1000 정규화를 쓴다. 그 차이를 호출자가 알아야 하면 백엔드를 바꿀 때
S3 도 함께 고쳐야 한다.

그래서 **백엔드가 자기 규약을 0~1 상대값으로 바꿔서 돌려준다.** S3 는 뷰포트 크기를
곱해 실제 좌표를 만든다. 스크린샷 크기와 뷰포트 크기가 다른 경우(devicePixelRatio)도
상대값이면 영향을 받지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class VLMError(RuntimeError):
    """VLM 호출 실패. 재시도로 해결되지 않는 상태."""


@dataclass
class Located:
    """VLM 이 찾은 위치. 좌표는 0~1 상대값이다.

    ## confidence 를 함께 받는 이유

    VLM 은 못 찾았을 때도 그럴듯한 좌표를 낸다. 그 좌표를 그대로 누르면 엉뚱한 곳을
    눌러 놓고 케이스를 진행하게 되고, 그 FAIL 이 구현 결함인지 잘못 누른 것인지
    구분할 수 없다 — S3 가 '정확히 1개만 확정한다' 를 계약으로 삼은 것과 같은 이유다.

    그래서 임계값 아래면 보정을 포기한다. 못 찾은 것을 못 찾았다고 말하는 편이,
    아무 데나 누르고 통과시키는 것보다 낫다.
    """

    # [x1, y1, x2, y2] — 0~1 상대값
    bbox: tuple[float, float, float, float]
    confidence: float = 1.0

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return (x1 + x2) / 2, (y1 + y2) / 2

    def is_sane(self) -> bool:
        """좌표가 화면 안에 있고 크기가 0 이 아닌가.

        모델이 좌표를 뒤집어 내거나(x2 < x1) 범위를 벗어난 값을 내는 일이 실제로
        있다. 그대로 쓰면 Playwright 가 화면 밖을 눌러 조작 오류가 나고, 원인이
        '요소를 못 찾았다' 가 아니라 '클릭 실패' 로 기록되어 흐려진다.
        """
        x1, y1, x2, y2 = self.bbox
        if not all(0.0 <= v <= 1.0 for v in self.bbox):
            return False
        return x2 > x1 and y2 > y1


@runtime_checkable
class VLMClient(Protocol):
    """화면 이미지에서 자연어로 지목한 요소의 위치를 찾는 능력."""

    name: str

    def locate(self, *, image_png: bytes, target: str, hint: str = "") -> Located:
        """이미지에서 target 에 해당하는 요소의 위치를 돌려준다.

        Args:
            image_png: 화면 스크린샷 (PNG 바이트)
            target: 찾을 것 — 기획서의 자연어 라벨 ("이메일", "로그인")
            hint: 요소 종류 등 좁히는 데 쓸 말 ("입력란", "버튼")

        Raises:
            VLMError: 통신 실패, 좌표를 얻지 못한 응답 등
        """
        ...
