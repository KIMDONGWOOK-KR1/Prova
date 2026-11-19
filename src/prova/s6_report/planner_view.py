"""기획자용 보고서 (planner.html) — 리포트와 같은 모양, 기획자가 판단하는 데 쓰는 것만 (2026-11-19).

## 왜 따로 있는가

report.html 은 원인을 찾아 고치는 사람의 문서다 — 실행 조건, 추출 경고, 단계별 기록, 단계마다의
캡처가 다 있다. 예시 사이트(화면 1개)에서는 그래도 짧지만, 실물 기획서(화면 21개·43건·경고
150줄)에서는 결론과 틀린 곳 사이에 읽지 않을 것이 수백 줄 놓였다. 기획자는 '어디가 기획서와
다른가, 무엇을 못 봤는가' 만 묻는다.

## 무엇을 남기고 무엇을 빼는가

남김: 결론·집계, 판정의 뜻을 바꾸는 알림(한 줄씩), 기획서와 다른 곳(리포트와 같은 카드),
확인하지 못한 곳(멈춘 이유가 같은 것끼리), 보지 않은 화면, 확인하지 않은 것, 시안과 실제 화면.

뺌: 실행 조건, 직전 실행 비교 상자, 추출 경고·모델 메모, 단계별 기록 표와 단계마다의 캡처,
소요 시간, 그때의 주소, 통과 케이스 카드(수만 남긴다). 전부 report.html 에 있다.

## 화면 단위로 넘겨 본다

화면이 여럿이면 첫 장은 요약(결론 + 화면 목록)이고, 화면을 누르면 그 화면의 건만 보인다.
한 파일 안에 모든 장을 두고 주소의 `#` 로 한 장만 보인다 — 파일 하나로 보낼 수 있고 인터넷 없이
열린다. 인쇄·PDF·스크립트가 꺼진 때는 전부 펼친다. 화면이 하나뿐이면 넘길 것이 없어 한 장이다.

카드와 스타일은 report_builder 의 것을 그대로 쓴다. 두 벌로 쓰면 한쪽이 뒤처진다. 판정은 바꾸지 않는다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from prova.models import TestReport, Verdict
from prova.s6_report.report_builder import (
    _COPY_JS, _CSS, _LIGHTBOX_JS, _NO_URL, _PRINT_JS, _THEME_BTN_JS, _THEME_JS, THEME_BUTTON,
    _case_html, _chart_html, _conclusion, _esc, _groups, _screens_phrase,
    _shots_html, fail_kind, is_weak_pass,
)
from prova.s6_report.spec_figures import build_spec_figures
from prova.wording import missing_names, stop_reason

PLANNER_FILE = "planner.html"

_PLANNER_CSS = """
/* 기획자용 보고서 — 화면 단위로 넘겨 본다. 색·글자·카드는 리포트(_CSS)의 것이다. */
.pg[hidden], .pgnav[hidden] { display:none; }
/* 넘기는 줄 — 위쪽에 붙어 있어 긴 장에서도 목록으로 돌아갈 수 있다. */
.pgnav { display:flex; align-items:center; gap:var(--sp-2); flex-wrap:wrap; margin-bottom:var(--sp-5);
         padding-bottom:var(--sp-3); border-bottom:1px solid var(--line); font-size:var(--tx-md); }
.pgnav a { text-decoration:none; padding:5px 12px; border-radius:var(--r-full); border:1px solid var(--line); }
.pgnav a:hover { border-color:var(--text); }
.pgnav a:focus-visible { outline:none; box-shadow:var(--focus-ring); }
.pgnav a[aria-disabled=true] { opacity:.35; pointer-events:none; }
.pgnav .at { margin-left:auto; color:var(--muted); font-variant-numeric:tabular-nums; }
/* 화면 장의 머리 — 화면 이름이 제목이다. */
.pg-h { display:flex; align-items:baseline; gap:6px 16px; flex-wrap:wrap; margin:0 0 var(--sp-2); }
.pg-h h2 { border:0; margin:0; padding:0; font-size:24px; font-weight:400; letter-spacing:-0.02em; }
.pg-h .scr-n { font-size:var(--tx-md); }
.pg > h3 { font-size:var(--tx-base); font-weight:650; margin:var(--sp-8) 0 0; padding-bottom:var(--sp-2);
           border-bottom:2px solid var(--text); }
