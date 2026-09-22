"""모델이 낸 경고는 출처를 달고, 기획서 본문을 베낀 것은 뺀다.

## 왜 (2026-09-22 멘토링 시연 준비에서 실측)

실물 7B 로 상품등록 기획서를 돌리면 리포트와 터미널에 이 줄이 떴다.

    ! 설계 문서 경고: [product] 이 화면은 판매자 계정으로 로그인한 상태에서 동작한다.

기획서 §5 '전제' 의 본문 한 문장이다. 프롬프트가 "판단할 수 없는 내용은 warnings
에 기록하세요" 라고 하자 모델이 그 칸에 본문을 옮겼다. 판정에는 영향이 없지만
읽는 사람은 **도구가 기획서에서 문제를 찾았다** 고 읽는다 — 코드가 낸 구조
경고(표 누락, 백필)와 같은 칸에 같은 모양으로 섞여 있어서다.

두 가지를 한다.
- 기획서 본문에 그대로 있는 문장은 경고가 아니다(정보가 0이다) — 뺀다.
- 남는 모델 경고에는 "모델 메모:" 를 붙인다. 모델이 판단을 못 했다고 말하는
  통로는 살리되, 코드가 확인한 사실과 구분되게 한다.
"""

from __future__ import annotations

from prova.models import ScreenSpec
from prova.s1_spec_extractor.extractor import _label_model_warnings

DOC_TEXT = """## 5. 전제

이 화면은 판매자 계정으로
로그인한 상태에서 동작한다.
"""


def spec_warned(*warnings: str) -> ScreenSpec:
    return ScreenSpec(screen_id="product", screen_name="상품 등록", url_path="/product",
                      warnings=list(warnings))


def test_본문을_베낀_문장은_경고가_아니다():
    """PDF 줄바꿈이 문장 중간에 걸려 있어도 같은 문장으로 본다."""
    spec = spec_warned("이 화면은 판매자 계정으로 로그인한 상태에서 동작한다.")
    _label_model_warnings(spec, DOC_TEXT)
    assert spec.warnings == []


def test_모델이_판단을_못_한_것은_출처를_달고_남긴다():
    spec = spec_warned("가격의 최대값이 기획서에 없습니다")
    _label_model_warnings(spec, DOC_TEXT)
    assert spec.warnings == ["모델 메모: 가격의 최대값이 기획서에 없습니다"]


def test_빈_경고는_버린다():
    spec = spec_warned("", "   ")
    _label_model_warnings(spec, DOC_TEXT)
    assert spec.warnings == []
