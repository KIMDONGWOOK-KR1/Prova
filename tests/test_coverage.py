"""확인하지 않은 것을 찾아내는가 — 커버리지 검출.

## 이 검출기가 실제로 찾아낸 것

가장 처음 만든 로그인 화면의 실패 조건 4번이었다.

    | 등록되지 않은 계정 | "이메일 또는 비밀번호가 올바르지 않습니다." 노출 |

그 문구를 확인하는 케이스가 하나도 없었다. 규칙을 다 지켰지만 등록되지 않은 계정이라는
상황은 '값이 규칙을 어겼는가' 로 만들 수 없기 때문이다. 그런데 리포트는 여러 차례
'로그인 7/7 통과' 라고 보고했다.

**확인하지 않은 것과 확인해서 통과한 것은 다르다.** 전자는 리포트에 아예 나타나지
않으므로 더 위험하다.

기획서에 예시 동작(시나리오)을 추가해 그 구멍을 닫았고, 이 테스트가 다시 벌어지지
않게 못 박는다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prova.models import ScreenSpec, UIElement
from prova.s2_case_generator.coverage import (
    checked_messages,
    coverage_gaps,
    declared_messages,
)
from prova.s2_case_generator.generator import generate_cases

SPEC_DIR = Path("fixtures/specs")


def golden(stem: str) -> ScreenSpec:
    return ScreenSpec.model_validate(
        json.loads((SPEC_DIR / f"{stem}_spec.golden.json").read_text(encoding="utf-8"))
    )


class TestDeclaredMessages:
    """기획서가 적어 둔 문구를 빠짐없이 모아야 한다. 못 모으면 구멍을 못 본다."""

    def test_요소_에러문구와_공통문구를_모은다(self):
        spec = golden("login")
        found = declared_messages(spec)
        assert any("올바른이메일형식" in k for k in found)
        assert any("필수입력항목입니다" in k for k in found)

    def test_실패_조건의_인용_문구를_모은다(self):
        spec = golden("login")
        sources = set(declared_messages(spec).values())
        assert any("실패 조건" in s for s in sources)

    def test_성공_조건의_인용_문구를_모은다(self):
        spec = golden("login")
        assert any("환영합니다" in k for k in declared_messages(spec))

    def test_공백_배치가_달라도_같은_문구로_센다(self):
        """PDF 에서 뽑은 문구는 줄바꿈 위치가 다르다. 정규화하지 않으면 같은 문구를
        둘로 세어 없는 구멍을 보고한다."""
        spec = ScreenSpec(
            screen_id="s", screen_name="화면", url_path="/s",
            elements=[UIElement(element_id="f", type="input", label="필드",
                                error_message="문구는\n한 줄이 아니다")],
            failure_conditions=['위반 시 "문구는 한 줄이 아니다" 노출'],
        )
        assert len(declared_messages(spec)) == 1


class TestCheckedMessages:
    def test_케이스의_기대값만_센다(self):
        """제목이나 스텝에 문구가 있어도 판정에 쓰이지 않으면 확인한 것이 아니다."""
        spec = golden("login")
        checked = checked_messages(generate_cases(spec))
        assert any("올바른이메일형식" in c for c in checked)


class TestCoverageGaps:
    def test_지금_세_화면에는_구멍이_없다(self):
        """회귀 방지. 기획서에 문구를 추가하고 검증 경로를 만들지 않으면 여기서
        걸린다 — 그게 이 테스트의 목적이다."""
        for stem in ("login", "signup", "search"):
            spec = golden(stem)
            gaps = coverage_gaps(spec, generate_cases(spec))
            assert gaps == [], f"{stem}: {gaps}"

    def test_로그인의_미등록_계정_문구는_시나리오가_덮는다(self):
        """이 검출기가 처음 찾아낸 구멍이다. 규칙 위반으로는 만들 수 없는 상황이라
        기획서가 예시 입력을 제시해야 검증된다."""
        spec = golden("login")
        assert any("nobody@test.com" in str(s.given.values()) for s in spec.scenarios)
        assert coverage_gaps(spec, generate_cases(spec)) == []

    def test_시나리오를_빼면_다시_보고한다(self):
        spec = golden("login")
        spec.scenarios = []
        gaps = coverage_gaps(spec, generate_cases(spec))
        assert len(gaps) == 1
        assert "이메일 또는 비밀번호가 올바르지 않습니다." in gaps[0]
        assert "실패 조건 4번" in gaps[0]

    def test_무엇을_해야_하는지_사유에_적는다(self):
        """'확인하지 않았다' 만 알려 주면 읽는 사람이 할 일을 모른다."""
        spec = golden("login")
        spec.scenarios = []
        assert "예시 입력" in coverage_gaps(spec, generate_cases(spec))[0]

    def test_문구가_없는_요구는_세지_않는다(self):
        """"정렬은 최신순" 처럼 노출 문구가 없는 요구는 문구 대조로 셀 수 없다.
        이 방식의 한계이고, 없는 것을 있는 척하지 않는다."""
        spec = ScreenSpec(
            screen_id="s", screen_name="화면", url_path="/s",
            elements=[UIElement(element_id="b", type="button", label="확인")],
            failure_conditions=["정렬 순서는 최신순이어야 한다"],
        )
        assert coverage_gaps(spec, generate_cases(spec)) == []
