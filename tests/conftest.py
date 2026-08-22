"""테스트 공용 픽스처.

## SUT 를 테스트가 직접 띄운다

외부에서 띄워 둔 서버에 의존하면 테스트가 환경에 따라 통과·실패를 오간다.
uvicorn 을 스레드로 올려 테스트가 수명을 소유한다.

세션 범위로 한 번만 띄우는 이유: 기동 비용을 화면 수만큼 곱하지 않기 위해서다.

다만 검증 대상이 **상태를 아주 안 갖는 것은 아니다** — 회원가입이 프로세스 전역
`sut.app.REGISTERED` 에 계정을 쓴다(2026-08-20 이후). e2e 는 같은 프로세스의
스레드 서버를 치고 SUT 단위 테스트는 모듈을 직접 import 하므로 전부 같은 dict 다.
그래서 아래 autouse 픽스처가 테스트마다 그 표를 스냅샷/복원한다. 이게 없으면
`REGISTERED` 를 읽는 판정이 하나만 늘어도 실행 순서에 따라 결과가 달라진다.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn


@pytest.fixture(autouse=True)
def _isolate_sut_state():
    """SUT 의 등록 계정 표를 테스트 전후로 되돌린다 (모듈 docstring 참고)."""
    import copy

    from sut import app as sut_app

    snapshot = copy.deepcopy(sut_app.REGISTERED)
    yield
    sut_app.REGISTERED.clear()
    sut_app.REGISTERED.update(snapshot)


def _free_port() -> int:
    """비어 있는 포트를 OS 에게 받아 온다.

    고정 포트를 쓰면 다른 프로세스(개발 중 띄워 둔 SUT 등)와 충돌해 테스트가
    엉뚱한 서버를 검증한다.
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def sut_base() -> str:
    """SUT 를 백그라운드 스레드로 띄우고 base URL(good/bad 변형 제외)을 돌려준다."""
    from sut.app import app

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.fail("SUT 서버가 기동하지 않았습니다")

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=5)


def load_script(path: str):
    """scripts/ 의 파일을 모듈로 불러온다. 테스트가 스크립트의 함수를 직접 쓸 때.

    `scripts/` 는 패키지가 아니다(`__init__.py` 가 없다). 측정 스크립트를 패키지로
    만들지 않는 이유: `prova` 는 도구이고 스크립트는 그 도구로 재는 절차라서, 같은
    import 경로에 두면 무엇이 제품이고 무엇이 측정인지 흐려진다.

    **`sys.modules` 에 먼저 등록하는 것이 중요하다.** 등록하지 않으면 스크립트 안의
    `@dataclass` 가 `from __future__ import annotations` 와 만나 터진다 —
    dataclasses 가 타입 문자열을 풀려고 `sys.modules[cls.__module__]` 를 찾는데
    그것이 None 이기 때문이다. 원인이 데이터셋이나 채점과 무관한 곳에서 나오므로
    처음 만나면 시간을 크게 잡아먹는다.
    """
    import importlib.util
    import sys

    name = f"_script_{Path(path).stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
