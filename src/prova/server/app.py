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

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from prova.history import list_runs, load_reports
from prova.llm.factory import BackendError, make_llm
from prova.models import SpecDocument
from prova.nodes import AgentState, extract_spec, finish_titles
from prova.spec_edits import diff_docs
from prova.s2_case_generator.rule_expander import RULE_LABELS
from prova.wording import (
    expectation_sentence, reproduction_lines, rule_subject, source_sentence,
)
from prova.pipeline import build_plan, configured_workers, execution_options, run_pipeline
from prova.sut_build import check_sut_build
from prova.server.runner import JobRunner
from prova.theme import TOKENS_CSS
from prova.vlm.base import VLMError
from prova.llm.vllm_backend import DEFAULT_BASE_URL, DEFAULT_MODEL
from prova.vlm.qwen_vl import QwenVLClient

STATIC = Path(__file__).parent / "static"
UPLOADS = Path("uploads")
RUNS = Path("runs")
EXAMPLE_SPECS = Path("fixtures/specs")
EXAMPLE_FIGMAS = Path("fixtures/figma")
#: 프로젝트 이름에 쓸 수 없는 글자 — 이름이 폴더 이름이 되므로 경로 구분자와 Windows 금지 문자를 막는다.
PROJECT_FORBIDDEN = '/\\:*?"<>|'
PROJECT_MAX = 60


def _spec_dirs() -> list[Path]:
    # UPLOADS 를 부를 때 읽는다 — 테스트가 옮긴 자리를 따라가야 한다.
    return [EXAMPLE_SPECS, UPLOADS]


def _figma_dirs() -> list[Path]:
    return [EXAMPLE_FIGMAS, UPLOADS]

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
    allowed = [d.resolve() for d in _spec_dirs() if d.exists()]
    if not any(path.is_relative_to(root) for root in allowed):
        raise HTTPException(400, f"허용되지 않은 경로입니다: {raw}")
    if not path.exists():
        raise HTTPException(404, f"기획서를 찾을 수 없습니다: {raw}")
    return path


def _safe_figma(raw: str) -> Path:
    """Figma 응답 경로 확인 — _safe_spec 과 같은 안전장치, 디렉터리만 다르다."""
    path = Path(raw).resolve()
    allowed = [d.resolve() for d in _figma_dirs() if d.exists()]
    if not any(path.is_relative_to(root) for root in allowed):
        raise HTTPException(400, f"허용되지 않은 경로입니다: {raw}")
    if not path.exists():
        raise HTTPException(404, f"Figma 응답을 찾을 수 없습니다: {raw}")
    return path


def _project_name(raw: str) -> str:
    """프로젝트 이름을 확인한다. 이름이 곧 `uploads/` 아래 폴더 이름이다.

    화면이 보낸 글자를 그대로 폴더로 쓰면 `../` 로 올린 파일이 아무 데나 떨어진다
    (_safe_spec 과 같은 이유). 빈 이름은 '프로젝트 없음' 이다.
    """
    name = raw.strip()
    if not name:
        return ""
    bad = (len(name) > PROJECT_MAX or name.startswith(".") or name.endswith(".")
           or any(ch in PROJECT_FORBIDDEN or ord(ch) < 32 for ch in name))
    if bad:
        raise HTTPException(
            400, f"프로젝트 이름으로 쓸 수 없습니다: {raw!r} — {PROJECT_MAX}자 이하로, "
                 f"{' '.join(PROJECT_FORBIDDEN)} 없이, 점으로 시작하거나 끝나지 않게 적어 주세요.")
    return name


def _rel(path: Path) -> str:
    return str(path).replace("\\", "/")


def _spec_groups() -> list[dict]:
    """기획서를 묶음별로 — 프로젝트 폴더들, 프로젝트 없이 올린 것, 저장소의 예시 순.

    project 가 None 인 묶음은 예시 기획서다(사용자가 만든 것이 아니다). "" 는 프로젝트
    없이 올린 것.
    """
    groups: list[dict] = []
    if UPLOADS.exists():
        for d in sorted(p for p in UPLOADS.iterdir() if p.is_dir()):
            specs = sorted(_rel(p) for p in d.glob("*.pdf"))
            if specs:
                groups.append({"project": d.name, "label": d.name, "specs": specs})
        loose = sorted(_rel(p) for p in UPLOADS.glob("*.pdf"))
        if loose:
            groups.append({"project": "", "label": "프로젝트 없이 올린 기획서", "specs": loose})
    if EXAMPLE_SPECS.exists():
        groups.append({"project": None, "label": "예시 기획서",
                       "specs": sorted(_rel(p) for p in EXAMPLE_SPECS.glob("*.pdf"))})
    return groups