.pg > h3.defect { color:var(--fail); } .pg > h3.infra { color:var(--note-fg); }
/* 화면 목록 — 한 줄이 한 화면. 누르면 그 화면의 장으로 간다. */
.pg .scr { grid-template-columns:80px minmax(0,1fr); padding:8px 0; align-items:center; }
.pg .scr-t.none { width:80px; height:50px; }
a.scr { color:inherit; text-decoration:none; }
a.scr:hover { background:var(--bg-hover); }
a.scr:focus-visible { outline:none; box-shadow:var(--focus-ring); }
.scr .go { margin-left:auto; color:var(--muted); font-size:var(--tx-md); white-space:nowrap; }
.scr-t.plain img { display:block; width:80px; height:50px; object-fit:cover; object-position:top;
                   border:1px solid var(--line); border-radius:var(--r-sm); background:var(--gray-0); }
@media (max-width:640px) { .pg .scr { grid-template-columns:56px minmax(0,1fr); }
  .scr-t.plain img, .pg .scr-t.none { width:56px; height:36px; } .scr .go { display:none; } }
/* 판정의 뜻을 바꾸는 알림 — 한 줄씩. */
.warn.slim { padding-top:var(--sp-2); padding-bottom:var(--sp-2); }
.warn.slim::before { top:11px; }
.warn.slim b { display:inline; font-size:14px; margin:0 6px 0 0; }
/* 멈춘 이유가 같은 건의 묶음 — 이유와 그때의 화면은 한 번, 건마다는 접어 둔다. */
.stuck { border-bottom:1px solid var(--line); padding-bottom:var(--sp-2); }
.stuck .fwhy { padding-top:var(--sp-4); font-size:var(--tx-base); color:var(--text); }
.stuck .fwhy small { display:block; font-size:var(--tx-md); color:var(--muted); margin-top:2px; }
.stuck .case:last-child { border-bottom:0; }
.stuck .case.failed > summary { padding-top:10px; padding-bottom:10px; }
.stuck .case.failed > summary .no { top:11px; font-size:var(--tx-base); }
.stuck .case .head { font-size:var(--tx-base); font-weight:400; }
.stuck .shots.last { max-width:560px; margin:0 0 var(--sp-2); }
.pg .scr-l { margin-top:var(--sp-3); }
.passline { color:var(--muted); font-size:var(--tx-md); margin:var(--sp-6) 0 0; }
.pfoot { margin-top:var(--sp-12); padding-top:var(--sp-3); border-top:1px solid var(--line);
         color:var(--muted); font-size:13px; }
