"""실행 전 빌드 도장 확인 — 낡은 대상을 상대로 재지 않는다.

떠 있는 대상이 자기 소스보다 낡았으면, 거기서 나온 FAIL 은 구현의 결함이
아니라 **잰 대상이 옛것이라서** 난 것이다. 리포트만 보면 둘은 구별되지
않는다. 그래서 실행 **전에** 한 번 묻는다.

묻기만 한다. 판단은 대상이 한다 — prova 는 URL 만 알고 대상의 소스 경로를
모르므로, '내 소스가 나보다 새것인가' 는 그 프로세스만 답할 수 있다
(`sut/app.py` 의 `/__build__` 참고).

도장이 없으면 아무 말도 하지 않는다. prova 의 대상은 임의의 웹앱이고 실물
대상에 이 엔드포인트가 없는 것이 정상이다 — 없다고 매번 경고하면 그 경고는
곧 아무도 읽지 않게 된다. '도장이 없다' 와 '도장이 어긋났다' 는 다른 사실이다.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urlsplit, urlunsplit

#: (URL) -> (상태 코드, 본문 dict 또는 None). 닿지 않으면 OSError 를 낸다.
Fetch = Callable[[str], tuple[int, Optional[dict]]]

_PATH = "/__build__"
_TIMEOUT = 3.0


@dataclass(frozen=True)
class BuildCheck:
    """확인 결과.

    `state` 는 넷 중 하나다 — match(일치) / stale(어긋남) / absent(도장 없음) /
    unreachable(닿지 않음). `blocks` 는 어긋남에서만 참이다.
    """

    state: str
    message: str
    stamp: str = ""
    current: str = ""

    @property
    def blocks(self) -> bool:
        return self.state == "stale"


def build_url(base_url: str) -> str:
    """대상 URL 에서 도장 주소를 만든다.

    `--url` 은 보통 변형 경로까지 온다(`http://localhost:8100/good`). 도장은
    앱 루트에 있으므로 경로와 질의문자열을 떼어낸다.
    """
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, _PATH, "", ""))


def _http_get(url: str) -> tuple[int, Optional[dict]]:
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (json.JSONDecodeError, UnicodeDecodeError):
        # 200 인데 JSON 이 아니다 — 도장이 아니라 남의 라우트다.
        return 200, None


def check_sut_build(base_url: str, *, fetch: Fetch = _http_get) -> BuildCheck:
    url = build_url(base_url)
    try:
        status, body = fetch(url)
    except OSError as exc:
        # 대상이 죽었으면 파이프라인이 제 이름으로 실패한다. 여기서 가로채면
        # 원인이 '빌드 확인 실패' 로 잘못 적힌다.
        return BuildCheck("unreachable", f"SUT 빌드 확인: 닿지 않음 ({exc})")

    if status != 200 or not isinstance(body, dict) or "stale" not in body:
        # 모르는 응답으로 '최신이다' 라고 말하지 않는다. 도장이 아니면 도장이
        # 없는 것과 같다.
        return BuildCheck("absent", "SUT 빌드 확인: 해당 없음")

    stamp = str(body.get("stamp", ""))
    current = str(body.get("current", ""))
    if body["stale"]:
        return BuildCheck(
            "stale",
            "SUT 가 자기 소스보다 낡았습니다 — 그 프로세스를 재시작하세요.\n"
            f"  임포트 시점 {stamp[:12]} · 지금 디스크 {current[:12]}\n"
            "  --reload 로 띄웠어도 감시자 프로세스가 죽으면 일꾼만 남아\n"
            "  옛 코드를 계속 서빙합니다(포트는 열려 있습니다).",
            stamp, current,
        )
    return BuildCheck("match", "SUT 빌드 확인: 일치", stamp, current)
