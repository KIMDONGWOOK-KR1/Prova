"""S2 전반부 — 입력 검증 규칙을 위반 케이스로 전개한다. LLM 을 쓰지 않는다.

## 왜 LLM 이 아니라 순수 함수인가

명세서 §10-2 도 "규칙 -> 위반 매핑은 거의 결정적 패턴" 이라 판단했다.
'대문자 1자 이상' 이라는 규칙에서 '대문자가 없는 값' 을 만드는 일에는 추론이
필요하지 않다. 코드로 짜면 이득이 명확하다.

- 결정적이다: 같은 기획서에서 언제나 같은 케이스가 나온다. 회귀 비교가 가능하다.
- 공짜다: API 비용도, GPU 시간도 들지 않는다.
- 검증된다: 생성한 값이 정말 그 규칙만 위반하는지 단위 테스트로 확인할 수 있다.
  LLM 출력에는 이런 보증을 걸 수 없다.

LLM 은 판단이 필요한 곳에만 쓴다 (S1 의 자연어 -> 스키마 매핑, S2 의 케이스 제목).

## 핵심 계약: 하나의 케이스는 하나의 규칙만 위반한다

명세서의 예시 케이스 signup-pw-no-upper-002 는 대문자와 특수문자를 동시에
빠뜨린 "abcd1234" 를 쓴다. 그 케이스가 FAIL 이면 개발자는 "대문자 검증이 없나,
특수문자 검증이 없나, 둘 다인가" 를 알 수 없다.

그래서 위반값을 만들 때 **대상 규칙만 깨고 나머지 규칙은 모두 만족시킨다.**

    require_uppercase 위반 -> "abcd123!"   (소문자·숫자·특수문자·길이 모두 충족)
    require_special   위반 -> "Abcd1234"   (특수문자만 없음)
    min_length        위반 -> "Abc1!"      (짧지만 문자 종류 요건은 충족)

이렇게 하면 리포트에서 규칙과 실패가 1:1 로 연결되고, 개발자는 어느 검증
로직을 추가해야 하는지 바로 안다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from prova.models import UIElement

SPECIAL_POOL = "!@#$%^&*"
UPPER_POOL = "ABCDEFGH"
LOWER_POOL = "abcdefgh"
DIGIT_POOL = "12345678"

# 사람이 읽는 규칙 이름. 리포트와 케이스 제목에 쓴다.
RULE_LABELS = {
    "required": "필수 입력",
    "format": "형식",
    "min_length": "최소 길이",
    "max_length": "최대 길이",
    "require_uppercase": "대문자 포함",
    "require_lowercase": "소문자 포함",
    "require_digit": "숫자 포함",
    "require_special": "특수문자 포함",
    "pattern": "정규식 패턴",
}


@dataclass(frozen=True)
class Violation:
    """규칙 하나를 위반하는 입력값 하나."""

    rule: str          # constraints 키 (또는 "required")
    value: str         # 그 규칙만 위반하는 입력값
    description: str   # 리포트용 설명 — 왜 이 값을 넣었는지

    @property
    def rule_label(self) -> str:
        return RULE_LABELS.get(self.rule, self.rule)


# ---------------------------------------------------------------------------
# 규칙 판정 — 생성한 값이 옳은지 검사하는 기준
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _count_upper(s: str) -> int:
    return sum(1 for c in s if c.isupper())


def _count_lower(s: str) -> int:
    return sum(1 for c in s if c.islower())


def _count_digit(s: str) -> int:
    return sum(1 for c in s if c.isdigit())


def _count_special(s: str) -> int:
    return sum(1 for c in s if not c.isalnum() and not c.isspace())


def satisfies(value: str, constraints: dict) -> bool:
    """value 가 constraints 의 모든 규칙을 만족하는가.

    위반값 생성이 의도대로 됐는지 검사하는 기준이다. 이 함수와 SUT 의 검증
    로직이 같은 규칙을 구현하지만, 서로 참조하지 않는다 — 테스트 대상과 판정
    기준이 같은 코드를 공유하면 둘이 함께 틀렸을 때 알 수 없기 때문이다.
    """
    for key, expected in constraints.items():
        if key == "format" and expected == "email":
            if not _EMAIL_RE.fullmatch(value):
                return False
        elif key == "min_length" and len(value) < int(expected):
            return False
        elif key == "max_length" and len(value) > int(expected):
            return False
        elif key == "require_uppercase" and _count_upper(value) < int(expected):
            return False
        elif key == "require_lowercase" and _count_lower(value) < int(expected):
            return False
        elif key == "require_digit" and _count_digit(value) < int(expected):
            return False
        elif key == "require_special" and _count_special(value) < int(expected):
            return False
        elif key == "pattern" and not re.fullmatch(str(expected), value):
            return False
    return True


# ---------------------------------------------------------------------------
# 값 생성
# ---------------------------------------------------------------------------


def _compose(
    *, length: int, n_upper: int, n_lower: int, n_digit: int, n_special: int
) -> str:
    """지정한 문자 종류 개수를 만족하면서 length 를 채운 문자열.

    부족한 길이는 소문자로 메운다. 소문자 요건이 0 이어도 소문자를 넣는 것은
    문제가 되지 않는다 — constraints 는 '최소 N자 포함' 형태의 하한 조건이고,
    '소문자를 넣지 마라' 같은 상한 조건은 없다.
    """
    parts = (UPPER_POOL[:n_upper] + LOWER_POOL[:n_lower]
             + DIGIT_POOL[:n_digit] + SPECIAL_POOL[:n_special])
    if len(parts) < length:
        parts += LOWER_POOL[0] * (length - len(parts))
    return parts


def valid_value_for(element: UIElement) -> str:
    """element 의 모든 규칙을 만족하는 값. 정상(positive) 케이스에 쓴다.

    기획서가 예시값(테스트 계정 등)을 제시했으면 그것을 우선한다. 코드가 만든
    값은 규칙은 만족하지만 시스템에 등록된 값이 아닐 수 있고, 그러면 정상
    케이스가 구현 결함 없이 실패한다(오탐).
    """
    if element.sample_value:
        return element.sample_value

    c = element.constraints
    if c.get("format") == "email":
        return "user@test.com"
    if "pattern" in c:
        # 정규식은 역생성이 어렵다. 기획서에 예시 값이 없으면 사람이 채워야 한다.
        return ""

    n_upper = int(c.get("require_uppercase", 0))
    n_lower = max(int(c.get("require_lowercase", 0)), 1)
    n_digit = max(int(c.get("require_digit", 0)), 1)
    n_special = int(c.get("require_special", 0))
    length = int(c.get("min_length", 0))

    value = _compose(length=length, n_upper=n_upper, n_lower=n_lower,
                     n_digit=n_digit, n_special=n_special)

    # max_length 가 있으면 그 안으로 줄인다. 자르면 문자 종류 요건이 깨질 수
    # 있으므로, 하한 요건에 필요한 최소 문자만 남기고 다시 만든다.
    max_len = c.get("max_length")
    if max_len is not None and len(value) > int(max_len):
        value = _compose(length=0, n_upper=n_upper, n_lower=n_lower,
                         n_digit=n_digit, n_special=n_special)[: int(max_len)]
    return value


def _violation_value(rule: str, constraints: dict) -> str | None:
    """rule 만 위반하고 나머지 constraints 는 만족하는 값. 못 만들면 None."""
    others = {k: v for k, v in constraints.items() if k != rule}

    # 나머지 규칙을 만족시키기 위한 하한을 먼저 계산한다.
    n_upper = int(others.get("require_uppercase", 0))
    n_lower = max(int(others.get("require_lowercase", 0)), 1)
    n_digit = max(int(others.get("require_digit", 0)), 1)
    n_special = int(others.get("require_special", 0))
    min_len = int(others.get("min_length", 0))

    if rule == "format" and constraints.get("format") == "email":
        return "not-an-email"

    if rule == "min_length":
        target = int(constraints["min_length"]) - 1
        if target < 0:
            return None
        # 문자 종류 요건을 지키면서 길이만 부족하게 만든다.
        base = _compose(length=0, n_upper=n_upper, n_lower=n_lower,
                        n_digit=n_digit, n_special=n_special)
        if len(base) > target:
            # 종류 요건을 지키면 이미 목표 길이를 넘는다 -> 이 규칙만 위반하는
            # 값이 존재하지 않는다. 억지로 만들면 다른 규칙까지 깨진다.
            return None
        return base + LOWER_POOL[0] * (target - len(base))

    if rule == "max_length":
        limit = int(constraints["max_length"])
        base = _compose(length=max(min_len, limit + 1), n_upper=n_upper,
                        n_lower=n_lower, n_digit=n_digit, n_special=n_special)
        return base if len(base) > limit else base + LOWER_POOL[0]

    if rule in ("require_uppercase", "require_lowercase", "require_digit", "require_special"):
        # 대상 종류를 0개로 두고 나머지 요건과 길이를 채운다.
        counts = {"require_uppercase": n_upper, "require_lowercase": n_lower,
                  "require_digit": n_digit, "require_special": n_special}
        counts[rule] = 0
        # 소문자를 0으로 만들 때는 길이 채움도 소문자를 쓸 수 없다.
        filler = DIGIT_POOL[0] if rule == "require_lowercase" else LOWER_POOL[0]
        base = _compose(length=0,
                        n_upper=counts["require_uppercase"],
                        n_lower=counts["require_lowercase"],
                        n_digit=counts["require_digit"],
                        n_special=counts["require_special"])
        if len(base) < min_len:
            base += filler * (min_len - len(base))
        max_len = others.get("max_length")
        if max_len is not None and len(base) > int(max_len):
            return None
        return base

    if rule == "pattern":
        return "___invalid___"

    return None


def sample_value_conflicts(element: UIElement) -> Optional[str]:
    """기획서 예시값이 기획서의 검증 규칙을 위반하는가.

    위반한다면 기획서 자체가 모순된 상태다 (예: '8자 이상' 이라 쓰고 예시값은
    6자). 구현 결함이 아니라 기획 결함이므로 리포트의 warnings 로 알린다.
    """
    if not element.sample_value:
        return None
    if satisfies(element.sample_value, element.constraints):
        return None
    return (
        f"'{element.label}' 의 기획서 예시값 {element.sample_value!r} 이 같은 기획서의 "
        f"검증 규칙 {element.constraints} 를 만족하지 않습니다. 기획서를 확인하세요."
    )


def violations_for_element(element: UIElement) -> list[Violation]:
    """element 의 규칙 하나하나에 대응하는 위반값 목록.

    만들 수 없는 위반(규칙끼리 충돌해 대상 규칙만 깨는 값이 존재하지 않는 경우)은
    조용히 건너뛴다. 억지로 값을 만들면 다른 규칙까지 위반해서 FAIL 원인이
    흐려지기 때문이다.
    """
    violations: list[Violation] = []

    if element.required:
        violations.append(Violation(
            rule="required",
            value="",
            description=f"'{element.label}' 을 비워 둔다 (필수 입력 검증 확인)",
        ))

    for rule in element.constraints:
        value = _violation_value(rule, element.constraints)
        if value is None:
            continue
        violations.append(Violation(
            rule=rule,
            value=value,
            description=(
                f"'{element.label}' 에 {RULE_LABELS.get(rule, rule)} 규칙만 위반하는 "
                f"값을 넣는다 (다른 규칙은 모두 충족)"
            ),
        ))
    return violations
