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

#: 기획서 문장 안의 따옴표 묶음. 한 곳에 둔다 — 2026-08-22 까지 세 모듈이 각자
#: 같은 패턴을 갖고 있었고(길이 상한만 달랐다), 따옴표 집합을 한쪽만 고치면 문구
#: 추출이 조용히 갈렸다. 길이 상한은 쓰는 곳의 사정이라 인자로 받는다.
_QUOTES = "\"'“”‘’"


def quoted_re(max_len: int) -> "re.Pattern[str]":
    """따옴표로 감싼 2~max_len 글자를 잡는 패턴. group(1) 이 안쪽 문구다."""
    return re.compile(f"[{_QUOTES}]([^{_QUOTES}]{{2,{max_len}}})[{_QUOTES}]")

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
