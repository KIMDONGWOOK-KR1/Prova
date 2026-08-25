"""로컬 웹 UI 의 HTTP 층.

## 두 단계로 나뉜 이유

    POST /api/plan   브라우저를 열지 않고 '무엇을 테스트할지' 만 정한다
    POST /api/run    사람이 승인한 목록으로 실제 실행한다

자연어 요청은 케이스 선택을 모델에 맡기는 일이고, 그건 이 파이프라인에서
**미탐을 만들 수 있는 유일한 자리**다. 잘못 골라서 결함을 못 본 것과 결함이 없는
것이 리포트에서 똑같이 초록불로 보인다. 그래서 실행 전에 해석 결과를 사람에게
보여주고 승인을 받는다 — UI 는 자연어 층의 편의가 아니라 안전장치다.

## 127.0.0.1 에만 바인딩한다

이 서버는 사용자 기계의 파일(기획서 PDF)을 읽고 사용자 기계의 브라우저를 연다.
바깥에 열면 그 두 가지가 그대로 남의 것이 된다.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from prova.llm.factory import BackendError, make_llm
from prova.pipeline import build_plan, run_pipeline
from prova.server.runner import JobRunner
from prova.theme import TOKENS_CSS

STATIC = Path(__file__).parent / "static"
UPLOADS = Path("uploads")
RUNS = Path("runs")
SPEC_DIRS = [Path("fixtures/specs"), UPLOADS]
FIGMA_DIRS = [Path("fixtures/figma"), UPLOADS]

runner = JobRunner()
app = FastAPI(title="Prova", docs_url=None, redoc_url=None)


# ---------------------------------------------------------------------------
# 경로 안전장치
# ---------------------------------------------------------------------------


def _safe_spec(raw: str) -> Path:
    """기획서 경로가 허용된 디렉터리 안인지 확인한다.

    화면이 보내온 문자열을 그대로 열면 상위 디렉터리를 타고 아무 파일이나 읽을
    수 있다. 로컬 전용이라도 브라우저 안의 다른 페이지가 이 API 를 부를 수
    있으므로 막는다 — localhost 는 같은 기계라는 뜻이지 신뢰할 수 있다는 뜻이 아니다.
    """
    path = Path(raw).resolve()
    allowed = [d.resolve() for d in SPEC_DIRS if d.exists()]
    if not any(path.is_relative_to(root) for root in allowed):
        raise HTTPException(400, f"허용되지 않은 경로입니다: {raw}")
    if not path.exists():
        raise HTTPException(404, f"기획서를 찾을 수 없습니다: {raw}")
    return path


def _safe_figma(raw: str) -> Path:
    """Figma 응답 경로 확인 — _safe_spec 과 같은 안전장치, 디렉터리만 다르다."""
    path = Path(raw).resolve()
    allowed = [d.resolve() for d in FIGMA_DIRS if d.exists()]
    if not any(path.is_relative_to(root) for root in allowed):
        raise HTTPException(400, f"허용되지 않은 경로입니다: {raw}")
    if not path.exists():
        raise HTTPException(404, f"Figma 응답을 찾을 수 없습니다: {raw}")
    return path


def _config() -> dict:
    cfg_path = Path("configs/default.yaml")
    if not cfg_path.exists():
        return {}
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}


# ---------------------------------------------------------------------------
# 요청 본문
# ---------------------------------------------------------------------------


class PlanRequest(BaseModel):
    pdf: str
    url: str
    #: Figma 응답(JSON) 경로. 주면 병합 모드 — 기획서 규칙 + 디자인 문구·흐름,
    #: 어긋나면 계획 화면에 '기획↔디자인 불일치' 로 실린다 (s1_merge).
    figma: Optional[str] = None
    request: Optional[str] = None
    #: 기본값을 두지 않는다 — 요청이 빠뜨리면 조용히 mock 이 되는데, "mock 은
    #: 사용자가 직접 고를 때만" 이 이 도구의 규칙이다. 화면은 항상 보낸다.
    backend: str


class RunRequest(PlanRequest):
    #: 사람이 승인한 case_id. 계획 화면이 돌려주는 값이다.
    case_ids: list[str] = []
    #: 계획 단계에서 모델이 밝힌 근거 (리포트에 그대로 남긴다)
    reason: str = ""


# ---------------------------------------------------------------------------
# 화면
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/static/tokens.css")
def tokens() -> Response:
    """디자인 토큰. 파일이 아니라 theme.py 에서 만들어 준다.

    리포트도 같은 문자열을 인라인하므로, 색을 만드는 곳이 하나로 유지된다.
    """
    return Response(TOKENS_CSS, media_type="text/css")


@app.get("/api/state")
def state() -> dict:
    specs: list[str] = []
    for d in SPEC_DIRS:
        if d.exists():
            specs += sorted(str(p).replace("\\", "/") for p in d.glob("*.pdf"))
    figmas: list[str] = []
    for d in FIGMA_DIRS:
        if d.exists():
            figmas += sorted(str(p).replace("\\", "/") for p in d.glob("*.json")
                             if not p.name.endswith(".golden.json"))
    cfg = _config()
    return {
        "busy": runner.busy,
        "specs": specs,
        "figmas": figmas,
        "backend": cfg.get("llm", {}).get("backend", "mock"),
    }


@app.post("/api/upload")
async def upload(file: UploadFile) -> dict:
    if not (file.filename or "").lower().endswith((".pdf", ".json")):
        raise HTTPException(400, "PDF(기획서) 또는 JSON(Figma 응답)만 올릴 수 있습니다.")
    UPLOADS.mkdir(parents=True, exist_ok=True)
    dest = UPLOADS / Path(file.filename).name
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    return {"path": str(dest).replace("\\", "/")}


# ---------------------------------------------------------------------------
# 1단계 · 계획 — 브라우저를 열지 않는다
# ---------------------------------------------------------------------------


@app.post("/api/plan")
def plan(body: PlanRequest) -> dict:
    pdf = _safe_spec(body.pdf)
    figma = _safe_figma(body.figma) if body.figma else None
    cfg = _config()

    def work(report):
        llm = _backend(body.backend, cfg, pdf, report)
        state, n_all = build_plan(
            pdf_path=str(pdf),
            base_url=body.url,
            llm=llm,
            request=body.request,
            figma_json=str(figma) if figma else None,
            on_progress=report,
        )
        sel = state.selection
        chosen = set(sel.selected)
        return {
            "total_generated": n_all,
            "cases": [
                {
                    "case_id": c.case_id,
                    "screen_id": c.screen_id,
                    "title": c.title,
                    "violates": c.violates,
                    "flow_id": c.flow_id,
                    "selected": c.case_id in chosen,
                }
                # 선택 전 전체 목록을 생성 순서 그대로 쓴다. 제외된 것도
                # 제목·화면·규칙을 갖고 있어야 사람이 되돌릴지 판단할 수 있다.
                for c in state.all_cases
            ],
            "reason": sel.reason,
            "fallback": sel.fallback,
            "warnings": sel.warnings,
            "widened": sel.widened,
            "request": sel.request,
            # 화면별 확인 범위. named 는 요청이 그 화면을 이름으로 지목했는가다 —
            # 지목했는데 일부만 골라졌으면 화면이 그 사실을 크게 보여야 한다.
            "coverage": [c.model_dump() for c in sel.coverage],
            "screens": {s.screen_id: s.screen_name for s in state.doc.screens},
            "coverage_gaps": state.coverage_gaps,
            # 기획↔디자인 불일치 — 사람이 케이스를 승인하는 자리(계획 화면)에서
            # 실행 전에 봐야 한다. 구현을 검증하기 전에 입력끼리 모순이면 그게
            # 먼저다.
            "design_mismatches": state.design_mismatches,
        }

    return _submit("plan", work)


# ---------------------------------------------------------------------------
# 2단계 · 실행 — 승인한 목록으로만 돈다
# ---------------------------------------------------------------------------


@app.post("/api/run")
def run(body: RunRequest) -> dict:
    pdf = _safe_spec(body.pdf)
    figma = _safe_figma(body.figma) if body.figma else None
    cfg = _config()
    if not body.case_ids:
        raise HTTPException(
            400, "실행할 케이스가 없습니다. 0건 실행은 '통과율 100%' 리포트가 됩니다."
        )

    exec_cfg = cfg.get("execution", {})
    ground_cfg = cfg.get("grounding", {})
    agent_cfg = cfg.get("agent", {})

    def work(report):
        llm = _backend(body.backend, cfg, pdf, report)
        run_id = "ui-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        test_report, run_dir = run_pipeline(
            pdf_path=str(pdf),
            base_url=body.url,
            llm=llm,
            figma_json=str(figma) if figma else None,
            run_id=run_id,
            runs_root=RUNS,  # 목록·리포트 조회(RUNS)와 같은 뿌리여야 한다
            case_ids=body.case_ids,
            request=body.request,
            reason=body.reason,
            headless=exec_cfg.get("headless", True),
            viewport=exec_cfg.get("viewport"),
            step_timeout_ms=int(exec_cfg.get("step_timeout_ms", 10000)),
            settle_timeout_ms=int(exec_cfg.get("settle_timeout_ms", 2000)),
            screenshot_every_step=exec_cfg.get("screenshot_every_step", True),
            max_heal=int(agent_cfg.get("max_heal", 2)),
            min_confidence=float(ground_cfg.get("vlm_confidence_threshold", 0.5)),
            on_progress=report,
        )
        return {
            "run_id": run_id,
            "summary": test_report.summary,
            "report_url": f"/runs/{run_id}/report.html",
            "run_dir": str(run_dir).replace("\\", "/"),
        }

    return _submit("run", work)


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------


def _backend(name: str, cfg: dict, pdf: Path, report):
    """백엔드를 만들고 경고를 진행 메시지로 흘린다.

    mock 으로 돌렸다는 사실은 화면에 반드시 보여야 한다 — 아무 추론도 하지 않은
    리포트를 실제 실행 결과로 착각하는 것이 이 도구에서 가장 위험한 실패다.
    """
    try:
        llm, warnings = make_llm(name, cfg, pdf)
    except BackendError as exc:
        raise RuntimeError(str(exc)) from exc
    for w in warnings:
        report(w)
    return llm


def _submit(kind: str, work) -> dict:
    try:
        job = runner.submit(kind, work)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    return {"job_id": job.job_id}


@app.get("/api/job/{job_id}")
def job_status(job_id: str, since: int = 0) -> dict:
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(404, f"작업을 찾을 수 없습니다: {job_id}")
    return job.public(since)


@app.get("/api/runs")
def runs(limit: int = 20) -> dict:
    """지난 실행 목록. runs/ 를 훑어 리포트가 있는 것만 최신순으로 준다.

    report.json 이 없는 디렉터리가 많다 — 디버그·데모 잔여물이다. 그런 것을
    목록에 넣으면 눌렀을 때 404 가 나므로 애초에 거른다.
    """
    root = RUNS
    if not root.exists():
        return {"runs": []}

    found = []
    for d in root.iterdir():
        meta = d / "report.json"
        if not d.is_dir() or not meta.exists():
            continue
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        summary = data.get("summary") or {}
        found.append({
            "run_id": data.get("run_id", d.name),
            "target": data.get("target_url", ""),
            "spec": Path(data.get("spec_source", "")).name,
            "created_at": data.get("created_at", ""),
            "total": summary.get("total", 0),
            "pass": summary.get("pass", 0),
            "fail": summary.get("fail", 0),
            "summary": summary,
        })

    found.sort(key=lambda r: r["created_at"], reverse=True)
    return {"runs": found[:limit]}


@app.get("/api/report/{run_id}")
def report(run_id: str) -> RedirectResponse:
    """실행 디렉터리 안의 report.html 로 넘긴다.

    ## 왜 파일을 직접 돌려주지 않는가

    리포트는 스크린샷과 DOM 스냅샷을 **상대 경로**로 참조한다
    (`login-valid-001/step1.png`). `/api/report/xxx` 에서 그대로 돌려주면 그
    경로가 `/api/login-valid-001/step1.png` 로 풀려 전부 404 가 된다 —
    판정의 근거인 증거 자료가 통째로 사라진다.

    `/runs/<run_id>/report.html` 로 넘기면 상대 경로가 옆 파일을 정확히 가리킨다.
    """
    path = (RUNS / run_id / "report.html").resolve()
    if not path.is_relative_to(RUNS.resolve()) or not path.exists():
        raise HTTPException(404, f"리포트를 찾을 수 없습니다: {run_id}")
    return RedirectResponse(f"/runs/{run_id}/report.html")


# 정적 파일은 마지막에 붙인다. 위의 /static/tokens.css 라우트가 먼저 잡혀야
# 파일이 없는 그 경로가 404 로 떨어지지 않는다.
app.mount("/static", StaticFiles(directory=STATIC), name="static")

# 실행 산출물. 리포트가 스크린샷·DOM 스냅샷을 상대 경로로 참조하므로 디렉터리를
# 통째로 서빙해야 증거 자료가 살아 있다. StaticFiles 가 경로 탈출을 막는다.
RUNS.mkdir(parents=True, exist_ok=True)
app.mount("/runs", StaticFiles(directory=RUNS), name="runs")
