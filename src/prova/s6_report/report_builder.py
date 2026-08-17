"""S6 — 판정 결과를 리포트로 만든다 (JSON + HTML).

## 리포트가 답해야 하는 질문

이 리포트를 읽는 사람은 대개 기획서를 쓴 사람이 아니라 코드를 고쳐야 하는
개발자다. 그가 알고 싶은 것은 순서대로 이렇다.

    1. 뭐가 깨졌나            -> 요약 카드 (통과율, 실패 건수)
    2. 어느 규칙이 문제인가    -> 실패 목록의 '위반 규칙' 열
    3. 정말 그런가            -> 기대 vs 실제, 스크린샷
    4. 무엇을 고쳐야 하나      -> failure_detail

그래서 실패 케이스를 위에 모으고, 각 실패에 기대·실제·근거를 나란히 붙인다.
통과 케이스는 접어 두되 지우지는 않는다 — '무엇이 검증됐는지' 도 기획-구현
일치를 확인하는 증거이기 때문이다.

## 왜 HTML 을 직접 만드는가

리포트는 실행 산출물이라 브라우저에서 파일로 열린다(file:// 스킴). CDN 을
불러오면 오프라인이나 폐쇄망에서 깨진다. B2B QA 도구라는 성격상 폐쇄망 실행을
가정해야 하므로, CSS 를 문서 안에 인라인하고 외부 의존을 두지 않는다.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

from prova.models import SpecDocument, TestReport, Verdict

# 실패 원인 코드 -> 사람이 읽는 이름과 설명 (명세서 §6)
CATEGORY_LABELS = {
    "element_not_found": ("요소 미탐지", "화면에서 조작할 요소를 찾지 못했습니다."),
    "input_error": ("입력 불가", "요소를 찾았으나 조작할 수 없었습니다 (가림·비활성)."),
    "assertion_mismatch": ("기대 불일치", "실행은 됐으나 기획서의 기대와 다릅니다."),
    "timeout": ("시간 초과", "대기 시간을 초과했습니다."),
    "page_error": ("페이지 오류", "HTTP 오류 또는 JS 콘솔 예외가 있습니다."),
    "unknown": ("원인 미분류", "규칙으로 분류되지 않았습니다."),
}


def build_report(
    run_id: str,
    target_url: str,
    verdicts: list[Verdict],
    doc: SpecDocument | None = None,
    coverage: list[str] | None = None,
    spec_source: str = "",
    backend: str = "",
) -> TestReport:
    """판정 목록을 TestReport 로 집계한다."""
    summary = TestReport.summarize(verdicts)

    # 어떤 백엔드로 실행했는지 남긴다. mock 으로 돌린 리포트를 실제 실행 결과로
    # 착각하면 QA 도구로서 최악의 사고가 된다.
    summary["llm_backend"] = backend
    if doc is not None:
        # 문서 경고와 화면별 경고를 한 곳에 모은다. 화면이 여럿이면 경고 앞에
        # [화면 ID] 가 붙어 어디를 고쳐야 하는지가 드러난다 (all_warnings 참고).
        summary["spec_warnings"] = doc.all_warnings
        summary["screen_names"] = {s.screen_id: s.screen_name for s in doc.screens}
    # 확인하지 않은 것. 통과율과 나란히 놓여야 '통과' 의 범위를 알 수 있다.
    if coverage:
        summary["coverage_gaps"] = list(coverage)

    return TestReport(
        run_id=run_id,
        target_url=target_url,
        spec_source=spec_source,
        summary=summary,
        cases=verdicts,
        created_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    )


def save_json(report: TestReport, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "report.json"
    path.write_text(
        json.dumps(report.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

_CSS = """
:root {
  --bg:#f6f7f9; --card:#fff; --line:#e3e6ea; --text:#1c1f23; --muted:#666d75;
  --pass:#1a7f4b; --pass-bg:#e8f6ee; --fail:#c02626; --fail-bg:#fdecec;
  --accent:#2f6fed;
}
* { box-sizing:border-box; }
body { margin:0; padding:32px 24px; background:var(--bg); color:var(--text);
       font-family:"Malgun Gothic","Segoe UI",sans-serif; font-size:14px; line-height:1.6; }
