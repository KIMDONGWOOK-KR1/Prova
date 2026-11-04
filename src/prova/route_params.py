"""화면 경로의 자리표시자(`/pets/:petId`)를 다룬다.

## 왜 필요한가 (2026-11-03)

상세 화면처럼 경로에 값이 들어가는 화면은 기획서에 `/pets/:petId` 로 적힌다. 그 글자를
그대로 열면 SPA 는 200 으로 '없는 항목' 화면을 그리고, 그 화면에서 찾는 요소는 전부
'못 찾음' 이 된다 — 라벨이 틀린 것처럼 보이지만 실제로는 엉뚱한 화면에 있다.

기획서가 `예시 경로 | /pets/luna` 를 적어 두었으면 그 값으로 연다. 없으면 열지 않는다.
"""

from __future__ import annotations

import os
import re

# 경로 조각 하나가 통째로 자리표시자인 모양: :id · {id} · [id]
_SEGMENT = re.compile(r"^(:[A-Za-z_]\w*|\{[^/{}]+\}|\[[^/\[\]]+\])$")


def _path_part(path: str) -> str:
    """스킴·호스트와 쿼리·조각을 뗀 경로. 포트의 ':' 와 쿼리의 ':' 는 자리표시자가 아니다."""
    path = re.sub(r"^[a-z]+://[^/]*", "", path)
    return re.split(r"[?#]", path, maxsplit=1)[0]


def _segments(path: str) -> list[str]:
    return _path_part(path).strip("/").split("/")


def is_route(target: str) -> bool:
    """열 수 있는 주소 하나인가. 공백·쉼표가 들어 있으면 문장이거나 경로 여럿이다.

    2026-11-04 0051 B: 공통 화면의 경로 칸이 '모든 서비스 경로에 공통 적용' 이었다. 그대로
    열자 앱이 '없는 페이지' 를 그렸고, 헤더 버튼이 없다는 오탐이 났다.
    """
    # 쉼표는 경로 사이(', /b', ',/b')일 때만 거른다 — 쿼리 값의 쉼표('ids=a,b')는 주소의 일부다.
    return bool(target) and not re.search(r"\s|,\s*/", target)


def _query(path: str) -> dict[str, str]:
    """쿼리의 키 -> 값. 조각(#)은 뗀다."""
    if "?" not in path:
        return {}
    query = path.split("?", 1)[1].split("#", 1)[0]
    pairs = (p.split("=", 1) for p in query.split("&") if p)
    return {kv[0]: (kv[1] if len(kv) > 1 else "") for kv in pairs}


def _query_placeholders(path: str) -> set[str]:
    """값이 통째로 자리표시자인 쿼리 키 — `/search?q={keyword}` 의 q.

    2026-11-04: 경로 조각만 보던 검사를 이것이 빠져나갔다. 값 일부만 중괄호인 것('{a}x')과
    'a:b' 는 자리표시자가 아니다."""
    return {k for k, v in _query(path).items() if _SEGMENT.match(v)}


def has_placeholder(path: str) -> bool:
    """경로나 쿼리에 값을 채워야 하는 자리가 있는가."""
    return (any(_SEGMENT.match(seg) for seg in _segments(path))
            or bool(_query_placeholders(path)))


def _segment_placeholder(path: str) -> bool:
    return any(_SEGMENT.match(seg) for seg in _segments(path))


def _matches(pattern: str, example: str) -> bool:
    """예시 경로가 패턴과 같은 모양인가 — 조각 수가 같고, 자리표시자가 아닌 조각은 같고,
    자리표시자인 쿼리 키는 예시에도 실제 값으로 있다."""
    want, got = _segments(pattern), _segments(example)
    if len(want) != len(got):
        return False
    if not all(_SEGMENT.match(w) or w == g for w, g in zip(want, got)):
        return False
    filled = _query(example)
    return all(filled.get(k) and not _SEGMENT.match(filled[k])
               for k in _query_placeholders(pattern))


def _tidy(url_path: str) -> str:
    """S1 이 옮기며 '=' '&' '?' 옆에 넣은 공백을 지운다('chart ={chart}', '& page=')."""
    return re.sub(r"\s*([=&?])\s*", r"\1", (url_path or "").strip())


