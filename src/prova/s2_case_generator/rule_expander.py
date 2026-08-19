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

## 값은 요소 하나만 보고 정할 수 없다 (same_as)

회원가입 화면의 '비밀번호 확인' 은 자기 규칙이 없다. **다른 요소와 같아야 한다**
는 것이 규칙이다. 그래서 값 생성이 요소 단위 함수로 끝나지 않고 화면 단위
해석(resolve_values)이 필요해진다. 의존 순서대로 풀어야 하기 때문이다.

이 확장이 위의 '하나의 케이스는 하나의 규칙만 위반한다' 계약과 부딪히는 지점이
하나 있다. 비밀번호에 위반값을 넣으면 비밀번호 확인의 값도 함께 어긋나 두 규칙이
동시에 깨진다. 그래서 위반 케이스를 만들 때 **위반값을 먼저 고정하고 그것에
의존하는 값들을 다시 계산한다**(resolve_values 의 overrides). 비밀번호 확인은
위반값과 같은 값이 되어, 깨지는 규칙은 여전히 비밀번호의 것 하나다.

예외는 required 위반이다. 비밀번호를 비우면 비밀번호 확인도 비게 되어 두 요소의
required 가 함께 깨진다. 빈 값과 같아야 하는 값은 빈 값뿐이므로 피할 수 없다.
두 경우 모두 기대 문구가 같은 '필수 입력' 문구라서 판정은 흔들리지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from prova.models import ScreenSpec, UIElement

SPECIAL_POOL = "!@#$%^&*"
UPPER_POOL = "ABCDEFGH"
LOWER_POOL = "abcdefgh"
DIGIT_POOL = "12345678"

# 체크박스의 '체크된 상태' 를 나타내는 값.
#
# 값으로 표현하는 이유: TestStep.value 는 문자열이고, 스텝을 만드는 쪽에서
# '빈 값이면 uncheck, 아니면 check' 로 일관되게 처리할 수 있다. HTML 체크박스가
# 전송하는 기본값이 "on" 이라 그것을 그대로 쓴다.
CHECKED = "on"

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
    "same_as": "다른 항목과 일치",
    "numeric": "숫자만 입력",
}

# 사용자가 문자를 직접 입력하지 않는 요소 유형.
#
# 이 유형에는 문자 종류·길이 규칙을 전개하지 않는다. 선택지에서 고르거나
# 체크하는 요소이므로 '8자 미달인 값' 같은 입력을 만들 방법이 없고, 억지로
# 만들면 실행 자체가 실패해 판정이 조작 오류로 뭉개진다. 이 요소들에서
# 검증할 수 있는 것은 '선택/체크하지 않았을 때' 뿐이다.
NON_TEXT_TYPES = ("checkbox", "select")


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


def satisfies(value: str, constraints: dict, ref_value: Optional[str] = None) -> bool:
    """value 가 constraints 의 모든 규칙을 만족하는가.

    위반값 생성이 의도대로 됐는지 검사하는 기준이다. 이 함수와 SUT 의 검증
    로직이 같은 규칙을 구현하지만, 서로 참조하지 않는다 — 테스트 대상과 판정
    기준이 같은 코드를 공유하면 둘이 함께 틀렸을 때 알 수 없기 때문이다.

    Args:
        ref_value: same_as 가 가리키는 요소의 값. same_as 는 값 하나만 보고
            판정할 수 없는 유일한 규칙이라 밖에서 받는다. 넘기지 않으면 same_as
            검사를 건너뛴다 — 판정할 근거가 없을 때 임의로 통과/실패시키는 것보다
            그 규칙을 보지 않았다고 두는 편이 낫다. 건너뛴 사실은 호출자가
            안다(resolve_values 가 의존을 풀어 값을 넘긴다).
    """
    for key, expected in constraints.items():
        if key == "same_as":
            if ref_value is not None and value != ref_value:
                return False
        elif key == "format" and expected == "email":
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
        elif key == "numeric" and expected:
            if not value.isdigit():
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