.embedded .pfoot, .embedded .pg .actions { display:none; }
@media print {
  .pg[hidden] { display:block !important; }
  .pgnav, a.scr .go { display:none; }
  .pg + .pg { break-before:page; }
  .case .head { flex-basis:100%; }
}
"""

# 주소의 # 로 한 장만 보인다. 카드 번호(#c-…)로 오면 그 카드가 든 장을 연다.
_PAGER_JS = """(function () {
  var pages = [].slice.call(document.querySelectorAll('section.pg'));
  if (pages.length < 2) return;
  var nav = document.getElementById('pgnav'), order = pages.slice(1);
  function toTop() {
    try {
      if (self !== top && window.frameElement) {
        var pw = parent, bar = pw.document.querySelector('.topbar');
        var y = window.frameElement.getBoundingClientRect().top + pw.scrollY
              - (bar ? bar.getBoundingClientRect().height : 0) - 16;
        if (pw.scrollY > y) pw.scrollTo(0, y);
        return;
      }
    } catch (e) {}
    window.scrollTo(0, 0);
  }
  function show(page, target) {
    pages.forEach(function (p) { p.hidden = p !== page; });
    var i = order.indexOf(page);
    nav.hidden = i < 0;
    if (i >= 0) {
      var prev = nav.querySelector('.prev'), next = nav.querySelector('.next');
      prev.href = '#' + (i > 0 ? order[i - 1].id : page.id);
      next.href = '#' + (i < order.length - 1 ? order[i + 1].id : page.id);
      prev.setAttribute('aria-disabled', i === 0);
      next.setAttribute('aria-disabled', i === order.length - 1);
      nav.querySelector('.at').textContent = (i + 1) + ' / ' + order.length;
    }
    if (target) {
      if (target.tagName === 'DETAILS') target.open = true;
      target.scrollIntoView({ block: 'start' });
    } else { toTop(); }
  }
  function route() {
    var el = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    var page = el && el.closest('section.pg');
    show(page || pages[0], el && el !== page ? el : null);
  }
  window.addEventListener('hashchange', route);
  window.addEventListener('beforeprint', function () { pages.forEach(function (p) { p.hidden = false; }); });
  window.addEventListener('afterprint', route);
  route();
})();"""

_SAVE_PDF_JS = """document.addEventListener('click', function (e) {
  if (e.target.closest && e.target.closest('#pdfBtn')) window.print();
});"""


def _notices(s: dict, selection) -> str:
    """판정의 뜻을 바꾸는 알림만, 한 줄씩. 이것이 빠지면 연습 결과가 실제 결과로 읽힌다."""
    out = []
    if str(s.get("llm_backend", "")).startswith("mock"):
        out.append(("dup", "연습용으로 실행한 결과입니다", "기획서를 실제 모델로 읽지 않았습니다. "
                    "실제 검증 결과로 쓰지 마세요."))
    if s.get("filtered_by"):
        out.append(("", "일부 케이스만 실행했습니다", f"전체 {s.get('cases_available', '?')}건 중 "
                    f"{s.get('total', 0)}건입니다. 이 결과는 전체 상태를 뜻하지 않습니다."))
    excluded = len(selection.excluded) if selection else 0
    if excluded:
        out.append(("", f"{excluded}건은 이번 실행에서 제외했습니다", "제외한 건은 통과한 것이 아니라 "
                    "실행하지 않은 것입니다."))
    if s.get("input_kind") == "figma":
        out.append(("", "입력이 Figma 디자인입니다", "검증 규칙이 없어 이름·안내 문구·선택 항목만 대조했습니다."))
    dry = s.get("dry_run")
    if dry:
        out.append(("dup", "쓰기 요청을 막고 실행했습니다", f"그 때문에 {dry.get('cases_blocked', 0)}건은 "
                    "제출 뒤를 보지 못해 확인 불가입니다."))
    if s.get("url_note"):
        out.append(("", str(s["url_note"]), ""))
    return "".join(f"<div class='warn slim {cls}'><b>{_esc(head)}</b>{_esc(body)}</div>"
                   for cls, head, body in out)


def _first_shot(report: TestReport, sid: str) -> str | None:
    return next((r.screenshot for v in report.cases if v.screen_id == sid and not v.flow_id
                 for r in v.step_results if r.action == "navigate" and r.screenshot), None)


def _split(line: str, names: dict) -> tuple[str, str]:
    """'[화면 ID] 문장' 을 (화면 ID, 문장)으로. 화면을 모르면 ('', 원문)."""
    m = re.match(r"\[([^\]]+)\]\s*(.*)", str(line), re.S)
    if not m:
        return "", str(line)
    by_name = {str(v): k for k, v in names.items()}
    sid = m.group(1) if m.group(1) in names else by_name.get(m.group(1), "")
    return (sid, m.group(2)) if sid else ("", str(line))


def _tally(cases: list[Verdict]) -> str:
    kinds = [fail_kind(v) for v in cases if v.verdict == "FAIL"]
    passed = sum(1 for v in cases if v.verdict == "PASS")
    return " · ".join(x for x in (
        f"<span class='n defect'>기획서와 다름 {kinds.count('defect')}</span>" if "defect" in kinds else "",
        f"<span class='n infra'>확인하지 못함 {kinds.count('infra')}</span>" if "infra" in kinds else "",
        f"확인 불가 {kinds.count('unv')}" if "unv" in kinds else "",
        f"통과 {passed}") if x)


def _stuck_html(items: list[Verdict], defects: list[Verdict], numbers: dict, target_url: str) -> str:
    """확인하지 못한 곳 — 멈춘 이유가 같은 것끼리 묶는다. 이유와 그때의 화면은 한 번만 보인다."""
    groups: dict[str, list[Verdict]] = {}
    for v in items:
        groups.setdefault(stop_reason(v)[1], []).append(v)
    missing_at = {name: numbers.get(d.case_id, "") for d in defects for name in missing_names(d)[0]}
    out = []
    for sentence, group in groups.items():
        target = stop_reason(group[0])[0]
        same = (f"<small>'{_esc(target)}' 은(는) 기획서와 다른 곳 {missing_at[target]}번에서 화면에 없던 "
                "이름입니다. 같은 차이 때문에 멈춘 것으로 보입니다.</small>"
                if target and target in missing_at else "")
        if len(group) < 2:
            out.append(f"<div class='stuck'>{_case_html(group[0], True, target_url=target_url, no=numbers.get(group[0].case_id), planner=True)}"
                       f"{f'<div class={chr(39)}fwhy{chr(39)}>{same}</div>' if same else ''}</div>")
            continue
        cards = "".join(_stuck_card(v, numbers.get(v.case_id), target_url) for v in group)
        out.append(f"<div class='stuck'><div class='fwhy'><b>같은 이유로 {len(group)}건</b>{_esc(sentence)}"
                   f"{same}</div>{_shots_html(group[0], last=True)}{cards}</div>")
    return "".join(out)


def _stuck_card(v: Verdict, no, target_url: str) -> str:
    """묶음 안의 한 건 — 접어 둔다. 제목은 무엇을 확인하려던 것인지다(이유는 묶음 머리에 있다)."""
    card = _case_html(v, False, target_url=target_url, no=no, planner=True)
    # 대제목(멈춘 이유)은 묶음 머리와 같은 말이다 — 확인하려던 것으로 바꾼다.
    head = f"<span class=head>{_esc(stop_reason(v)[1])}</span>"
    title = f"<span class=title>{_esc(v.plain or v.title)}</span>"
    return card.replace(title, "", 1).replace(head, f"<span class=head>{_esc(v.plain or v.title)}</span>", 1)


def _screen_body(report: TestReport, sid: str, cases: list[Verdict], numbers: dict, gaps: list[str],
                 figures: dict, name: str) -> str:
    """한 화면의 본문 — 다른 곳, 확인하지 못한 곳, 확인하지 않은 것, 시안과 실제 화면."""
    fails = [v for v in cases if v.verdict == "FAIL"]
    defects = [v for v in fails if fail_kind(v) == "defect"]
    stuck = [v for v in fails if fail_kind(v) != "defect"]
    passed = [v for v in cases if v.verdict == "PASS"]
    out = []
    if defects:
        out.append(f"<h3 class='defect'>기획서와 다른 곳 {len(defects)}</h3>" + "".join(
            _case_html(v, True, target_url=report.target_url, no=numbers.get(v.case_id), planner=True)
            for v in defects))
    if stuck:
        out.append(f"<h3 class='infra'>확인하지 못한 곳 {len(stuck)}</h3>"
                   "<p class='scope-note'>도중에 멈춰 결과를 보지 못했습니다. 결함이라는 뜻은 아닙니다.</p>"
                   + _stuck_html(stuck, defects, numbers, report.target_url))
    if gaps:
        out.append("<h3>확인하지 않은 것</h3>" + "".join(
            f"<div class='scr-l'>{_esc(g)}</div>" for g in gaps))
    if sid in figures:
        crop, full = figures[sid]
        shot = _first_shot(report, sid)
        real = (f"<a href='{_esc(shot)}' target='_blank'><img src='{_esc(shot)}' loading='lazy' "
                f"alt='{_esc(name)} 실제 화면'><div class='cap'>{_esc(name)} · 실제 화면</div></a>" if shot else "")
        out.append(
            "<h3>기획서 시안과 실제 화면</h3><p class='scope-note'>색·배치는 자동으로 대조하지 않았습니다. "
            "나란히 놓고 직접 비교하세요. 누르면 크게 봅니다.</p>"
            f"<div class='shots pair'><a href='{_esc(full)}' target='_blank'><img src='{_esc(crop)}' "
            f"loading='lazy' alt='{_esc(name)} 기획서 시안'><div class='cap'>{_esc(name)} · 기획서 시안</div></a>"
            f"{real}</div>")
    if passed:
        weak = sum(1 for v in passed if is_weak_pass(v))
        out.append(f"<p class='passline'>기획서대로인 항목 {len(passed)}건"
                   f"{f' (그중 {weak}건은 오류가 없는지만 확인)' if weak else ''}</p>")
    return "".join(out)


def render_planner_html(report: TestReport, spec_figures: dict | None = None) -> str:
    s = report.summary or {}
    figures = spec_figures or {}
    names: dict = {k: v for k, v in (s.get("screen_names") or {}).items() if k}
    cases = report.cases
    total = s.get("total", len(cases)) or 0
    fails = [v for v in cases if v.verdict == "FAIL"]
    checked = list(dict.fromkeys(v.screen_id for v in cases if v.screen_id and not v.flow_id))
    # 번호는 리포트(report.html)와 같다 — 기획자와 개발사가 '3번' 으로 같은 건을 가리킨다.
    numbers = {v.case_id: i for i, v in enumerate(
        (v for items in _groups(fails, names).values() for v in items), 1)}

    gap_by: dict[str, list[str]] = {}
    for g in s.get("coverage_gaps") or []:
        sid, text = _split(g, names)
        gap_by.setdefault(sid, []).append(text)
    no_url = {sid for sid, text in (_split(w, names) for w in s.get("spec_warnings") or [])
              if sid and _NO_URL in text}

    history = s.get("history") or {}
    changed = len(history.get("regressed") or []) + len(history.get("fixed") or [])
    cond = " · ".join(x for x in (
        _screens_phrase(names, checked),
        f"{history['round']}번째 실행" if history.get("round") else "",
        "" if not history.get("previous_run") else
        (f"직전보다 새로 실패 {len(history.get('regressed') or [])} · 해결 {len(history.get('fixed') or [])}"
         if changed else "직전과 같은 결과"),
    ) if x)
    sel = report.selection
    chart = _chart_html(cases, len(s.get("coverage_gaps") or []), len(sel.excluded) if sel else 0,
                        s.get("pass_rate", 0))
    head = (
        "<div class='result-head'>"
        f"<div><h1>{_conclusion(cases, total)}</h1>{f'<div class={chr(39)}cond{chr(39)}>{_esc(cond)}</div>' if cond else ''}</div>"
        "<div class='actions'><a class='btn primary' href='report.xlsx' download>엑셀 받기</a>"
        "<button class='btn' id='pdfBtn' type='button' style='border-color:var(--line);background:transparent;"
        "color:var(--text)'>PDF 로 저장</button></div></div>"
        f"{chart}{_notices(s, sel)}")

    # 장 나누기 — 케이스가 있는 화면마다 한 장, 화면 사이(흐름)도 한 장.
    units: list[tuple[str, str, list[Verdict]]] = [
        (sid, str(names.get(sid) or sid), [v for v in cases if v.screen_id == sid and not v.flow_id])
        for sid in checked]
    flows = list(dict.fromkeys(v.flow_id for v in cases if v.flow_id))
    units += [(f"flow:{fid}", f"화면 사이 {fid}", [v for v in cases if v.flow_id == fid]) for fid in flows]
    unseen = [sid for sid in names if sid not in checked]

    if len(units) + len(unseen) <= 1:
        # 넘길 것이 없다 — 리포트와 같은 순서로 한 장에 다 보인다.
        sid, name, mine = units[0] if units else ("", "", [])
        # 리포트의 '한 줄 목록' 은 두지 않는다 — 바로 아래 카드의 대제목이 같은 말이다.
        body = _screen_body(report, sid, mine, numbers, gap_by.get(sid, []) + gap_by.get("", []),
                            figures, name)
        pages = f"<section class='pg' id='p-top'>{head}{body}</section>"
        nav = ""
    else:
        rows, sections = [], []
        for i, (sid, name, mine) in enumerate(units, 1):
            shot = _first_shot(report, sid)
            thumb = (f"<div class='scr-t plain'><img src='{_esc(shot)}' loading='lazy' alt=''></div>"
                     if shot else "<div class='scr-t none'></div>")
            gaps = gap_by.get(sid, [])
            rows.append(
                f"<a class='scr' href='#p-{i}'>{thumb}<div class='scr-b'><div class='scr-h'><b>{_esc(name)}</b>"
                f"<span class='scr-n'>확인 {len(mine)}건 — {_tally(mine)}"
                f"{f' · 확인하지 않은 것 {len(gaps)}' if gaps else ''}</span>"
                "<span class='go'>자세히 보기</span></div></div></a>")
            sections.append(
                f"<section class='pg' id='p-{i}'><div class='pg-h'><h2>{_esc(name)}</h2>"
                f"<span class='scr-n'>확인 {len(mine)}건 — {_tally(mine)}</span></div>"
                f"{_screen_body(report, sid, mine, numbers, gaps, figures, name)}</section>")
        for sid in unseen:
            name = str(names.get(sid) or sid)
            crop = figures.get(sid, ("", ""))[0]
            thumb = (f"<div class='scr-t plain'><img src='{_esc(crop)}' loading='lazy' alt=''></div>"
                     if crop else "<div class='scr-t none'></div>")
            why = ("화면 주소가 기획서에 없어 열지 못했습니다. 실행할 때 이 화면의 주소를 알려 주면 확인합니다."
                   if sid in no_url else "이번 실행에서 확인한 케이스가 없습니다.")
            rows.append(f"<div class='scr unseen'>{thumb}<div class='scr-b'><div class='scr-h'><b>{_esc(name)}</b>"
                        f"<span class='scr-n'><b class='unseen'>보지 않음</b> — {why}</span></div></div></div>")
        loose = "".join(f"<div class='scr-l'><b>확인하지 않은 것</b> {_esc(g)}</div>" for g in gap_by.get("", []))
        note = ""
        if unseen:
            note = (f"<p class='scope-note'>기획서 화면 {len(names)}개 가운데 {len(names) - len(unseen)}개를 "
                    "확인했습니다. '보지 않음' 은 <b>통과한 것이 아니라 확인하지 않은 것</b>입니다.</p>")
        pages = (f"<section class='pg' id='p-top'>{head}<h2>화면별 결과 ({len(rows)})</h2>{note}"
                 f"<div class='scope'>{''.join(rows)}</div>{loose}</section>{''.join(sections)}")
        nav = ("<nav class='pgnav' id='pgnav' hidden aria-label='화면 넘기기'><a href='#p-top'>전체 요약</a>"
               "<a class='prev' href='#p-top'>이전 화면</a><a class='next' href='#p-top'>다음 화면</a>"
               "<span class='at'></span></nav>")

    spec_name = str(report.spec_source or "").replace("\\", "/").rsplit("/", 1)[-1]
    when = str(report.created_at or "")[:16].replace("T", " ")
    crumbs = (f"<b title='{_esc(report.spec_source)}'>{_esc(spec_name)}</b><span aria-hidden='true'>→</span>"
              if spec_name else "")
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<script>{_THEME_JS}</script>
<title>Prova 기획서 대조 결과 · {_esc(spec_name or report.run_id)}</title>
<style>{_CSS}{_PLANNER_CSS}</style>
<script>if(self!==top)document.documentElement.className='embedded'</script></head>
<body>
<header class="topbar">
<div class="crumbs">{crumbs}<span>{_esc(report.target_url)}</span></div>
<div class="name">Prova</div>
<div class="when"><span>기획서 대조 결과 · {_esc(when)}</span>{THEME_BUTTON}</div>
</header>
<div class="wrap">
{nav}{pages}
<p class="pfoot">단계별 기록·캡처·실행 조건은 <a href="report.html">고치는 사람용 리포트</a>에 있습니다.</p>
</div><script>{_LIGHTBOX_JS}</script><script>{_COPY_JS}</script><script>{_PRINT_JS}</script>
<script>{_THEME_BTN_JS}</script><script>{_PAGER_JS}</script><script>{_SAVE_PDF_JS}</script></body></html>
"""


