"""Figma API 응답을 받아 다듬어 저장한다.

사용법:
    uv run python scripts/fetch_figma.py fixtures/figma/login_signup.json

.env 의 FIGMA_TOKEN·FIGMA_FILE_KEY 를 쓴다. 저장 전에 trim_figma_response 로
필요한 키만 남긴다 — 다듬기를 손으로 하면 '실물 API 응답' 이라는 증거가
사라지므로 반드시 이 스크립트로 한다. 토큰은 저장물에 남지 않는다(응답 본문에
없고, 이 스크립트도 쓰지 않는다).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from prova.s1_figma.figma_parser import trim_figma_response  # noqa: E402


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "fixtures/figma/login_signup.json")
    token = os.environ.get("FIGMA_TOKEN", "")
    file_key = os.environ.get("FIGMA_FILE_KEY", "")
    if not token or not file_key:
        raise SystemExit(".env 의 FIGMA_TOKEN·FIGMA_FILE_KEY 가 필요합니다 — "
                         "set -a && . ./.env && set +a 후 다시 실행하세요.")
    resp = requests.get(
        f"https://api.figma.com/v1/files/{file_key}",
        headers={"X-Figma-Token": token}, timeout=60)
    resp.raise_for_status()
    trimmed = trim_figma_response(resp.json())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(trimmed, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"{out} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
