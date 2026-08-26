"""계획(S1~S2 산출물) 저장·복원 — 두 실물 모델을 한 실행으로 관통시키는 다리.

## 왜 있는가

한 GPU 는 7B(추출)와 VL(탐지)을 동시에 싣지 못한다. 그래서 실행을 둘로 자른다:
7B 로 S1~S2 를 돌려 계획을 저장하고(`--plan-only`), 서버를 교체한 뒤 저장된
계획으로 S3~S6 을 이어 돈다(`--resume`). 이 파일은 그 사이를 건너는 plan.json
하나를 책임진다.

## 계약

- **저장·복원이 산출물을 바꾸지 않는다.** 승인한 계획과 다른 것이 돌면 안 된다.
- **선택된 케이스 본문을 두 번 저장하지 않는다.** all_cases(전체 본문) +
  selected_case_ids(목록)만 담고, 복원은 항상 all_cases 에서 id 로 골라낸다 —
  두 사본이 어긋날 자리를 만들지 않기 위해서다.
- **재개는 pdf 를 다시 읽지 않는다.** 대신 계획 시점의 sha256 을 저장해 두고,
  파일이 그 사이 바뀌었으면 경고를 리포트까지 실어 보낸다(plan_warnings).
  경고이지 오류가 아니다 — 판정은 계획 시점 문서 기준으로 성립한다.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from prova.models import CaseSelection, SpecDocument, TestCase

#: plan.json 의 스키마 버전. 필드가 바뀌면 올린다 — 옛 계획을 새 코드로 조용히
#: 읽으면 빠진 필드가 기본값으로 채워져 "계획과 다른 실행" 이 된다.
PLAN_SCHEMA_VERSION = 1

#: CLI 와 서버가 같은 이름을 봐야 한다.
PLAN_FILENAME = "plan.json"


class PlanError(Exception):
    """plan.json 을 읽을 수 없는 상태 — 부재·버전 불일치·손상."""


class SavedPlan(BaseModel):
    """plan.json 의 전체 내용.

    입력 기록(pdf·figma·URL)과 산출물(doc·케이스·선택)을 함께 담는다. 입력
    기록은 재개 시 다시 묻지 않기 위해서이고, 산출물은 LLM 없이 S3~S6 을
    돌리기 위해서다.
    """

    schema_version: int = PLAN_SCHEMA_VERSION
    created_at: str = ""
    #: 추출을 수행한 LLM 백엔드 이름. 리포트가 "누가 추출했는가" 를 말할 근거.
    backend: str = ""

    # 입력 기록
    pdf_path: str = ""
    pdf_sha256: str = ""
    figma_json: Optional[str] = None
    figma_sha256: str = ""
    screen_urls: dict[str, str] = Field(default_factory=dict)
    base_url: str = ""
    only: Optional[str] = None

    # 산출물
    n_all: int = 0
    doc: SpecDocument
    all_cases: list[TestCase] = Field(default_factory=list)
    selected_case_ids: list[str] = Field(default_factory=list)
    selection: Optional[CaseSelection] = None
    coverage_gaps: list[str] = Field(default_factory=list)
    design_mismatches: list[str] = Field(default_factory=list)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_plan(state, *, n_all: int, only: Optional[str]) -> Path:
    """build_plan 을 마친 상태를 run_dir/plan.json 으로 저장한다."""
    pdf = Path(state.pdf_path) if state.pdf_path else None
    figma = Path(state.figma_json) if state.figma_json else None
    plan = SavedPlan(
        created_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        backend=getattr(state.llm, "name", "") if state.llm else "",
        pdf_path=state.pdf_path,
        pdf_sha256=_sha256(pdf) if pdf and pdf.exists() else "",
        figma_json=state.figma_json,
        figma_sha256=_sha256(figma) if figma and figma.exists() else "",
        screen_urls=dict(state.screen_urls),
        base_url=state.base_url,
        only=only,
        n_all=n_all,
        doc=state.doc,
        all_cases=state.all_cases,
        selected_case_ids=[c.case_id for c in state.cases],
        selection=state.selection,
        coverage_gaps=list(state.coverage_gaps),
        design_mismatches=list(state.design_mismatches),
    )
    state.run_dir.mkdir(parents=True, exist_ok=True)
    path = state.run_dir / PLAN_FILENAME
    path.write_text(
        json.dumps(plan.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_plan(run_dir: Path) -> SavedPlan:
    """run_dir/plan.json 을 읽는다. 못 읽으면 PlanError — 조용한 폴백은 없다."""
    path = Path(run_dir) / PLAN_FILENAME
    if not path.exists():
        raise PlanError(
            f"{path} 이 없습니다 — 먼저 `prova run --plan-only` 로 계획을 저장하세요."
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PlanError(f"{path} 을 JSON 으로 읽을 수 없습니다: {exc}") from exc
    version = raw.get("schema_version")
    if version != PLAN_SCHEMA_VERSION:
        raise PlanError(
            f"plan.json 버전이 다릅니다 (파일 {version}, 지원 {PLAN_SCHEMA_VERSION}) "
            "— 같은 버전의 prova 로 계획을 다시 저장하세요."
        )
    return SavedPlan.model_validate(raw)


def plan_warnings(plan: SavedPlan) -> list[str]:
    """계획과 지금 사이에 달라진 것을 찾는다.

    재개는 pdf 를 다시 읽지 않으므로, 파일이 바뀌었어도 실행은 계획 시점 문서
    기준으로 성립한다. 그 사실을 사람이 알아야 하므로 경고로 만들고, 호출자가
    리포트까지 실어 보낸다.
    """
    warnings: list[str] = []
    # 조사가 라벨마다 다르므로(문서'가'·응답'이') 주격·목적격을 함께 적어 둔다.
    for subject, obj, path_str, expected in (
        ("설계 문서가", "설계 문서를", plan.pdf_path, plan.pdf_sha256),
        ("Figma 응답이", "Figma 응답을", plan.figma_json, plan.figma_sha256),
    ):
        if not path_str or not expected:
            continue
        path = Path(path_str)
        if not path.exists():
            warnings.append(
                f"{obj} 찾을 수 없습니다: {path_str} — "
                "판정은 계획 시점 입력 기준입니다."
            )
        elif _sha256(path) != expected:
            warnings.append(
                f"{subject} 계획 이후 바뀌었습니다: {path_str} — 재개는 입력을 "
                "다시 읽지 않으므로 판정은 계획 시점 입력 기준입니다."
            )
    return warnings
