"""자연어 요청으로 실행할 케이스를 고른다 (S2 와 S3 사이).

## 이 층이 다른 층과 다른 점

S1 의 자연어 해석이 틀리면 케이스가 이상해지고, 그건 리포트에서 눈에 띈다.
S2 의 제목 다듬기가 틀려도 판정은 그대로다. 그런데 **케이스 선택이 틀리면
아무 흔적도 남지 않는다** — 실행되지 않은 케이스는 리포트에 아예 없고,
"검사했는데 통과" 와 "아예 안 봤다" 가 똑같이 초록불로 보인다.

지금까지 이 도구가 오탐 0건을 유지할 수 있었던 이유는 케이스 선택에 LLM 이
관여하지 않았기 때문이다. 여기서 그 보장이 깨지므로, 깨지는 방식을 통제한다.

## 다섯 가지 계약

0. **기획서에 없는 것은 묻지도 않는다** — 요청이 기획서 어휘와 하나도 겹치지 않으면
   모델을 부르기 전에 거부한다. 실모델 측정에서 "결제 화면 확인해줘" 에 7B 가
   로그인 케이스 세 개를 집어 오는 것을 확인했다 (check_grounded 참고).

1. **부분집합** — 결과는 항상 원본 케이스의 부분집합이다. 모델이 없는 case_id
   를 돌려줘도 케이스가 생기지 않는다. 실행되지 않은 케이스가 리포트에 나타나면
   판정 전체가 거짓이 된다.

2. **빈 선택 거부** — 아무것도 못 고르면 예외다. `filter_cases` 와 같은 이유로,
   0건 실행은 "전체 0건, 통과율 100%" 리포트가 된다.

3. **실패는 더 많이 검사하는 쪽으로 넘어진다** — LLM 이 죽거나 없으면 전체를
   실행한다. 적게 고르면 결함이 숨지만 많이 고르면 숨지 않는다. 방향이
   한쪽뿐이라 안전한 쪽이 정해져 있다. 대기 상한을 둘 때와 같은 판단이다.

## 모델에게 '고르는 일'만 시킨다

모델은 case_id 목록만 돌려준다. 입력값·스텝·기대값은 손대지 못한다. 그래서
해석이 틀려도 나올 수 있는 최악은 '엉뚱한 케이스를 돌렸다' 이고, '엉뚱한 판정을
내렸다' 는 될 수 없다.
"""

from __future__ import annotations

import re
from typing import Optional

from prova.llm.base import LLMClient, LLMError
from prova.models import CaseSelection, ScreenCoverage, SpecDocument, TestCase
from prova.s2_case_generator.rule_expander import RULE_LABELS

# schema 의 title 이 mock 백엔드의 라우팅 키다 (llm/mock_backend.py 참고).
_SELECTION_SCHEMA = {
    "title": "CaseSelection",
    "type": "object",
    "properties": {
        "case_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
        "reason": {"type": "string"},
    },
    "required": ["case_ids", "reason"],
}