def fill_pending_from_plan(report: TestReport, run_dir: Path) -> None:
    """옛 실행(판정에 남은 단계가 없다)이면 실행 폴더의 plan.json 에서 채운다.

    멈춘 뒤 단계는 2026-11-19 부터 판정에 실린다(Verdict.pending_steps). 그 전의 실행도 계획 파일이
    옆에 있으면 같은 재현 절차를 보일 수 있다. 없거나 읽지 못하면 실행한 단계까지만 보인다.
    """
    stuck = [v for v in report.cases
             if not v.pending_steps and any(r.status == "error" for r in v.step_results)]
    if not stuck:
        return
    try:
        plan = json.loads((Path(run_dir) / "plan.json").read_text(encoding="utf-8"))
        by_id = {c.get("case_id"): c for c in plan.get("all_cases") or []}
    except (OSError, ValueError):
        return
    for v in stuck:
        case = by_id.get(v.case_id)
        if not case:
            continue
        done_setup = sum(1 for r in v.step_results if r.phase == "setup")
        done_test = sum(1 for r in v.step_results if r.phase != "setup")
        rest = ([("setup", x) for x in (case.get("setup_steps") or [])[done_setup:]]
                + [("test", x) for x in (case.get("steps") or [])[done_test:]])
        v.pending_steps = [{"action": x.get("action", ""), "target": x.get("target", ""),
                            "value": x.get("value"), "phase": phase} for phase, x in rest]


def save_planner_html(report: TestReport, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fill_pending_from_plan(report, out_dir)
    path = out_dir / PLANNER_FILE
    path.write_text(render_planner_html(report, build_spec_figures(report, out_dir)), encoding="utf-8")
    return path


def build_from_run_dir(run_dir: Path) -> Path:
    """이미 끝난 실행(report.json)에서 기획자용 보고서를 만든다 — 이 기능 전의 실행에도."""
    data = json.loads((Path(run_dir) / "report.json").read_text(encoding="utf-8"))
    return save_planner_html(TestReport.model_validate(data), run_dir)