def _project_names(groups: list[dict]) -> list[str]:
    """고를 수 있는 프로젝트 이름 — 기획서를 올린 폴더와, 실행할 때 적었던 이름."""
    names = {g["project"] for g in groups if g["project"]}
    names |= {(r.get("summary") or {}).get("project", "") for r in load_reports(RUNS)}
    return sorted(n for n in names if n)


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
    #: 사람이 계획 화면에서 고친 추출 결과(SpecDocument). 주면 기획서를 다시 읽지 않고 이
    #: 문서로 케이스를 만든다. 원래 추출과 다른 점은 리포트에 남는다 (prova.spec_edits).
    doc: Optional[dict] = None


class RunRequest(PlanRequest):
    #: 사람이 승인한 case_id. 계획 화면이 돌려주는 값이다.
    case_ids: list[str] = []
    #: 계획 단계에서 모델이 밝힌 근거 (리포트에 그대로 남긴다)
    reason: str = ""
    #: 2차 경로(화면 이미지로 찾기). 기본은 끈다 — 좌표를 누르는 경로라 틀리면
    #: 그 뒤 판정이 전부 거짓이 된다. 켜는 것은 사람이 고르고, 리포트가 남긴다.
    vlm: bool = False
    #: 쓰기 요청(POST·PUT·PATCH·DELETE)을 막고 실행한다 (prova.dry_run, CLI --dry-run).
    #: 기본은 끈다 — 막으면 제출 케이스가 '확인 불가' 가 된다. 켰는지는 리포트가 남긴다.
    dry_run: bool = False
    #: 실행을 묶을 이름. 비우면 기획서와 대상 URL 로 묶는다 (prova.history)
    project: str = ""


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
    groups = _spec_groups()
    # 예전 순서(예시 → 올린 것)를 지킨다. 프로젝트 폴더 안의 것도 빠짐없이 넣는다.
    specs = [p for g in reversed(groups) for p in g["specs"]]
    figmas: list[str] = []
    for d in _figma_dirs():
        if d.exists():
            figmas += sorted(str(p).replace("\\", "/") for p in d.glob("*.json")
                             if not p.name.endswith(".golden.json"))
    cfg = _config()
    return {
        "busy": runner.busy,
        "specs": specs,
        "spec_groups": groups,
        "projects": _project_names(groups),
        "figmas": figmas,
        "backend": cfg.get("llm", {}).get("backend", "mock"),
    }


@app.post("/api/upload")
async def upload(file: UploadFile, project: str = Form("")) -> dict:
    """파일을 올린다. 프로젝트를 적었으면 기획서(PDF)는 그 프로젝트 폴더에 넣는다.

    Figma 응답(JSON)은 프로젝트와 상관없이 한곳에 둔다 — 기획서에 딸린 선택 자료라
    묶음을 따로 만들지 않는다.
    """
    filename = (file.filename or "").lower()
    if not filename.endswith((".pdf", ".json")):
        raise HTTPException(400, "PDF(기획서) 또는 JSON(Figma 응답)만 올릴 수 있습니다.")
    name = _project_name(project) if filename.endswith(".pdf") else ""
    folder = UPLOADS / name if name else UPLOADS
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / Path(file.filename).name
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    return {"path": _rel(dest), "project": name}


# ---------------------------------------------------------------------------
# 1단계 · 계획 — 브라우저를 열지 않는다
# ---------------------------------------------------------------------------