_SELECTION_SYSTEM = """\
당신은 QA 담당자입니다. 사용자의 요청을 읽고, 케이스 목록에서 그 요청을 확인하는 데
필요한 것을 **모두** 고릅니다.

# 판단 방법

케이스를 하나씩 보면서 이렇게 물으세요.

    "이 케이스를 실행하지 않아도 사용자의 요청에 답할 수 있는가?"

답할 수 없으면 고릅니다. 하나만 골라도 되는 상황은 거의 없습니다.

# 규칙

1. 목록에 있는 case_id 만 쓰세요. 새로 만들지 마세요.
2. 요청이 **화면**을 가리키면 그 화면의 케이스를 전부 고르세요.
   대표 케이스 하나만 고르면 안 됩니다.
   특히 `required`(필수 입력)만 고르고 형식·길이·문자종류 규칙을 빠뜨리는 일이
   잦습니다. **위반 규칙이 무엇이든 그 화면 것이면 전부 고르세요.**
3. 요청이 **항목**(이메일·비밀번호·닉네임 등)을 가리키면 그 항목의 케이스를
   전부 고르세요. 규칙이 여러 개면 규칙마다 케이스가 하나씩 있습니다.
4. "~만", "~뿐" 이 붙어도 그것은 **범위를 좁히라는 뜻이지 개수를 줄이라는 뜻이
   아닙니다.** "이메일만 봐줘" 는 이메일 케이스 전부입니다.
5. 애매하면 고르세요. 빠뜨리면 결함을 놓치지만, 더 고르면 시간만 더 씁니다.
6. reason 에는 무엇을 기준으로 골랐는지 한 문장으로 쓰세요.

# 예시

목록:
- signup-valid-001 [화면 signup] 정상 회원가입
- signup-email-required-002 [화면 signup · 위반 required] 이메일 미입력
- signup-email-format-003 [화면 signup · 위반 format] 이메일 형식 위반
- signup-nickname-min_length-011 [화면 signup · 위반 min_length] 닉네임 최소 길이 위반
- login-valid-001 [화면 login] 정상 로그인

요청: "회원가입이 잘 되는지 확인해줘"
고름: signup-valid-001, signup-email-required-002, signup-email-format-003,
      signup-nickname-min_length-011
이유: 화면을 가리켰으므로 signup 화면의 케이스를 전부. login 은 다른 화면이라 제외.

요청: "이메일 입력 검증만 봐줘"
고름: signup-email-required-002, signup-email-format-003
이유: 이메일 항목의 케이스를 전부. required 와 format 둘 다 이메일 검증이다.

요청: "정상적으로 가입되는지만 보면 돼"
고름: signup-valid-001
이유: 정상 경로 하나만 명시적으로 지목했다.
"""


# 요청 전체를 뜻하는 말. 기획서 어휘가 하나도 없어도 뜻이 명확한 경우다.
_ALL_WORDS = ("전부", "전체", "모두", "모든", "다 확인", "빠짐없이", "싹")

# 낱말 쪼개기에서 버리는 말 — '검사하는 행위' 를 가리키는 일반어.
#
# 홀드아웃 측정에서 "고객센터 문의가 접수되는지 확인" 이 어휘 검사를 통과했다.
# 라벨 '비밀번호 확인' 을 쪼갠 '확인' 이 매치된 것이다. '확인' 은 거의 모든
# 요청에 들어가는 말이라, 이대로면 검사가 사실상 무력화된다.
#
# 온전한 이름('비밀번호 확인')은 그대로 어휘에 남는다 — 여기서 거르는 것은
# 쪼개서 나온 조각뿐이다. 그래서 "비밀번호 확인란이 동작하는지" 는 여전히
# 통과한다('비밀번호 확인'·'비밀번호' 가 매치).
#
# '조회' 는 홀드아웃 B(2026-08-22)가 잡았다 — 화면 이름 '주문 조회' 의 조각이
# "배송 조회가 되는지" 를 통과시켜 7B 가 orders-valid 를 골랐다. '확인' 과 같은
# 모양의 코드 결함이라 같은 원칙으로 고쳤다. 홀드아웃을 보고 고친 것이므로 B 의
# 거부 2건은 더 이상 일반화 증거가 아니다 — 다음 실물 기획서에서 다시 잰다.
_SPLIT_STOPWORDS = frozenset({"확인", "입력", "검사", "검증", "테스트", "동작", "화면", "조회"})