def several_paths(url_path: str) -> list[str]:
    """경로 칸을 열 수 있는 경로 목록으로 읽는다. 경로 하나 그대로이거나 못 읽으면 빈 목록.

    - 쉼표·'및' 으로 여럿: '/reviews/new, /reviews/new?itemId={itemId}' (0051 B)
    - ';' 뒤는 설명: '/jobs; 예: /jobs?type=...' (0094 A)
    - '=' 옆 공백: '/dashboard?tab={tab}& page= {page}' (0051 A)

    나눈 조각이 모두 '/' 로 시작하는 경로일 때만 읽는다 — '새 작성 /topics/new, 수정 ...'
    같은 문장 안의 경로를 골라 열면 기획서가 그 화면이라고 하지 않은 곳일 수 있다.
    """
    if is_route(url_path or ""):
        return []
    text = _tidy(url_path)
    head = text.split(";", 1)[0].strip()
    if ";" in text and head.startswith("/") and is_route(head):
        return [head]
    parts = [p.strip() for p in re.split(r",\s*(?=/)|\s+및\s+", text)]
    if all(p.startswith("/") and is_route(p) for p in parts):
        return parts
    return []


def _drop_query_placeholders(path: str) -> str:
    """값이 자리표시자인 쿼리 키를 뺀다 — '/search?q={keyword}&sort=new' -> '/search?sort=new'.

    2026-11-04 0051 A: 기획서가 필터용 선택 값을 쿼리 자리표시자로 적었다. 열지 않으면 그
    화면의 케이스가 전부 확인 불가(65건)였고, 글자 그대로 열면 '{keyword}' 를 검색한
    화면이다. 값을 빼면 그 화면의 기본 상태다. 경로 조각의 자리표시자는 빼지 않는다 —
    빼면 다른 화면이다.
    """
    if _segment_placeholder(path) or not _query_placeholders(path):
        return path
    base, _, rest = path.partition("?")
    query, hash_, frag = rest.partition("#")
    kept = [p for p in query.split("&")
            if p and not _SEGMENT.match(p.split("=", 1)[1] if "=" in p else "")]
    return base + (f"?{'&'.join(kept)}" if kept else "") + (hash_ + frag)


def _open_path(path: str, example) -> str:
    if has_placeholder(path) and example and _matches(path, example):
        return example
    return _drop_query_placeholders(path)


def entry_path(spec) -> str:
    """케이스가 이 화면을 열 때 쓸 경로.

    자리표시자가 있고 기획서의 예시 경로가 같은 모양이면 예시 경로. 그 외에는 화면 경로를
    그대로 돌려준다 — 채우지 못한 자리표시자는 실행 단계가 열지 않고 멈춘다
    (playwright_driver 의 navigate). 모양이 다른 예시는 쓰지 않는다: 다른 화면의 값을
    잘못 읽었을 수 있고, 그 값으로 열면 또 엉뚱한 화면이다.

    경로가 여럿 적혔으면 자리표시자 없는 첫 경로, 없으면 예시가 맞는 첫 경로를 쓴다.
    """
    example = getattr(spec, "example_path", None)
    paths = several_paths(spec.url_path)
    if len(paths) > 1:
        for path in paths:
            if not has_placeholder(path):
                return path
        for path in paths:
            if example and _matches(path, example):
                return example
        for path in paths:
            opened = _drop_query_placeholders(path)
            if not has_placeholder(opened):
                return opened
        return spec.url_path
    path = paths[0] if paths else spec.url_path
    return _open_path(path, example)


def _single_arrival(path: str) -> str:
    path = _tidy(path)
    if not has_placeholder(path):
        return path
    if not _segment_placeholder(path):
        # 쿼리에만 자리표시자 — 경로까지 본다. 뒤에 '/' 를 붙이면 /search?q=dog 에 없다.
        return _path_part(path)
    prefix = []
    for seg in _path_part(path).split("/"):
        if _SEGMENT.match(seg):
            break
        prefix.append(seg)
    return "/".join(prefix) + "/"


def arrival_fragment(path: str) -> str:
    """흐름의 도착 확인에 쓸 주소 조각 — 자리표시자 앞까지.

    도착 확인은 주소에 이 글자가 들어 있는지 본다. '/pets/:petId' 를 그대로 찾으면
    /pets/luna 에 제대로 도착해도 실패한다 — 구현이 옳은데 '기획서와 다름' 이 되는 오탐.

    경로가 여럿 적혔으면 모두에 들어 있는 앞부분을 쓴다 — 어느 쪽에 도착해도 맞다.
    """
    paths = several_paths(path)
    if not paths:
        return _single_arrival(path)
    return os.path.commonprefix([_single_arrival(p) for p in paths])
