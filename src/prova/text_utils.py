"""텍스트 정규화 — PDF 문구와 화면 문구를 같은 기준에서 비교한다.

## 왜 이 모듈이 필요한가

PDF에서 추출한 텍스트는 원문을 그대로 복원하지 못한다. reportlab이든 어떤
PDF 생성기든 셀·단락 폭에 맞춰 줄을 바꾸고, 한글은 단어 경계가 아닌 문자
단위로도 줄바꿈되기 때문이다. 실제로 관측한 예:

    원문   비밀번호는 8자 이상이며 대문자·특수문자를 각 1자 이상 포함해야 합니다.
    추출   비밀번호는 8자\n이상이며 대문자·\n특수문자를 각\n1자 이상\n포함해야 합니다.

'8자\n이상이며' 의 개행은 공백으로 바꿔야 맞고, '대문자·\n특수문자' 의 개행은
지워야 맞다. 텍스트만 보고는 어느 쪽인지 판별할 수 없다.

그래서 Prova는 원문 복원을 시도하지 않는다. 대신 **비교를 정규형에서** 한다.
공백을 전부 제거한 형태(loosen)로 양쪽을 맞춰 비교하면 줄바꿈 위치가 어떻든
같은 문구는 같게, 다른 문구는 다르게 판정된다.

## 주의

loosen은 공백만 무시한다. 문구 자체가 다르면(구현이 기획서와 다른 메시지를
쓴 경우) 반드시 다른 정규형이 나와야 한다 — 그게 Prova가 잡아내야 하는
불일치이기 때문이다. 조사·어미까지 관대하게 비교하려는 유혹을 견뎌야 한다.
"""

from __future__ import annotations

import re
from typing import Optional

#: 기획서 문장 안의 따옴표 짝 (여는 것 -> 닫는 것). 한 곳에 둔다 — 2026-08-22 까지 세
#: 모듈이 각자 같은 패턴을 갖고 있었고, 따옴표 집합을 한쪽만 고치면 문구 추출이 조용히
#: 갈렸다. 길이 상한은 쓰는 곳의 사정이라 인자로 받는다. 큰따옴표 계열을 먼저 본다.
_DOUBLE_PAIRS = (('"', '"'), ("“", "”"))
_SINGLE_PAIRS = (("'", "'"), ("‘", "’"))


def _pairs_re(pairs) -> "re.Pattern[str]":
    """짝 맞춘 따옴표 패턴. 길이는 여기서 거르지 않는다 — 안에서 거르면 너무 짧은 문구
    ('"가"') 의 닫는 따옴표가 다음 문구의 여는 따옴표로 잘못 짝지어진다.

    ASCII 작은따옴표는 영어 아포스트로피와 모양이 같다. 글자 바로 뒤의 ' 는 여는
    따옴표가 아니고(user's), 영문자 바로 앞의 ' 는 닫는 따옴표가 아니다(John's 의 s).
    한글 조사가 바로 붙는 것('필수'를)은 막지 않는다.
    """
    parts = []
    for o, c in pairs:
        if o == "'":
            parts.append(r"(?<![A-Za-z0-9])'([^']*)'(?![A-Za-z])")
        else:
            parts.append(f"{re.escape(o)}([^{re.escape(c)}]*){re.escape(c)}")
    return re.compile("|".join(parts))


def find_quoted(text: str, max_len: int) -> list[str]:
    """기획서 문장에서 따옴표 안 문구(2~max_len 글자)를 순서대로 뽑는다.

    ## 짝을 맞추고, 큰따옴표 계열을 먼저 본다 (2026-09-23)

    예전 패턴은 여섯 따옴표 중 아무것으로나 열고 아무것으로나 닫았다. 아포스트로피(')도
    그 안에 있어서 "Welcome! You're logged in." 은 "Welcome! You" 로 잘렸고, 따옴표가
    없는 영어 문장 "user's profile ... John's" 에서도 ' 와 ' 사이를 문구로 잡았다.
    쓰는 곳마다 둔 짧은 길이 한도(40)가 그걸 우연히 줄여 주고 있었는데, 그 한도 때문에
    parabank 의 61자 성공 문구는 아예 못 읽었다.

    그래서 여는 따옴표와 같은 짝으로 닫힐 때만 문구로 본다. 큰따옴표 계열에서 하나라도
    찾으면 그것만 쓰고, 없을 때만 작은따옴표 짝을 본다 — 영어 문장의 아포스트로피가
    문구를 만들어 내지 않게.
    """
    for pairs in (_DOUBLE_PAIRS, _SINGLE_PAIRS):
        inner = [next(g for g in m.groups() if g is not None)
                 for m in _pairs_re(pairs).finditer(text)]
        found = [q for q in inner if 2 <= len(q) <= max_len]
        if found:
            return found
    return []


_WS = re.compile(r"\s+")

# PDF 폰트에 글리프가 없을 때 pdfplumber 가 남기는 자리표시자.
# 불릿·특수기호에서 흔히 나온다. 예: '(cid:127) 필수 입력이다'
_CID = re.compile(r"\(cid:\d+\)")


def strip_cid(text: Optional[str]) -> str:
    """(cid:NNN) 자리표시자를 제거한다.

    PDF 에 폰트 글리프가 임베딩되지 않으면 pdfplumber 가 문자 대신 이 형태를
    돌려준다. 그대로 LLM 프롬프트에 들어가면 노이즈가 되고, 에러 문구 비교에
    끼면 오판정을 만든다. 우리가 만드는 PDF 는 폰트를 제대로 심어 이 문제가
    없지만, 실무 PDF 가 들어올 때를 대비해 파서 단계에서 걸러낸다.
    """
    if not text:
        return ""
    return _CID.sub(" ", text)


def normalize_ws(text: Optional[str]) -> str:
    """(cid:NNN) 을 걷어내고 개행·탭·연속 공백을 단일 공백으로 정리한다.

    사람이 읽는 용도(리포트 표시, LLM 프롬프트)에 쓴다.
    """
    if not text:
        return ""
    return _WS.sub(" ", strip_cid(text)).strip()


def loosen(text: Optional[str]) -> str:
    """공백을 전부 제거한 비교용 정규형.

    문구 동일성 판정에만 쓴다. 사람에게 보여주는 용도로는 쓰지 않는다.
    """
    if not text:
        return ""
    return _WS.sub("", strip_cid(text))


def contains_loose(haystack: Optional[str], needle: Optional[str]) -> bool:
    """haystack 안에 needle 문구가 (공백 차이를 무시하고) 들어 있는가.

    빈 needle은 False를 반환한다. 빈 문자열은 어떤 텍스트에도 포함되므로,
    기대 문구가 비어 있는 케이스가 조용히 PASS로 통과하는 사고를 막는다.
    """
    n = loosen(needle)
    if not n:
        return False
    return n in loosen(haystack)