def spec_vocabulary(
    cases: list[TestCase], doc: Optional[SpecDocument] = None
) -> tuple[set[str], list[str], list[str]]:
    """기획서가 쓰는 말을 모은다.

    Returns:
        (대조용 어휘, 화면 이름 목록, 요소 이름 목록) — 뒤의 둘은 거부 메시지용이다.

    동의어 표를 두지 않는다. '패스워드'를 '비밀번호'로 이어 주면 편하지만, 그 표는
    기획서마다 달라지고 관리되지 않으면 조용히 낡는다. **기획서가 실제로 쓴 말만**
    받아들이고, 못 알아들었을 때 무엇을 쓸 수 있는지 알려 주는 편이 정직하다.
    """
    vocab: set[str] = set()
    screens: list[str] = []
    labels: list[str] = []

    if doc is not None:
        for screen in doc.screens:
            if screen.screen_name:
                screens.append(screen.screen_name)
                vocab.add(screen.screen_name)
            # url_path 의 조각도 받는다 ("/login" -> "login")
            vocab.update(seg for seg in screen.url_path.split("/") if len(seg) > 2)
            for el in screen.elements:
                if el.label:
                    labels.append(el.label)
                    vocab.add(el.label)
        for flow in doc.flows:
            if flow.title:
                vocab.add(flow.title)

    # 케이스에서도 모은다. doc 이 없는 호출부(단위 테스트)를 위한 것이기도 하고,
    # 규칙 이름은 doc 에 한국어로 없기 때문이기도 하다.
    for c in cases:
        vocab.add(c.screen_id)
        if c.violates:
            vocab.add(c.violates)
            vocab.add(RULE_LABELS.get(c.violates, c.violates))
        if c.flow_id:
            vocab.add(c.flow_id)

    # 규칙 이름은 한국어·영어 둘 다 받는다. 리포트와 case_id 에 영어가 그대로
    # 나오므로 사람이 "min_length 만 봐줘" 라고 쓰는 일이 실제로 있다.
    vocab.update(RULE_LABELS.values())
    vocab.update(RULE_LABELS.keys())
    # case_id 를 그대로 붙여넣는 경우도 받는다.
    vocab.update(c.case_id for c in cases)

    # 여러 낱말로 된 이름은 낱말 단위로도 받는다.
    #
    # 실모델 측정에서 "계정 찾기에서 개인정보가 새지 않는지" 가 거부됐다 —
    # 기획서는 '비밀번호 찾기' 라고 쓰고 사람은 '계정 찾기' 라고 썼기 때문이다.
    # 동의어 표를 두는 대신 **기획서가 쓴 말을 더 잘게 받는다**: '비밀번호 찾기'
    # 에서 '찾기' 를 얻으면 '계정 찾기' 도 통과한다.
    #
    # 동의어 표를 안 두는 이유는 그대로다 — 표는 기획서마다 달라지고 관리되지
    # 않으면 조용히 낡는다. 낱말 쪼개기는 기획서에서 자동으로 따라온다.
    for term in list(vocab):
        for word in re.split(r"[\s_\-/]+", term):
            if len(word) >= 2 and word not in _SPLIT_STOPWORDS:
                vocab.add(word)

    return {v for v in vocab if len(v) >= 2}, screens, labels


def check_grounded(
    request: str, cases: list[TestCase], doc: Optional[SpecDocument] = None
) -> None:
    """요청이 기획서 안의 것을 가리키는지 본다. 아니면 예외를 던진다.

    ## 왜 모델에게 묻기 전에 하는가

    실모델 측정에서 드러난 구멍이다. "결제 화면 확인해줘" 를 그대로 넘기면 7B 는
    빈 목록을 주지 않고 **로그인 케이스 세 개를 집어 온다.** 리포트에는
    "요청 '결제 화면 확인해줘' → 3건 실행, 통과율 100%" 가 남는다.

    기존 안전장치 넷 중 어느 것도 막지 못한다 — 부분집합이고, 0건이 아니고,
    해석도 '성공' 했다. 그러니 그 상황 자체를 만들지 않는다.

    ## 왜 여기서는 거부가 안전한 방향인가

    다른 실패(모델 죽음·스키마 위반)는 '더 많이 검사하는' 쪽으로 넘어졌다. 무엇을
    빼도 되는지 모르는 상태였기 때문이다. 여기서는 다르다 — **요청이 이 기획서와
    무관하다는 것을 알고 있다.** 전체를 돌려 주면 사람은 자기가 물은 것에 답을
    받았다고 읽는다. 잘못 거부하면 사람이 즉시 알고 다시 쓸 수 있지만, 잘못
    통과하면 아무도 모른다.

    Raises:
        ValueError: 기획서 어휘와 하나도 겹치지 않고 '전체' 를 뜻하지도 않을 때.
    """
    if any(w in request for w in _ALL_WORDS):
        return

    vocab, screens, labels = spec_vocabulary(cases, doc)
    lowered = request.lower()
    if any(term.lower() in lowered for term in vocab):
        return

    covers = []
    if screens:
        covers.append("화면: " + ", ".join(dict.fromkeys(screens)))
    if labels:
        covers.append("항목: " + ", ".join(dict.fromkeys(labels)))
    if not covers:
        covers.append("케이스: " + ", ".join(c.case_id for c in cases))

    lines = [f"'{request}' 는 이 기획서가 다루지 않는 것 같습니다."]
    lines += [f"  이 기획서가 다루는 것 — {line}" for line in covers]
    lines.append("  기획서의 말로 다시 쓰거나, 요청을 비우면 전체 케이스를 실행합니다.")
    raise ValueError("\n".join(lines))


