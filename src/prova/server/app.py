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
from prova.pipeline import build_plan, execution_options, run_pipeline
from prova.sut_build import check_sut_build
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
    #: 2차 경로(VLM) 서버 주소. CLI 의 `--vlm` 과 같다. 비우면 1차 경로만 쓴다.
    #:
    #: 계획 단계(PlanRequest)에는 두지 않는다 — 계획은 브라우저를 열지 않으므로
    #: 요소를 찾을 일이 없다. 읽지 않는 값을 받으면 화면이 거짓 약속을 한다.
    vlm: Optional[str] = None
    #: 2차 경로 모델 이름. 비우면 QwenVLClient 의 기본값.
    vlm_model: Optional[str] = None


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
            # 대상 URL 에 화면 경로가 붙어 있어 뗐다면 그 사실 (pipeline.strip_screen_path)
            "url_note": state.url_note,
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

    def work(report):
        llm = _backend(body.backend, cfg, pdf, report)
        # 2차 경로는 백엔드보다 **뒤에** 만든다. 둘 다 GPU 서버를 쓰는데, 먼저
        # 실패하는 쪽이 사람이 먼저 고칠 쪽이라야 한다 — 추출이 안 되면 2차
        # 경로가 붙어도 실행할 케이스가 없다.
        vlm = _vlm(body.vlm, body.vlm_model, report)
        run_id = "ui-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        test_report, run_dir = run_pipeline(
            pdf_path=str(pdf),
            base_url=body.url,
            llm=llm,
            vlm=vlm,
            figma_json=str(figma) if figma else None,
            run_id=run_id,
            runs_root=RUNS,  # 목록·리포트 조회(RUNS)와 같은 뿌리여야 한다
            case_ids=body.case_ids,
            request=body.request,
            reason=body.reason,
            **execution_options(cfg),
            sut_build=build.state,
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

#: GPU 서버가 없을 때 다음에 할 수 있는 것. 연결 실패 사유 뒤에 붙인다.
#:
#: 무엇을 고르는 것인지 함께 적는다 — 연습용은 저장된 정답을 쓰므로 배관은
#: 증명해도 추출 정확도는 증명하지 못한다. 그 사실을 빼고 권하면, 연습용으로
#: 낸 숫자가 실측으로 보고되는 길을 화면이 열어 주는 셈이다.
_NO_GPU_HINT = (
    "GPU 서버가 없다면 'LLM 백엔드' 를 '연습용 — 저장된 정답 사용' 으로 바꿔 "
    "지금 바로 돌려볼 수 있습니다. 다만 연습용은 픽스처 기획서의 저장된 정답을 "
    "쓰므로, 파이프라인이 끝까지 도는 것은 보여 주지만 기획서 추출이 정확한지는 "
    "증명하지 못합니다 — 연습용으로 나온 수치를 실측으로 보고하지 마세요."
)


def _vlm(url: Optional[str], model: Optional[str], report):
    """2차 경로(VLM) 클라이언트를 만들고 연결을 확인한다. 비어 있으면 None.

    ## 연결이 안 되면 실행하지 않는다

    조용히 보정 없이 진행하면 **'2차 경로를 켰다' 고 믿는 실행이 실제로는 그냥
    1차 경로**가 된다. CLI 가 같은 이유로 여기서 멈춘다(`cli._make_vlm`).
    자가치유가 동작하는지 보려고 켠 실행이 말없이 안 켜진 채 끝나면, 그 결과를
    보고 "2차 경로가 필요 없다" 는 반대 결론까지 낼 수 있다.

    ## 켰다는 사실을 진행 로그에 남긴다

    리포트는 보정된 케이스를 표시하지만, 보정이 **한 건도 일어나지 않은** 실행은
    2차 경로를 켠 것과 끈 것이 리포트에서 똑같아 보인다. 무엇을 켜고 돌렸는지는
    판정의 전제이므로 화면이 말해야 한다 (mock 경고와 같은 판단).
    """
    if not url:
        return None
    from prova.vlm.base import VLMError
    from prova.vlm.qwen_vl import QwenVLClient

    client = QwenVLClient(base_url=url, model=model) if model else QwenVLClient(base_url=url)
    try:
        client.health()
    except VLMError as exc:
        raise RuntimeError(
            f"2차 경로(VLM) 서버에 연결할 수 없습니다: {url}\n"
            f"  원인: {exc}\n\n"
            "주소를 비우면 1차 경로(selector)만으로 실행합니다. 1차가 요소를 "
            "찾지 못한 케이스는 탐지 실패로 남고, 없는 결함으로 보고하지 않습니다."
        ) from exc
    report(f"2차 경로: {client.name} @ {url} ({client.model})")
    return client


def _backend(name: str, cfg: dict, pdf: Path, report):
    """백엔드를 만들고 경고를 진행 메시지로 흘린다.

    mock 으로 돌렸다는 사실은 화면에 반드시 보여야 한다 — 아무 추론도 하지 않은
    리포트를 실제 실행 결과로 착각하는 것이 이 도구에서 가장 위험한 실패다.
    """
    try:
        llm, warnings = make_llm(name, cfg, pdf)
    except BackendError as exc:
        # 연결 실패 사유는 factory 가 정확히 적어 준다(터널·vllm serve). 그런데
        # 그것만 보면 GPU 가 없는 사람은 **여기서 막힌다** — 바로 위 드롭다운에
        # 답이 있는데 화면이 그 얘기를 하지 않는다. 다음에 할 수 있는 것을 알려
        # 준다. mock 으로 대신 돌려 주지는 않는다(설계: 조용히 폴백하지 않는다) —
        # 고르는 것은 사람이고, 무엇을 고르는 것인지도 함께 적는다.
        raise RuntimeError(f"{exc}\n\n{_NO_GPU_HINT}" if name == "vllm" else str(exc)
                           ) from exc
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


class _NoStoreStatic(StaticFiles):
    """정적 파일을 캐시하지 않게 준다.

    이 서버는 127.0.0.1 전용 개발 도구이고, `static/` 은 우리가 계속 고치는
    화면 코드다. 그런데 브라우저가 `app.js` 를 캐시하면 **고쳐도 화면이 안
    바뀐다** — 서버는 새 파일을 주는데 브라우저가 옛 것을 쓴다. 코드를 의심하며
    같은 자리를 두 번 고치게 되는 함정이고, 2026-09-23 에 실제로 걸렸다.

    이 저장소가 반복해서 치른 값과 같은 모양이다 — 있는 것과 동작하는 것은
    다르고, 둘이 갈라지면 사람이 엉뚱한 곳을 본다.

    `/runs` 에는 걸지 않는다. 실행 산출물은 한 번 쓰이면 바뀌지 않고, 스크린샷이
    많아 캐시가 실제로 값을 한다.
    """

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-store"
        return resp


# 정적 파일은 마지막에 붙인다. 위의 /static/tokens.css 라우트가 먼저 잡혀야
# 파일이 없는 그 경로가 404 로 떨어지지 않는다.
app.mount("/static", _NoStoreStatic(directory=STATIC), name="static")

# 실행 산출물. 리포트가 스크린샷·DOM 스냅샷을 상대 경로로 참조하므로 디렉터리를
# 통째로 서빙해야 증거 자료가 살아 있다. StaticFiles 가 경로 탈출을 막는다.
RUNS.mkdir(parents=True, exist_ok=True)
app.mount("/runs", StaticFiles(directory=RUNS), name="runs")