.wrap { max-width:1080px; margin:0 auto; }
h1 { font-size:24px; margin:0 0 4px; }
.meta { color:var(--muted); font-size:13px; margin-bottom:24px; }
.meta code { background:#eceff3; padding:1px 5px; border-radius:3px; font-size:12px; }
.cards { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:8px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:8px;
        padding:16px 20px; min-width:120px; flex:1; }
.card .n { font-size:26px; font-weight:700; }
.card .k { color:var(--muted); font-size:12px; }
.card.pass .n { color:var(--pass); } .card.fail .n { color:var(--fail); }
.bar { height:8px; background:var(--fail-bg); border-radius:4px; overflow:hidden;
       margin:16px 0 28px; }
.bar > i { display:block; height:100%; background:var(--pass); }
h2 { font-size:17px; margin:28px 0 12px; }
.case { background:var(--card); border:1px solid var(--line); border-radius:8px;
        margin-bottom:10px; overflow:hidden; }
.case > summary { padding:12px 16px; cursor:pointer; display:flex; gap:10px;
                  align-items:center; list-style:none; }
.case > summary::-webkit-details-marker { display:none; }
.tag { font-size:11px; font-weight:700; padding:2px 8px; border-radius:10px;
       white-space:nowrap; }
.tag.PASS { background:var(--pass-bg); color:var(--pass); }
.tag.FAIL { background:var(--fail-bg); color:var(--fail); }
.tag.rule { background:#eef2fb; color:var(--accent); font-weight:600; }
.title { flex:1; }
.ms { color:var(--muted); font-size:12px; }
.body { border-top:1px solid var(--line); padding:14px 16px; background:#fbfcfd; }
.reason { background:var(--fail-bg); border-left:3px solid var(--fail); padding:10px 12px;
          border-radius:0 4px 4px 0; margin-bottom:14px; }
table.kv { width:100%; border-collapse:collapse; margin-bottom:12px; }
table.kv th { text-align:left; width:110px; vertical-align:top; color:var(--muted);
              font-weight:600; padding:5px 8px 5px 0; font-size:13px; }
table.kv td { padding:5px 0; word-break:break-all; }
.steps { border-collapse:collapse; width:100%; font-size:13px; }
.steps th, .steps td { border:1px solid var(--line); padding:5px 8px; text-align:left; }
.steps th { background:#f0f2f5; font-weight:600; }
.steps td.err { color:var(--fail); }
.shots { display:flex; gap:10px; flex-wrap:wrap; margin-top:10px; }
.shots a { display:block; }
.shots img { height:150px; border:1px solid var(--line); border-radius:4px;
             background:#fff; display:block; }
.shots .cap { font-size:11px; color:var(--muted); text-align:center; margin-top:3px; }
.heal { background:#f3eefb; border:1px solid #cbb8e8; border-radius:6px;
        padding:12px 14px; margin-bottom:14px; font-size:13px; line-height:1.6; }
.heal b { color:#6b3fa0; }
.heal .why { color:var(--muted); margin:2px 0 8px; }
.gap { background:#eef4fb; border:1px solid #b8cfe8; border-radius:6px;
       padding:12px 14px; margin-bottom:14px; font-size:13px; line-height:1.6; }
.gap b { color:var(--accent); }
.gap .why { color:var(--muted); margin:2px 0 8px; }
.warn { background:#fff8e1; border:1px solid #f0d68a; border-radius:6px;
        padding:10px 14px; margin-bottom:18px; }
.warn b { display:block; margin-bottom:4px; }
.empty { color:var(--muted); padding:12px 0; }
.screens { border-collapse:collapse; font-size:13px; margin:14px 0 4px; }
.screens th, .screens td { border:1px solid var(--line); padding:5px 10px; text-align:left; }
.screens th { background:#f0f2f5; font-weight:600; }
.screens td.n { text-align:right; font-variant-numeric:tabular-nums; }
.screens td.f { color:var(--fail); font-weight:700; }
.screens td.k { color:var(--muted); font-size:12px; }
h3.grp { font-size:14px; margin:18px 0 6px; color:var(--muted); font-weight:600; }
"""


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def _category_html(verdict: Verdict) -> str:
    if not verdict.failure_category:
        return ""
    label, desc = CATEGORY_LABELS.get(verdict.failure_category,
                                      (verdict.failure_category, ""))
    return f"{_esc(label)} <span class='ms'>({_esc(desc)})</span>"


def _steps_html(verdict: Verdict) -> str:
    if not verdict.step_results:
        return ""
    rows = []
    for r in verdict.step_results:
        detail = r.error_detail or ""
        strategy = r.location.strategy if r.location else ""
        cls = " class='err'" if r.status == "error" else ""
        rows.append(
            f"<tr><td>{r.seq}</td><td>{_esc(r.action)}</td><td>{_esc(r.target)}</td>"
            f"<td>{_esc(strategy)}</td><td{cls}>{_esc(r.status)}</td>"
            f"<td>{r.elapsed_ms}ms</td><td{cls}>{_esc(detail)}</td></tr>"
        )
    return (
        "<table class='steps'><thead><tr><th>#</th><th>동작</th><th>대상</th>"
        "<th>탐지</th><th>결과</th><th>소요</th><th>오류</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _shots_html(verdict: Verdict) -> str:
    shots = [(r.seq, r.screenshot) for r in verdict.step_results if r.screenshot]
    if not shots:
        return ""
    items = "".join(
        f"<a href='{_esc(path)}' target='_blank'>"
        f"<img src='{_esc(path)}' alt='step {seq}'>"
        f"<div class='cap'>step {seq}</div></a>"
        for seq, path in shots
    )
    return f"<div class='shots'>{items}</div>"


def _case_html(verdict: Verdict, open_by_default: bool) -> str:
    ev = verdict.evidence or {}
    # 요소와 규칙을 함께 보여준다. 화면에 같은 규칙을 가진 요소가 여럿이면
    # (회원가입의 required 6개) 규칙 이름만으로는 어디를 고쳐야 할지 모른다.
    rule_label = (f"{verdict.target_element}.{verdict.violates}"
                  if verdict.target_element else verdict.violates)
    rule_tag = (f"<span class='tag rule'>{_esc(rule_label)}</span>"
                if verdict.violates else "")

    reason = ""
    if verdict.verdict == "FAIL" and verdict.failure_detail:
        reason = f"<div class='reason'>{_esc(verdict.failure_detail)}</div>"

    rows = [
        ("기대", _esc(ev.get("expected"))),
        ("실제", _esc(ev.get("actual"))),
        ("최종 URL", f"<code>{_esc(ev.get('url'))}</code>"),
    ]
    if verdict.failure_category:
        rows.append(("실패 분류", _category_html(verdict)))
    if ev.get("error_texts"):
        rows.append(("화면 에러", _esc(" / ".join(ev["error_texts"]))))

    kv = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)

    return (
        f"<details class='case'{' open' if open_by_default else ''}>"
        f"<summary><span class='tag {verdict.verdict}'>{verdict.verdict}</span>"
        f"{rule_tag}<span class='title'>{_esc(verdict.title)}</span>"
        f"<span class='ms'>{verdict.elapsed_ms}ms</span></summary>"
        f"<div class='body'>{reason}"
        f"<table class='kv'>{kv}</table>"
        f"{_steps_html(verdict)}{_shots_html(verdict)}"
        f"</div></details>"
    )


def _screens_html(by_screen: dict, by_flow: dict, names: dict) -> str:
    """화면별·흐름별 내역 표. 나눠 볼 것이 없으면 그리지 않는다.

    화면 하나에 흐름도 없으면 전체 요약과 같은 숫자를 두 번 보여주게 되고, 읽는
    사람이 '왜 두 번 있지' 를 확인하는 데 시간을 쓴다.

    흐름을 화면과 같은 표에 두되 행을 구분한다. 나란히 놓여야 '화면은 다 통과인데
    흐름만 실패' 라는 모양이 한눈에 보이고, 그 모양이 곧 '결함은 화면 사이에
    있다' 는 진단이다.
    """
    if len(by_screen) + len(by_flow) < 2:
        return ""

    def row(label: str, code: str, n: dict, kind: str) -> str:
        fail_cls = " class='n f'" if n["fail"] else " class='n'"
        return (
            f"<tr><td>{_esc(label)} <code>{_esc(code)}</code></td>"
            f"<td class='k'>{_esc(kind)}</td>"
            f"<td class='n'>{n['total']}</td><td class='n'>{n['pass']}</td>"
            f"<td{fail_cls}>{n['fail']}</td></tr>"
        )

    rows = [row(names.get(sid, sid), sid, n, "화면") for sid, n in by_screen.items()]
    rows += [row("화면 사이", fid, n, "흐름") for fid, n in by_flow.items()]
    return (
        "<table class='screens'><thead><tr><th>대상</th><th>종류</th><th>전체</th>"
        "<th>통과</th><th>실패</th></tr></thead><tbody>"
        + "".join(rows) + "</tbody></table>"
    )


def _grouped_html(verdicts: list[Verdict], names: dict, open_by_default: bool) -> str:
    """판정을 화면별로 묶어 렌더한다. 묶을 것이 하나면 소제목을 붙이지 않는다.

    흐름은 별도 구획으로 떼어 맨 뒤에 둔다. 마지막 화면 구획에 섞으면 **그 화면에
    결함이 하나 더 있는 것처럼 읽힌다** — 흐름의 실패는 화면 안이 아니라 화면
    사이의 문제이고 고칠 곳도 다르다.
    """
    if not verdicts:
        return ""
    groups: dict[str, list[Verdict]] = {}
    for v in verdicts:
        key = f"흐름 {v.flow_id}" if v.flow_id else names.get(v.screen_id or "?",
                                                             v.screen_id or "?")
        groups.setdefault(key, []).append(v)

    if len(groups) < 2:
        return "".join(_case_html(v, open_by_default) for v in verdicts)

    out = []
    for label, items in groups.items():
        out.append(f"<h3 class='grp'>{_esc(label)} · {len(items)}건</h3>")
        out.extend(_case_html(v, open_by_default) for v in items)
    return "".join(out)


def render_html(report: TestReport) -> str:
    s = report.summary
    total = s.get("total", 0) or 0
    passed, failed = s.get("pass", 0), s.get("fail", 0)
    rate = s.get("pass_rate", 0)

    fails = [v for v in report.cases if v.verdict == "FAIL"]
    passes = [v for v in report.cases if v.verdict == "PASS"]

    warnings = s.get("spec_warnings") or []
    warn_html = ""
    if warnings:
        items = "".join(f"<div>· {_esc(w)}</div>" for w in warnings)
        warn_html = (
            "<div class='warn'><b>설계 문서 추출 경고</b>"
            f"{items}</div>"
        )

    # 부분 실행 경고. --only 로 일부만 돌린 결과를 전체 결과로 착각하면
    # "통과율 100%" 가 실제 상태를 뜻하지 않게 된다.
    filtered = s.get("filtered_by")
    filter_warn = ""
    if filtered:
        avail = s.get("cases_available", "?")
        filter_warn = (
            "<div class='warn'><b>일부 케이스만 실행된 리포트입니다</b>"
            f"<div>필터 <code>{_esc(filtered)}</code> 로 전체 {_esc(avail)}건 중 "
            f"{total}건만 실행했습니다. 이 통과율은 전체 상태를 뜻하지 않습니다.</div></div>"
        )

    gaps = s.get("coverage_gaps") or []
    gap_html = ""
    if gaps:
        items = "".join(f"<div>· {_esc(g)}</div>" for g in gaps)
        gap_html = (
            "<div class='gap'><b>확인하지 않은 것 "
            f"({len(gaps)}건)</b>"
            "<div class='why'>기획서에 적혀 있으나 이 실행에서 대조한 케이스가 "
            "없습니다. 아래 항목은 <b>통과한 것이 아니라 확인하지 않은 것</b>입니다."
            "</div>"
            f"{items}</div>"
        )

    healed = s.get("healed", 0) or 0
    heal_html = ""
    if healed:
        healed_titles = "".join(
            f"<div>· {_esc(v.title)}</div>"
            for v in report.cases if v.healed
        )
        heal_html = (
            f"<div class='heal'><b>화면 이미지로 찾아 진행한 케이스 ({healed}건)</b>"
            "<div class='why'>기획서의 라벨로 요소를 찾지 못해 2차 경로로 보정했습니다. "
            "판정은 유효하지만 <b>라벨이 구현과 이어져 있지 않습니다</b> — "
            "'라벨로 요소를 찾을 수 있는지 확인' 케이스를 함께 보세요.</div>"
            f"{healed_titles}</div>"
        )

    # 기다려서 통과한 케이스.
    #
    # healed 와 같은 이유로 남긴다 — 도구가 편의를 제공했으면 그 사실이 리포트에
    # 있어야 한다. 여기서는 '이 화면이 결과를 늦게 보여준다' 는 사실이고, 실물
    # 화면의 성질에 대한 정보다. 통과율만 보는 사람도 알아야 한다.
    settled = s.get("settled", 0) or 0
    settle_html = ""
    if settled:
        rows = "".join(
            f"<div>· {_esc(v.title)} <b>{v.evidence['settled_ms']}ms</b></div>"
            for v in report.cases if v.evidence.get("settled_ms")
        )
        worst = max(v.evidence["settled_ms"] for v in report.cases
                    if v.evidence.get("settled_ms"))
        settle_html = (
            f"<div class='heal'><b>결과를 기다린 뒤 통과한 케이스 ({settled}건, "
            f"최대 {worst}ms)</b>"
            "<div class='why'>제출 직후에는 화면에 결과가 없었고, 기다린 뒤 나타났습니다. "
            "판정은 유효합니다 — <b>이 화면이 결과를 비동기로 렌더한다</b>는 뜻입니다. "
            "기다리지 않으면 올바른 구현이 FAIL 로 나옵니다.</div>"
            f"{rows}</div>"
        )

    backend = s.get("llm_backend", "")
    mock_warn = ""
    if backend.startswith("mock"):
        mock_warn = (
            "<div class='warn'><b>mock 백엔드로 실행된 리포트입니다</b>"
            "<div>설계 문서 추출에 실제 모델이 쓰이지 않았습니다. "
            "이 결과를 실제 검증 결과로 사용하지 마세요.</div></div>"
        )

    names = s.get("screen_names") or {}
    screens_html = _screens_html(s.get("by_screen") or {},
                                 s.get("by_flow") or {}, names)

    fail_section = _grouped_html(fails, names, open_by_default=True) or         "<div class='empty'>실패한 케이스가 없습니다.</div>"
    pass_section = _grouped_html(passes, names, open_by_default=False) or         "<div class='empty'>통과한 케이스가 없습니다.</div>"

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>Prova 리포트 — {_esc(report.run_id)}</title>
<style>{_CSS}</style></head>
<body><div class="wrap">
<h1>Prova 검증 리포트</h1>
<div class="meta">
  대상 <code>{_esc(report.target_url)}</code> ·
  설계 문서 <code>{_esc(report.spec_source)}</code> ·
  실행 <code>{_esc(report.run_id)}</code> · {_esc(report.created_at)}
  {f" · 모델 <code>{_esc(backend)}</code>" if backend else ""}
</div>
{mock_warn}{filter_warn}{heal_html}{settle_html}{gap_html}{warn_html}
<div class="cards">
  <div class="card"><div class="n">{total}</div><div class="k">전체 케이스</div></div>
  <div class="card pass"><div class="n">{passed}</div><div class="k">통과</div></div>
  <div class="card fail"><div class="n">{failed}</div><div class="k">실패</div></div>
  <div class="card"><div class="n">{rate}%</div><div class="k">통과율</div></div>
</div>
<div class="bar"><i style="width:{rate}%"></i></div>
{screens_html}

<h2>실패 케이스 ({len(fails)})</h2>
{fail_section}

<h2>통과 케이스 ({len(passes)})</h2>
{pass_section}
</div></body></html>
"""


def save_html(report: TestReport, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "report.html"
    path.write_text(render_html(report), encoding="utf-8")
    return path