def _key(case_id: str) -> str:
    """구분자·대소문자를 지운 대조용 열쇠."""
    return re.sub(r"[^a-z0-9]", "", case_id.lower())


def _resolve_id(cid: str, by_id: dict[str, TestCase]) -> tuple[Optional[str], Optional[str]]:
    """모델이 쓴 case_id 를 실제 케이스로 잇는다.

    ## 왜 고쳐 읽는가

    실모델 측정에서 7B 가 "비밀번호 확인란이 제대로 동작하는지" 에 대해 **올바른
    케이스 6건을 골랐는데** id 를 이렇게 썼다.

        signup-password_required-004        실제: signup-password-required-004
        signup-password_confirm_same_as-009 실제: signup-password_confirm-same_as-009

    case_id 가 '-' 와 '_' 를 섞어 쓰기 때문이다 — 요소 id(password_confirm)와 규칙
    이름(same_as)에 '_' 가 들어가고 이음쇠는 '-' 다. 6건 전부 무효가 되어 0건 거부로
    떨어졌다. **판단은 맞았는데 옮겨적기 실패가 그 판단을 통째로 날렸다.**

    ## 어디까지만 고쳐 읽는가

    구분자와 대소문자를 지웠을 때 **유일하게** 대응되는 케이스가 있을 때만이다.
    둘 이상에 걸리면 읽지 않는다 — 엉뚱한 케이스를 실행하는 것이 안 하는 것보다
    나쁘다. 실제 기획서 넷의 케이스 46개에서 충돌은 없다.

    없던 케이스를 만들어내지 않으므로 **부분집합 보장은 그대로다.** 그리고 고쳐
    읽었으면 그 사실을 경고로 남긴다 — 도구가 판단을 했으면 리포트에 있어야 한다.

    Returns:
        (실제 case_id 또는 None, 사람에게 알릴 말 또는 None)
    """
    trimmed = cid.strip()
    if trimmed in by_id:
        return trimmed, None

    key = _key(trimmed)
    hits = [real for real in by_id if _key(real) == key]
    if len(hits) == 1:
        return hits[0], (
            f"모델이 쓴 '{trimmed}' 를 '{hits[0]}' 로 읽었습니다 (구분자만 다릅니다)."
        )

    # 조용히 버리지 않는다. 모델이 목록에 없는 것을 지어냈다는 사실은 해석을
    # 얼마나 믿을지 판단하는 근거가 된다.
    return None, f"목록에 없는 case_id 를 무시했습니다: {cid}"


def _describe(cases: list[TestCase]) -> str:
    """모델에게 보여줄 케이스 목록.

    screen_id 를 함께 싣는다 — 요청은 보통 화면 단위("회원가입이 잘 되는지")로
    들어오는데 case_id 만으로는 화면 경계가 흐릿하다.
    """
    lines = []
    for c in cases:
        flow = f" · 흐름 {c.flow_id}" if c.flow_id else ""
        rule = f" · 위반 {c.violates}" if c.violates else ""
        lines.append(f"- {c.case_id} [화면 {c.screen_id}{flow}{rule}] {c.title}")
    return "\n".join(lines)


def _coverage(
    cases: list[TestCase],
    picked_ids: set[str],
    request: str,
    doc: Optional[SpecDocument] = None,
) -> list[ScreenCoverage]:
    """화면·흐름별로 몇 건 중 몇 건을 골랐는지 센다.

    ## 왜 '몇 건 제외' 로는 부족한가

    실모델 측정에서 "회원가입이 잘 되는지 확인해줘" 에 7B 가 17건 중 6건을 골랐고,
    프롬프트를 두 번 고쳐도 이 한 건은 안 고쳐졌다. 리포트에 "11건 제외" 라고만
    남으면 **회원가입 화면을 확인했다고 읽힌다** — 실제로는 3분의 1만 봤는데.

    화면 단위로 세면 "회원가입 6/17" 이 되고, 특히 **요청이 그 화면을 이름으로
    지목했는데 일부만 골랐다면**(named + partial) 화면과 리포트가 그걸 짚을 수 있다.

    흐름은 화면과 따로 센다 — 흐름 케이스의 screen_id 는 마지막 화면이라, 합치면
    그 화면에 케이스가 하나 더 있는 것처럼 읽힌다 (TestReport.summarize 와 같은 판단).
    """
    names = {sc.screen_id: sc.screen_name for sc in doc.screens} if doc else {}
    lowered = request.lower()

    def named(key: str, name: str) -> bool:
        if not request:
            return False
        return (key.lower() in lowered) or (bool(name) and name in request)

    order: list[tuple[str, str]] = []   # (kind, key) — 케이스 등장 순서
    slots: dict[tuple[str, str], ScreenCoverage] = {}
    for c in cases:
        kind, key = ("flow", c.flow_id) if c.flow_id else ("screen", c.screen_id)
        if (kind, key) not in slots:
            order.append((kind, key))
            name = names.get(key, key) if kind == "screen" else key
            slots[(kind, key)] = ScreenCoverage(
                kind=kind, key=key, name=name, named=named(key, name))
        slot = slots[(kind, key)]
        slot.total += 1
        if c.case_id in picked_ids:
            slot.selected += 1
    return [slots[k] for k in order]