def valid_value_for(element: UIElement, ref_value: Optional[str] = None) -> str:
    """element 의 모든 규칙을 만족하는 값. 정상(positive) 케이스에 쓴다.

    기획서가 예시값(테스트 계정 등)을 제시했으면 그것을 우선한다. 코드가 만든
    값은 규칙은 만족하지만 시스템에 등록된 값이 아닐 수 있고, 그러면 정상
    케이스가 구현 결함 없이 실패한다(오탐).

    Args:
        ref_value: same_as 가 가리키는 요소의 값. 의존 순서를 아는 것은
            resolve_values 이므로 여기서는 받아 쓰기만 한다.
    """
    if element.sample_value:
        return element.sample_value

    if element.type == "checkbox":
        return CHECKED

    if element.type == "select":
        # 선택지가 없으면 무엇을 골라야 할지 알 수 없다. 빈 값을 넣어 실행은
        # 계속하되, 기획서 결함으로 경고된다(spec_defects).
        return element.options[0] if element.options else ""

    if "same_as" in element.constraints:
        # 참조를 풀지 못했으면 빈 값이 된다. 이 경우도 spec_defects 가 경고한다.
        return ref_value or ""

    c = element.constraints
    if c.get("numeric"):
        # min/max_length 가 함께 있으면 그 길이에 맞춰 숫자로 채운다.
        min_len = int(c.get("min_length", 0))
        max_len = c.get("max_length")
        if max_len is not None:
            target_len = int(max_len)
        else:
            target_len = max(min_len, 5)  # 기본값: 최소 길이 또는 5자
        return "1" * target_len

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


def _same_as_violation_value(
    ref_value: Optional[str], others: dict
) -> str | None:
    """참조 요소와 다르지만 나머지 규칙은 만족하는 값.

    참조 값을 모르면 만들 수 없다 — '무엇과 다른 값' 인지 정할 수 없기 때문이다.
    그때는 None 을 돌려 케이스를 만들지 않는다. 아무 값이나 넣으면 우연히 참조
    값과 같아져서, 구현에 일치 검증이 없어도 PASS 가 나올 수 있다(미탐).
    """
    if ref_value is None:
        return None

    # 참조 값에 한 글자 붙이면 '다르다' 는 보장되고, 하한 조건(길이·문자 종류)은
    # 참조 값이 이미 만족하므로 그대로 유지된다.
    candidate = ref_value + LOWER_POOL[0]
    if satisfies(candidate, others):
        return candidate

    # max_length 같은 상한 규칙에 걸린 경우. 규칙을 만족하는 값을 새로 만들어
    # 보고, 그게 참조 값과 같으면 이 규칙만 위반하는 값을 만들 수 없다.
    fallback = _compose(
        length=int(others.get("min_length", 0)),
        n_upper=int(others.get("require_uppercase", 0)),
        n_lower=max(int(others.get("require_lowercase", 0)), 1),
        n_digit=max(int(others.get("require_digit", 0)), 1),
        n_special=int(others.get("require_special", 0)),
    )
    if fallback != ref_value and satisfies(fallback, others):
        return fallback
    return None


def _violation_value(
    rule: str, constraints: dict, ref_value: Optional[str] = None
) -> str | None:
    """rule 만 위반하고 나머지 constraints 는 만족하는 값. 못 만들면 None."""
    others = {k: v for k, v in constraints.items() if k != rule}

    # 나머지 규칙을 만족시키기 위한 하한을 먼저 계산한다.
    #
    # 소문자·숫자에 최소 1자의 바닥을 두는 것은 규칙이 아니라 값을 사람이 읽기
    # 좋게 만들려는 정책이다 (규칙이 없어도 "aaaaaaaa" 보다 "Aa1!aaaa" 가 낫다).
    # 규칙상 필요한 개수는 *_req 쪽이다. 둘을 구분해 두는 이유는 min_length 에서
    # 드러난다 — 그 정책 때문에 위반값을 만들 수 없게 되는 경우가 있다.
    n_upper = int(others.get("require_uppercase", 0))
    n_lower_req = int(others.get("require_lowercase", 0))
    n_digit_req = int(others.get("require_digit", 0))
    n_lower = max(n_lower_req, 1)
    n_digit = max(n_digit_req, 1)
    n_special = int(others.get("require_special", 0))
    min_len = int(others.get("min_length", 0))

    if rule == "format" and constraints.get("format") == "email":
        return "not-an-email"

    if rule == "numeric":
        # 숫자가 하나도 없는 짧은 한국어 — 위반이 자명하고 리포트에서 읽힌다.
        return "만원"

    if rule == "same_as":
        return _same_as_violation_value(ref_value, others)

    if rule == "min_length":
        target = int(constraints["min_length"]) - 1
        if target <= 0:
            # 길이 0 은 빈 값이고, 그건 required 위반과 구분되지 않는다. 같은
            # 입력으로 두 케이스를 만들면 리포트에서 원인이 갈리지 않는다.
            return None
        # 문자 종류 요건을 지키면서 길이만 부족하게 만든다.
        base = _compose(length=0, n_upper=n_upper, n_lower=n_lower,
                        n_digit=n_digit, n_special=n_special)
        if len(base) > target:
            # 읽기 좋게 만들려고 넣은 소문자·숫자 때문에 목표 길이를 넘었을 수
            # 있다 (예: '2자 이상' 규칙만 있는 닉네임). 실제 규칙만으로 다시
            # 만들어 본다. 그래도 넘으면 이 규칙만 위반하는 값이 존재하지 않는다.
            base = _compose(length=0, n_upper=n_upper, n_lower=n_lower_req,
                            n_digit=n_digit_req, n_special=n_special)
            if len(base) > target:
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


