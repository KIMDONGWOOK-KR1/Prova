"""기획서 예시값의 `{고유}` 를 실행할 때 케이스마다 새 값으로 바꾼다.

## 왜 (2026-09-23 외부 사이트 실측)

가입처럼 한 번 쓰면 끝나는 화면은 예시 아이디가 매번 같으면 **두 번째 실행부터**
'이미 있는 계정' 으로 정상 케이스가 FAIL 한다. 사이트는 멀쩡하다 — 오탐이다.
기획서 작성자가 `prova-{고유}` 처럼 적으면 실행마다 다른 값이 들어간다.

## 왜 실행 직전인가

케이스를 만들 때(S2) 바꾸면 계획(plan.json)에 값이 박히고, `--resume` 이 같은
값을 다시 쓴다. 원본 케이스는 그대로 두고 실행할 사본만 바꾼다.

## 한 케이스 안에서는 같은 값

전제·본 스텝·기대 문구를 한 값으로 바꾼다. 흐름 케이스가 가입한 아이디로 다음
화면에서 로그인하려면 같아야 한다. 케이스 사이에는 공유하지 않는다.

## 한계

값은 소문자·숫자 8자다(`_` 같은 기호를 거부하는 사이트가 있었다). S2 의 예시값
검사(rule_expander.sample_value_conflicts)는 바꾸기 전 글자를 본다 — 토큰(4자)과
바뀐 값(8자)의 길이가 달라 최대 길이 규칙에 걸릴 수 있다.
"""

from __future__ import annotations

import secrets

from prova.models import TestCase

UNIQUE_TOKEN = "{고유}"


def fill_unique(case: TestCase) -> TestCase:
    """토큰을 새 값으로 바꾼 사본. 토큰이 없으면 같은 객체를 돌려준다."""
    if UNIQUE_TOKEN not in case.model_dump_json():
        return case
    stamp = secrets.token_hex(4)

    def sub(text):
        return text.replace(UNIQUE_TOKEN, stamp) if text else text

    filled = case.model_copy(deep=True)
    for step in filled.setup_steps + filled.steps:
        step.value = sub(step.value)
    filled.expected.value = sub(filled.expected.value)
    return filled
