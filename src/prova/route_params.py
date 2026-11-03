"""화면 경로의 자리표시자(`/pets/:petId`)를 다룬다.

## 왜 필요한가 (2026-11-03)

상세 화면처럼 경로에 값이 들어가는 화면은 기획서에 `/pets/:petId` 로 적힌다. 그 글자를
그대로 열면 SPA 는 200 으로 '없는 항목' 화면을 그리고, 그 화면에서 찾는 요소는 전부
'못 찾음' 이 된다 — 라벨이 틀린 것처럼 보이지만 실제로는 엉뚱한 화면에 있다.

기획서가 `예시 경로 | /pets/luna` 를 적어 두었으면 그 값으로 연다. 없으면 열지 않는다.
"""

from __future__ import annotations

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
    return bool(target) and not re.search(r"[\s,]", target)


def has_placeholder(path: str) -> bool:
    """경로에 값을 채워야 하는 조각이 있는가."""
    return any(_SEGMENT.match(seg) for seg in _segments(path))


def _matches(pattern: str, example: str) -> bool:
    """예시 경로가 패턴과 같은 모양인가 — 조각 수가 같고, 자리표시자가 아닌 조각은 같다."""
    want, got = _segments(pattern), _segments(example)
    if len(want) != len(got):
        return False
    return all(_SEGMENT.match(w) or w == g for w, g in zip(want, got))


def entry_path(spec) -> str:
    """케이스가 이 화면을 열 때 쓸 경로.

    자리표시자가 있고 기획서의 예시 경로가 같은 모양이면 예시 경로. 그 외에는 화면 경로를
    그대로 돌려준다 — 채우지 못한 자리표시자는 실행 단계가 열지 않고 멈춘다
    (playwright_driver 의 navigate). 모양이 다른 예시는 쓰지 않는다: 다른 화면의 값을
    잘못 읽었을 수 있고, 그 값으로 열면 또 엉뚱한 화면이다.
    """
    example = getattr(spec, "example_path", None)
    if has_placeholder(spec.url_path) and example and _matches(spec.url_path, example):
        return example
    return spec.url_path


def arrival_fragment(path: str) -> str:
    """흐름의 도착 확인에 쓸 주소 조각 — 자리표시자 앞까지.

    도착 확인은 주소에 이 글자가 들어 있는지 본다. '/pets/:petId' 를 그대로 찾으면
    /pets/luna 에 제대로 도착해도 실패한다 — 구현이 옳은데 '기획서와 다름' 이 되는 오탐.
    """
    if not has_placeholder(path):
        return path
    prefix = []
    for seg in _path_part(path).split("/"):
        if _SEGMENT.match(seg):
            break
        prefix.append(seg)
    return "/".join(prefix) + "/"