def violations_for_element(
    element: UIElement, ref_value: Optional[str] = None
) -> list[Violation]:
    """element 의 규칙 하나하나에 대응하는 위반값 목록.

    만들 수 없는 위반(규칙끼리 충돌해 대상 규칙만 깨는 값이 존재하지 않는 경우)은
    조용히 건너뛴다. 억지로 값을 만들면 다른 규칙까지 위반해서 FAIL 원인이
    흐려지기 때문이다.

    Args:
        ref_value: same_as 가 가리키는 요소의 값 (resolve_values 가 풀어 준다).
    """
    violations: list[Violation] = []

    if element.required:
        violations.append(Violation(
            rule="required",
            value="",
            description=_required_description(element),
        ))

    if element.type in NON_TEXT_TYPES:
        # 선택·체크 요소에는 문자 규칙을 전개하지 않는다 (NON_TEXT_TYPES 설명 참고).
        return violations

    for rule in element.constraints:
        value = _violation_value(rule, element.constraints, ref_value)
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


def _required_description(element: UIElement) -> str:
    if element.type == "checkbox":
        return f"'{element.label}' 을 체크하지 않는다 (필수 동의 검증 확인)"
    if element.type == "select":
        return f"'{element.label}' 을 선택하지 않는다 (필수 선택 검증 확인)"
    return f"'{element.label}' 을 비워 둔다 (필수 입력 검증 확인)"


# ---------------------------------------------------------------------------
# 화면 단위 값 해석 — same_as 의존을 순서대로 푼다
# ---------------------------------------------------------------------------


def resolve_values(
    elements: list[UIElement],
    overrides: Optional[dict[str, str]] = None,
) -> tuple[dict[str, str], list[str]]:
    """요소별 입력값을 정한다. same_as 의존을 따라 순서대로 푼다.

    Args:
        elements: 값을 채울 요소들 (버튼처럼 값이 없는 요소가 섞여도 무해하다).
        overrides: 그대로 쓸 값. 위반 케이스에서 대상 요소의 위반값을 여기 넣으면,
            그것에 의존하는 값(비밀번호 확인 등)이 위반값 기준으로 다시 계산된다.
            이 재계산이 '하나의 케이스는 하나의 규칙만 위반한다' 계약을 지킨다.

    Returns:
        (element_id -> 값, 기획서 결함 경고 목록)

    경고를 값과 함께 돌려주는 이유: same_as 가 없는 요소를 가리키거나 서로를
    가리켜 순환하면 그건 구현 결함이 아니라 기획서 결함이다. 값 해석을 조용히
    포기하면 정상 케이스가 이유 없이 실패하는데, 그 원인이 리포트에 남지 않는다.
    """
    by_id = {e.element_id: e for e in elements}
    fixed = dict(overrides or {})
    values: dict[str, str] = {}
    warnings: list[str] = []

    def resolve(element_id: str, stack: list[str]) -> str:
        if element_id in values:
            return values[element_id]

        stack = stack + [element_id]
        element = by_id[element_id]

        if element_id in fixed:
            # 지정된 값은 규칙과 무관하게 그대로 쓴다. 위반값을 넣는 자리다.
            values[element_id] = fixed[element_id]
            return values[element_id]

        ref_id = element.constraints.get("same_as")
        ref_value: Optional[str] = None
        if ref_id:
            if ref_id not in by_id:
                warnings.append(
                    f"'{element.label}' 의 same_as 가 가리키는 요소 {ref_id!r} 가 "
                    f"기획서에 없습니다. 값 일치 검증 케이스를 만들 수 없습니다."
                )
            elif ref_id in stack:
                warnings.append(
                    f"same_as 제약이 순환합니다: {' -> '.join(stack + [ref_id])}. "
                    f"기획서를 확인하세요."
                )
            else:
                ref_value = resolve(ref_id, stack)

        values[element_id] = valid_value_for(element, ref_value)
        return values[element_id]

    for element in elements:
        resolve(element.element_id, [])
    return values, warnings