def _all(cases: list[TestCase], request: str, doc: Optional[SpecDocument] = None,
         **kwargs) -> tuple[list[TestCase], CaseSelection]:
    """전체를 실행하는 결과를 만든다 (요청 없음 또는 해석 실패)."""
    all_ids = {c.case_id for c in cases}
    return list(cases), CaseSelection(
        request=request,
        selected=[c.case_id for c in cases],
        excluded=[],
        coverage=_coverage(cases, all_ids, request, doc),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 선택 넓히기 — 모델이 가리킨 곳을 코드가 결정적으로 넓힌다
# ---------------------------------------------------------------------------
#
# 홀드아웃 A(2026-08-19·20)의 빠뜨림 3건은 모두 같은 모양이었다 — 7B 가 **맞는 곳을
# 가리키고도 묶음을 대표 하나로 접는다**: "개수가 맞게 나오는지" 에 count-005 만,
# "가입하고 로그인까지" 에 valid 둘만, "최신순으로 나오는지" 에 orders-valid 만.
# 프롬프트로 "전부 고르라" 고 세 번 말해도 접는다(노트 18).
#
# 그래서 모델에게 더 잘 고르라고 하지 않는다. 모델이 가리킨 곳을 코드가 넓힌다.
# 방향은 넓히기뿐이다 — 이 층의 안전 방향("더 많이 검사하는 쪽") 그대로이고,
# 더 담은 것은 시간만 더 쓴다. 넓힌 케이스마다 규칙 이름이 남아 모델이 고른 것과
# 코드가 더한 것을 리포트에서 구분할 수 있다.
#
# R3 의 낱말 표는 기획서 동의어 표가 아니다 — **도구가 만드는 케이스 종류의 이름**
# (RULE_LABELS 와 같은 자리)이라 기획서마다 낡지 않는다. 기획서 어휘 검사
# (check_grounded)는 손대지 않는다.

#: R1 — 하나를 고르면 같은 화면의 같은 종류를 전부 고르는 종류. 규칙 위반
#: 케이스(violates)는 여기 없다 — "이메일 형식만" 에 required 까지 더하면 범위
#: 지목을 무시하는 것이다.
_GROUP_KINDS = frozenset({"count", "scenario", "sorted", "sum", "seedcount"})

#: R3 — 요청에 이 낱말이 있고 고른 화면에 그 종류의 케이스가 있으면 더한다.
_KIND_WORDS: dict[str, tuple[str, ...]] = {
    "sorted": ("정렬", "최신순", "오래된순", "순서"),
    "sum": ("합계", "총액", "총 금액"),
    "count": ("개수", "건수", "몇 건", "몇 개"),
    "seedcount": ("개수", "건수", "몇 건", "몇 개", "빠짐없이"),
    "precondition-guard": ("가드", "로그인 안 한", "로그인 없이", "비로그인", "로그인하지 않"),
    "placeholders": ("문구", "안내", "placeholder"),
    "labels": ("문구", "라벨", "label"),
    "options": ("선택지", "선택 항목", "항목대로", "옵션"),
}


def case_kind(case: TestCase) -> str:
    """케이스 종류. case_id 의 가운데 조각에서 읽는다 — `{screen}-{kind}-{nnn}`.

    규칙 위반은 "rule", 흐름은 "flow". options-{element} 는 "options" 로 접는다.
    """
    if case.flow_id:
        return "flow"
    if case.violates:
        return "rule"
    body = case.case_id
    if body.startswith(case.screen_id + "-"):
        body = body[len(case.screen_id) + 1:]
    body = re.sub(r"-\d+$", "", body)
    if body.startswith("options-"):
        return "options"
    return body


def widen_selection(
    cases: list[TestCase], picked_ids: list[str], request: str,
    doc: Optional[SpecDocument] = None,
) -> tuple[list[TestCase], list[tuple[str, str]]]:
    """모델이 고른 case_id 를 세 규칙으로 넓힌다.

    Returns:
        (넓힌 케이스 — 생성 순서, [(더한 case_id, 규칙)]). 더한 것이 없으면 둘째는 빈
        목록. 빈 입력이면 아무것도 더하지 않는다 — 0건 거부 계약은 그대로다.
    """
    chosen = {cid for cid in picked_ids}
    if not chosen:
        return [], []
    by_id = {c.case_id: c for c in cases}
    picked = [by_id[cid] for cid in picked_ids if cid in by_id]
    added: list[tuple[str, str]] = []

    def add(case: TestCase, rule: str) -> None:
        if case.case_id not in chosen:
            chosen.add(case.case_id)
            added.append((case.case_id, rule))

    # R1 — 묶음 완성
    groups = {(c.screen_id, case_kind(c)) for c in picked if case_kind(c) in _GROUP_KINDS}
    for c in cases:
        if (c.screen_id, case_kind(c)) in groups:
            add(c, "R1")

    # R2 — 흐름 보강: 고른 정상 케이스의 화면들이 어떤 흐름의 화면을 모두 덮으면
    valid_screens = {c.screen_id for c in picked if case_kind(c) == "valid"}
    flows = {f.flow_id: f for f in (doc.flows if doc else [])}
    for c in cases:
        if not c.flow_id:
            continue
        flow = flows.get(c.flow_id)
        screens = set(flow.screen_ids) if flow else _screens_from_flow_id(c.flow_id, cases)
        if len(screens) >= 2 and screens <= valid_screens:
            add(c, "R2")

    # R3 — 종류 낱말: 고른 화면에서만
    picked_screens = {c.screen_id for c in picked if not c.flow_id}
    lowered = request.lower()
    kinds = {k for k, words in _KIND_WORDS.items() if any(w in lowered for w in words)}
    if kinds:
        for c in cases:
            if not c.flow_id and c.screen_id in picked_screens and case_kind(c) in kinds:
                add(c, "R3")

    return [c for c in cases if c.case_id in chosen], added


def _screens_from_flow_id(flow_id: str, cases: list[TestCase]) -> set[str]:
    """doc 이 없을 때 flow_id(`signup_then_login`)에서 화면 id 를 읽는다 — 흐름 id 는
    화면 id 를 밑줄로 잇는 관례라서, 케이스에 있는 화면 id 만 받는다."""
    known = {c.screen_id for c in cases}
    return {seg for seg in re.split(r"_(?:then|link_to|to)_", flow_id) if seg in known}


def select_cases(
    cases: list[TestCase],
    request: Optional[str],
    llm: Optional[LLMClient],
    doc: Optional[SpecDocument] = None,
) -> tuple[list[TestCase], CaseSelection]:
    """자연어 요청에 해당하는 케이스만 남긴다.

    Args:
        cases: S2 가 생성한 전체 케이스
        request: 사용자 요청 원문. None 이거나 공백이면 전체를 실행한다.
        llm: 요청 해석에 쓸 백엔드. None 이면 전체를 실행한다.
        doc: 기획서. 요청이 이 문서가 다루는 것을 가리키는지 먼저 확인하는 데 쓴다
            (check_grounded 참고). None 이면 케이스에서 어휘를 만든다.

    Returns:
        (실행할 케이스, 선택 내역). 선택 내역은 리포트에 그대로 실린다.

    Raises:
        ValueError: 요청이 기획서와 무관하거나, 요청에 해당하는 케이스가 하나도
            없을 때. 둘 다 "확인하지 않았는데 통과율이 남는" 결과를 막는다.
    """
    text = (request or "").strip()
    if not text:
        return _all(cases, "", doc)

    # 모델에게 묻기 전에 코드가 먼저 본다. 물어 보면 무엇이든 집어 온다.
    check_grounded(text, cases, doc)

    if llm is None:
        return _all(
            cases,
            text,
            doc,
            fallback=True,
            warnings=["LLM 백엔드가 없어 요청을 해석하지 못했습니다. 전체 케이스를 실행합니다."],
        )

    try:
        raw = llm.complete_json(
            system=_SELECTION_SYSTEM,
            user=f"요청: {text}\n\n케이스 목록:\n{_describe(cases)}\n\n출력 JSON:",
            schema=_SELECTION_SCHEMA,
            max_tokens=1024,
        )
    except LLMError as exc:
        # 여기서 일부만 돌리거나 멈추지 않는다. 해석에 실패했으면 무엇을 빼도
        # 되는지 모르는 상태이고, 그 상태에서 빼는 것은 결함을 덮는 일이다.
        return _all(
            cases,
            text,
            doc,
            fallback=True,
            warnings=[f"요청 해석에 실패해 전체 케이스를 실행합니다: {exc}"],
        )

    by_id = {c.case_id: c for c in cases}
    warnings: list[str] = []
    wanted: list[str] = []
    for cid in raw.get("case_ids", []):
        real, note = _resolve_id(cid, by_id)
        if note:
            warnings.append(note)
        if real and real not in wanted:
            wanted.append(real)

    if not wanted:
        available = ", ".join(c.case_id for c in cases)
        raise ValueError(
            f"'{text}' 에 해당하는 케이스가 없습니다.\n  실행 가능한 케이스: {available}"
        )

    # 모델이 가리킨 곳을 코드가 넓힌다(widen_selection 참고). 모델이 돌려준 순서가
    # 아니라 생성 순서를 따른다 — 흐름 케이스는 화면을 이어서 밟으므로 순서 자체가
    # 의미를 갖는다.
    picked, widened = widen_selection(cases, wanted, text, doc)
    chosen = {c.case_id for c in picked}
    selection = CaseSelection(
        request=text,
        selected=[c.case_id for c in picked],
        excluded=[c.case_id for c in cases if c.case_id not in chosen],
        reason=(raw.get("reason") or "").strip(),
        warnings=warnings,
        widened=[f"{cid} ({rule})" for cid, rule in widened],
        coverage=_coverage(cases, chosen, text, doc),
    )
    return picked, selection


def select_by_ids(
    cases: list[TestCase],
    case_ids: list[str],
    request: str = "",
    reason: str = "",
    doc: Optional[SpecDocument] = None,
) -> tuple[list[TestCase], CaseSelection]:
    """사람이 승인한 case_id 목록으로 좁힌다 (UI 의 계획 확인 단계 결과).

    `select_cases` 와 계약이 같다 — 부분집합이고, 비면 예외다. 다른 점은 **모델을
    부르지 않는다**는 것뿐이다. 계획 화면에서 이미 해석을 마쳤으므로 실행 시점에
    다시 물으면 그 사이에 답이 달라져 사람이 승인한 것과 다른 것이 돌 수 있다.

    Args:
        case_ids: 사람이 승인한 목록. 여기에 없는 케이스는 실행하지 않는다.
        request: 이 승인을 낳은 요청 원문 (리포트 기록용)
        reason: 계획 단계에서 모델이 밝힌 근거 (리포트 기록용)
        doc: 기획서. 화면별 확인 범위를 세는 데 쓴다 (_coverage 참고).
    """
    by_id = {c.case_id: c for c in cases}
    warnings = [
        f"승인 목록에 있으나 이번 생성 결과에 없는 case_id 를 무시했습니다: {cid}"
        for cid in case_ids
        if cid not in by_id
    ]
    wanted = {cid for cid in case_ids if cid in by_id}

    if not wanted:
        available = ", ".join(c.case_id for c in cases)
        raise ValueError(
            f"""승인한 케이스 중 실행 가능한 것이 없습니다.
  승인 목록: {', '.join(case_ids) or '(비어 있음)'}
  실행 가능한 케이스: {available}"""
        )

    picked = [c for c in cases if c.case_id in wanted]
    return picked, CaseSelection(
        request=request,
        selected=[c.case_id for c in picked],
        excluded=[c.case_id for c in cases if c.case_id not in wanted],
        reason=reason,
        approved=True,
        warnings=warnings,
        coverage=_coverage(cases, wanted, request, doc),
    )