@app.post("/api/plan")
def plan(body: PlanRequest) -> dict:
    pdf = _safe_spec(body.pdf)
    figma = _safe_figma(body.figma) if body.figma else None
    cfg = _config()

    edited = _edited_doc(body)

    def work(report):
        llm = _backend(body.backend, cfg, pdf, report)
        edits = _spec_edits(edited, pdf, figma, llm)
        state, n_all = build_plan(
            pdf_path=str(pdf),
            base_url=body.url,
            llm=llm,
            request=body.request,
            figma_json=str(figma) if figma else None,
            on_progress=report,
            doc=edited,
        )
        finish_titles(state)  # 사람이 승인하는 자리라 다듬은 제목을 보여 준다
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
                    # 사람이 읽는 이름 — 규칙·요소를 기획서의 말로 (화면이 식별자 대신 쓴다)
                    "rule_label": (RULE_LABELS.get(c.violates, c.violates)
                                   if c.violates else None),
                    "target_label": rule_subject(c.target_label, c.target_element) or None,
                    # 무슨 값으로 무엇을 기대하는지. 제목만 보고 승인하지 않게 한다.
                    "steps": reproduction_lines(c.steps, c.setup_steps),
                    "expected": expectation_sentence(c.expected),
                    "sources": [source_sentence(s) for s in c.spec_sources],
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
            # 대상 URL 에 화면 경로가 붙어 있어 뗐다면 그 사실 (pipeline.strip_screen_path)
            "url_note": state.url_note,
            # 기획서에서 읽은 내용 — 사람이 보고 고치는 자리 (prova.spec_edits).
            "doc": state.doc.model_dump(mode="json"),
            "spec_edits": edits,
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

    # 낡은 대상을 상대로 시작하지 않는다. 여기서 막는 이유는 CLI 와 같고
    # (prova.sut_build 모듈 설명), 이 화면이 9월에 팀원들이 쓰는 입구라
    # 가드가 CLI 에만 있으면 정작 필요한 곳에 없는 것과 같다.
    # 작업을 띄운 뒤가 아니라 요청 처리 중에 확인한다 — 진행 로그에 묻히지 않고
    # 화면이 곧바로 이유를 보여줘야 한다.
    build = check_sut_build(body.url)
    if build.blocks:
        raise HTTPException(409, build.message)
    # 같은 이유로 작업을 띄우기 전에 확인한다. 켰는데 서버가 없으면 locate 마다
    # 실패가 탐지 실패로 되돌아가, '보정을 켠' 실행이 조용히 1차 경로만 돈다.
    vlm = _make_vlm(cfg) if body.vlm else None
    edited = _edited_doc(body)

    def work(report):
        llm = _backend(body.backend, cfg, pdf, report)
        edits = _spec_edits(edited, pdf, figma, llm)
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
            vlm=vlm,
            **execution_options(cfg),
            sut_build=build.state,
            project=body.project.strip(),
            workers=configured_workers(cfg),
            on_progress=report,
            doc=edited,
            spec_edits=edits,
            dry_run=body.dry_run,
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


def _edited_doc(body: PlanRequest) -> Optional[SpecDocument]:
    """화면이 보낸 고친 추출 결과를 검사한다. 모양이 틀리면 작업을 띄우기 전에 400."""
    if body.doc is None:
        return None
    try:
        return SpecDocument.model_validate(body.doc)
    except ValueError as exc:
        raise HTTPException(400, f"고친 추출 결과를 읽을 수 없습니다: {exc}") from exc


def _spec_edits(edited: Optional[SpecDocument], pdf: Path, figma: Optional[Path],
                llm) -> list[str]:
    """원래 추출과 비교한 수정 목록. 원래 추출은 다시 읽어 얻는다 — 같은 모델 응답이
    저장돼 있어(llm/cache.py) 모델을 다시 부르지 않는다. 화면이 보낸 '원본' 은 믿지 않는다."""
    if edited is None:
        return []
    original = extract_spec(AgentState(
        pdf_path=str(pdf), base_url="", run_id="edits", run_dir=RUNS / "edits",
        llm=llm, figma_json=str(figma) if figma else None)).doc
    return diff_docs(original, edited)


def _backend(name: str, cfg: dict, pdf: Path, report):
    """백엔드를 만들고 경고를 진행 메시지로 흘린다.

    mock 으로 돌렸다는 사실은 화면에 반드시 보여야 한다 — 아무 추론도 하지 않은
    리포트를 실제 실행 결과로 착각하는 것이 이 도구에서 가장 위험한 실패다.
    """
    try:
        llm, warnings = make_llm(name, cfg, pdf, cache=True)
    except BackendError as exc:
        raise RuntimeError(str(exc)) from exc
    for w in warnings:
        report(w)
    return llm


def _make_vlm(cfg: dict):
    """2차 경로 클라이언트를 만들고 연결을 확인한다 (CLI `_make_vlm` 과 같은 규칙).

    주소와 모델은 설정의 llm 을 쓴다 — 추출과 요소 찾기를 같은 서버·같은 모델이
    맡는다(Qwen3.5-4B, 2026-09-28). 따로 받지 않으니 둘이 어긋날 수도 없다.
    """
    llm_cfg = cfg.get("llm", {})
    try:
        client = QwenVLClient(base_url=llm_cfg.get("base_url", DEFAULT_BASE_URL),
                              model=llm_cfg.get("model", DEFAULT_MODEL))
        client.health()
    except (ValueError, VLMError) as exc:
        raise HTTPException(409, f"2차 경로를 켤 수 없습니다 — {exc}")
    return client


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
    return {"runs": list_runs(RUNS, limit)}


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
