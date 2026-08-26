"""문서에 적힌 실행 명령이 함정을 되살리지 않는가.

## 왜 이 테스트가 있는가

SUT(`sut/app.py`)는 검증 **대상**이다. 그것을 고치고 서버 재시작을 잊으면, 도구는
옛 코드를 상대로 재고 **그 결과가 도구의 오탐처럼 보인다.**

2026-08-26 에 실제로 겪었다. 기간 역전 규칙을 구현하고 손으로 재 봤더니 `good`
에서 FAIL 이 하나 났다. 도구를 의심하며 케이스 생성과 판정을 훑었는데, 원인은
**8100 에 떠 있던 SUT 가 수정 전 코드를 서빙하고 있던 것**이었다. 테스트는
자체 SUT 를 띄우므로 초록불이었고, 그래서 더 헷갈렸다.

그래서 문서의 기동 명령에 `--reload` 를 붙였다. 문서를 고치는 것만으로는
부족하다 — 새 노트를 쓰면서 옛 명령을 복사하면 함정이 그대로 돌아온다. 여기서
막는다.

## 왜 문서를 검사하는가

이 저장소의 문서는 읽는 글이 아니라 **복사해서 실행하는 것**이다. 티칭 노트마다
'직접 확인' 절이 있고 9월에 팀원들이 그걸 그대로 친다. 실행되는 것이면 낡을 수
있고, 낡는 것이면 검사할 수 있다 (test_fixture_consistency 와 같은 원칙).
"""

from __future__ import annotations

from pathlib import Path

import pytest

#: SUT 기동 명령의 앞부분. 이 문자열이 있는 줄은 전부 검사 대상이다.
SUT_COMMAND = "uvicorn sut.app:app"

#: 반드시 함께 있어야 하는 것. --reload-dir 까지 요구하는 이유: 없으면 저장소
#: 전체(runs/·.venv 포함)를 stat 폴링한다.
REQUIRED = ("--reload", "--reload-dir sut")

#: 검사할 문서·스크립트. .venv 와 산출물은 보지 않는다.
ROOTS = ("README.md", "docs", "fixtures", "scripts", "sut")


def _command_lines() -> list[tuple[Path, int, str]]:
    found: list[tuple[Path, int, str]] = []
    for root in ROOTS:
        path = Path(root)
        paths = [path] if path.is_file() else [
            p for suffix in ("*.md", "*.py", "*.html")
            for p in path.rglob(suffix)
        ]
        for p in paths:
            if "__pycache__" in p.parts:
                continue
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if SUT_COMMAND in line:
                    found.append((p, i, line.strip()))
    return found


def test_기동_명령을_적은_곳이_있다():
    """검사가 아무것도 못 찾고 통과하는 것을 막는다 — 경로 규칙이 깨지면
    이 파일은 조용히 '전부 통과' 가 된다."""
    assert _command_lines(), f"'{SUT_COMMAND}' 를 적은 문서를 하나도 찾지 못했습니다"


@pytest.mark.parametrize("flag", REQUIRED)
def test_모든_기동_명령이_리로드로_띄운다(flag):
    """SUT 를 고치고 재시작을 잊으면 옛 코드를 상대로 재게 된다.

    고치는 방법: 그 줄을 아래로 바꾼다.
        uv run uvicorn sut.app:app --port 8100 --reload --reload-dir sut
    """
    missing = [f"{p}:{i}  {line}" for p, i, line in _command_lines() if flag not in line]
    assert not missing, (
        f"'{flag}' 없이 SUT 를 띄우는 명령이 남아 있습니다:\n  "
        + "\n  ".join(missing)
    )