# ---------------------------------------------------------------------------
# 기획서 자체의 모순 — 구현 결함이 아니라 기획 결함
# ---------------------------------------------------------------------------


def sample_value_conflicts(
    element: UIElement, ref_value: Optional[str] = None
) -> Optional[str]:
    """기획서 예시값이 기획서의 검증 규칙을 위반하는가.

    위반한다면 기획서 자체가 모순된 상태다 (예: '8자 이상' 이라 쓰고 예시값은
    6자). 구현 결함이 아니라 기획 결함이므로 리포트의 warnings 로 알린다.
    """
    if not element.sample_value:
        return None
    if satisfies(element.sample_value, element.constraints, ref_value):
        return None
    return (
        f"'{element.label}' 의 기획서 예시값 {element.sample_value!r} 이 같은 기획서의 "
        f"검증 규칙 {element.constraints} 를 만족하지 않습니다. 기획서를 확인하세요."
    )


def spec_defects(spec: ScreenSpec) -> list[str]:
    """기획서 안에서 발견되는 모순을 모아 돌려준다.

    한곳에 모으는 이유: 이 경고들은 모두 '케이스가 FAIL 이라서' 가 아니라
    '기획서가 앞뒤가 안 맞아서' 나오는 것이다. 구현 결함 보고와 섞이면 개발자가
    자기 코드를 고치려 하는데 정작 고칠 곳은 기획서다.
    """
    values, defects = resolve_values(spec.elements)

    for element in spec.elements:
        ref_id = element.constraints.get("same_as")
        conflict = sample_value_conflicts(
            element, values.get(ref_id) if ref_id else None
        )
        if conflict:
            defects.append(conflict)

        if element.type == "select" and not element.options:
            defects.append(
                f"'{element.label}' 은 선택 요소인데 선택 목록(options)이 "
                f"비어 있습니다. 정상 케이스가 값을 고를 수 없습니다."
            )

    defects.extend(_scenario_defects(spec))
    return defects


def _scenario_defects(spec: ScreenSpec) -> list[str]:
    """기획서 예시 시나리오가 실행 가능한 형태인지 본다.

    두 경우 모두 **조용히 오탐을 만든다.** 없는 요소를 가리키면 지정한 값이 그냥
    무시되어 시나리오가 의도와 다른 것을 확인하고(대개 통과해 버린다), 기대 문구가
    비면 비교할 대상이 없어 그 케이스가 항상 실패한다.
    """
    defects: list[str] = []
    known = {e.element_id for e in spec.elements}

    for i, scenario in enumerate(spec.scenarios, 1):
        missing = sorted(set(scenario.given) - known)
        if missing:
            defects.append(
                f"기획서 예시 {i}번이 가리키는 요소 {', '.join(missing)} 가 화면에 "
                f"없습니다. 그 값은 무시되므로 시나리오가 의도한 것을 확인하지 못합니다."
            )
        if not scenario.expect_text.strip():
            defects.append(
                f"기획서 예시 {i}번에 노출돼야 하는 문구가 비어 있습니다. "
                f"비교할 대상이 없어 이 케이스는 항상 실패합니다."
            )

    # 건수를 적어 두고 목록 요소는 정의하지 않은 경우.
    #
    # 이건 조용히 **미탐**을 만든다. 위 두 경우와 반대 방향이다 — 건수 케이스가
    # 아예 만들어지지 않으므로 리포트에는 아무 흔적도 남지 않고, 전부 통과한
    # 것처럼 보인다. 확인하지 않은 것과 확인해서 통과한 것은 다르다.
    counted = [i for i, s in enumerate(spec.scenarios, 1) if s.expect_count is not None]
    if counted and not any(e.type == "list" for e in spec.elements):
        defects.append(
            f"기획서 예시 {', '.join(map(str, counted))}번에 결과 건수가 있으나 "
            f"UI 요소 표에 목록(유형 '목록') 요소가 없습니다. 무엇을 셀지 알 수 "
            f"없어 건수 검증을 만들지 못했습니다 — 목록 요소를 추가하세요."
        )
    return defects
