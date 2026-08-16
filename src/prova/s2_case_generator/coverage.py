"""기획서에 적혀 있는데 아무 케이스도 확인하지 않는 것을 찾는다.

## 왜 이 모듈이 필요한가

이 도구가 낼 수 있는 가장 위험한 리포트는 FAIL 이 아니다. **"31/31 통과" 인데 실은
기획서의 절반을 확인하지 않은 리포트**다. 읽는 사람은 다 확인됐다고 믿고 넘어간다.

확인하지 않은 것과 확인해서 통과한 것은 다르다. 그런데 리포트에서는 똑같이 보인다 —
전자는 아예 나타나지 않으므로.

이 모듈이 실제로 찾아낸 것이 그 위험을 증명한다. **가장 처음 만든 로그인 화면**에
이런 행이 있었다.

    | 등록되지 않은 계정 | "이메일 또는 비밀번호가 올바르지 않습니다." 노출 |

이 문구를 확인하는 케이스가 하나도 없었다. 규칙을 다 지켰지만 등록되지 않은 계정이라는
상황은 '값이 규칙을 어겼는가' 로 만들 수 없기 때문이다(검색 화면의 scenarios 와 같은
성질이다). 그런데 리포트는 여러 차례 '로그인 7/7 통과' 라고 보고했다.

## 무엇을 대조하는가

기획서가 적어 둔 **문구**를 센다. 문구는 기획-구현 대조의 단위이고, 기획서에서
결정적으로 뽑을 수 있다.

    요소별 error_message      / 화면 공통 required_message
    실패 조건 표의 인용 문구   / 성공 조건의 인용 문구
    예시 시나리오의 기대 문구

그중 어떤 케이스의 기대값에도 들어가지 않는 문구를 '확인하지 않았다' 로 보고한다.

## 왜 경고가 아니라 별도 항목인가

이건 기획서의 결함도(spec_defects), 구현의 결함도(FAIL) 아니다. **검증 범위**에 대한
사실이다. 경고 목록에 섞으면 '기획서를 고치라' 는 말로 읽히는데, 고칠 곳은 기획서일
수도 있고(그 상황을 만들 입력을 제시해야 한다) 이 도구일 수도 있다.

## 못 찾는 것

문구가 없는 규칙은 이 방식으로 보이지 않는다. "정렬 순서는 최신순" 처럼 노출 문구가
없는 요구는 문구 대조로 셀 수 없다. 그건 이 모듈의 한계이고, 넓히려면 기획서가 확인
가능한 형태(예시 입력과 기대 결과)로 적어야 한다 — Scenario 가 그 자리다.
"""

from __future__ import annotations

import re

from prova.models import ScreenSpec, TestCase
from prova.text_utils import loosen

# 표·문장 안의 인용된 문구. pdf_parser 와 같은 인용부호 집합을 본다.
_QUOTED = re.compile(r"[\"'“”‘’]([^\"'“”‘’]{2,80})[\"'“”‘’]")


def declared_messages(spec: ScreenSpec) -> dict[str, str]:
    """기획서가 적어 둔 문구 -> 그 문구의 출처.

    키는 정규형(공백 무시)이다. PDF 에서 뽑은 문구와 케이스 기대값의 공백 배치가
    다를 수 있으므로, 같은 문구를 다르다고 세지 않게 맞춰 둔다.
    """
    found: dict[str, str] = {}

    def add(text: str | None, source: str) -> None:
        if text and text.strip():
            found.setdefault(loosen(text), source)

    for element in spec.elements:
        add(element.error_message, f"'{element.label}' 의 에러 메시지")
    add(spec.required_message, "필수 입력 공통 문구")

    for i, condition in enumerate(spec.failure_conditions, 1):
        for quoted in _QUOTED.findall(condition):
            add(quoted, f"실패 조건 {i}번")
    for quoted in _QUOTED.findall(spec.success_condition or ""):
        add(quoted, "성공 조건")
    for i, scenario in enumerate(spec.scenarios, 1):
        add(scenario.expect_text, f"예시 시나리오 {i}번")

    return found


def checked_messages(cases: list[TestCase]) -> set[str]:
    """케이스들이 실제로 대조하는 문구 (정규형).

    expected.value 만 본다. 그게 '화면에서 찾을 문구' 를 담는 필드이고, 판정이
    그 값으로 이루어진다. 케이스 제목이나 스텝에 문구가 들어 있어도 판정에 쓰이지
    않으면 확인한 것이 아니다.
    """
    return {loosen(c.expected.value) for c in cases if c.expected.value}


def coverage_gaps(spec: ScreenSpec, cases: list[TestCase]) -> list[str]:
    """기획서에 적혀 있는데 어떤 케이스도 확인하지 않는 문구를 문장으로.

    사유를 함께 적는다. '확인하지 않았다' 만 알려 주면 읽는 사람이 무엇을 해야
    하는지 알 수 없다. 대개 기획서가 **그 상황을 만들 입력을 제시하지 않은** 경우다.
    """
    declared = declared_messages(spec)
    checked = checked_messages(cases)

    gaps: list[str] = []
    for text, source in declared.items():
        if text in checked:
            continue
        original = next(
            (t for t in _originals(spec) if loosen(t) == text), text
        )
        gaps.append(
            f"{source}에 적힌 \"{original}\" 을 확인하는 케이스가 없습니다. "
            f"그 문구가 뜨는 상황을 값의 규칙만으로 만들 수 없다면, 기획서가 예시 "
            f"입력과 기대 문구를 짝으로 제시해야 검증할 수 있습니다."
        )
    return gaps


def _originals(spec: ScreenSpec) -> list[str]:
    """정규화 전 원문 문구들. 경고에 원문을 그대로 보여주기 위해 모은다."""
    out = [e.error_message for e in spec.elements if e.error_message]
    if spec.required_message:
        out.append(spec.required_message)
    for condition in spec.failure_conditions:
        out.extend(_QUOTED.findall(condition))
    out.extend(_QUOTED.findall(spec.success_condition or ""))
    out.extend(s.expect_text for s in spec.scenarios)
    return [t for t in out if t]
