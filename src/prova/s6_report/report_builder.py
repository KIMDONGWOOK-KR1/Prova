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
import math
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from prova.models import CaseSelection, SpecDocument, TestReport, Verdict
from prova.s6_report.spec_figures import build_spec_figures
from prova.theme import TOKENS_CSS
# 전략 이름 -> 사람이 읽는 설명. 표를 dom_locator 에 두는 이유는 전략 이름을
# 만드는 곳과 같은 파일이라야 새 전략을 추가할 때 눈에 들어오기 때문이다 —
# 실제로 2차 경로(vlm)가 생긴 뒤에도 그 표에 vlm 이 빠져 있었다.
from prova.s2_case_generator.rule_expander import RULE_LABELS
from prova.s3_grounder.dom_locator import strategy_label
from prova.wording import (ACTION_LABELS, copy_text, missing_names, not_blocked_sentence,
                            rule_subject, source_cells, source_sentence, step_sentence,
                            stop_reason)

#: 모델이 남긴 경고에 붙는 접두어 (extractor._label_model_warnings). 리포트·터미널이
#: 이것으로 '코드가 확인한 경고' 와 '모델이 한 말' 을 갈라 보여 준다.
MEMO_PREFIX = "모델 메모:"

# 스텝 표의 동작·상태. 코드 이름(fill·ok)은 코드를 아는 사람만 읽는다.
# (동작 이름표는 prova.wording 이 갖는다 — 엑셀·계획 화면과 같은 낱말을 쓴다.)
STATUS_LABELS = {"ok": "성공", "error": "오류"}

# 실패 원인 코드 -> 사람이 읽는 이름과 설명 (명세서 §6)
#: 인쇄(PDF 저장) 때는 접힌 카드·통과 목록·단계 기록을 모두 펼친다 — 종이에는 [펼치기] 가
#: 없어서, 접힌 채 인쇄하면 실패 카드의 근거가 빠진 문서가 된다. 인쇄가 끝나면 원래대로.
_PRINT_JS = """(function () {
  var opened = [], theme = null, root = document.documentElement;
  window.addEventListener('beforeprint', function () {
    // 종이는 늘 밝은 화면이다 — 어두운 화면으로 보던 중이어도 검은 바탕으로 찍히지 않게.
    theme = root.getAttribute('data-theme'); root.setAttribute('data-theme', 'light');
    opened = [];
    // 통과 케이스는 한 줄씩 목록으로 둔다 — 다 펼치면 같은 단계와 캡처가 케이스마다 되풀이된다.
    document.querySelectorAll('details:not([open])').forEach(function (d) {
      if (d.classList.contains('case') && d.closest('.passfold')) return;
      d.open = true; opened.push(d);
    });
  });
  window.addEventListener('afterprint', function () {
    if (theme) root.setAttribute('data-theme', theme); else root.removeAttribute('data-theme');
    opened.forEach(function (d) { d.open = false; });
    opened = [];
  });
})();"""

# 밝게 / 어둡게 — 파일로 연 리포트에는 웹 UI 의 버튼이 없어 PC 설정을 따라 어둡게만 나왔다(2026-11-19).
# 웹 UI 의 버튼과 같은 말·같은 저장 키(prova-theme)를 쓴다. 웹 UI 안에서는 위쪽 막대째 숨는다.
# 2026-11-25 hh: 21st.dev 'Liquid Toggle' · 'Liquid Glass Theme Toggle' 의 움직임을 이 스위치에 옮겼다 —
# 누르면 손잡이가 길어지고, 끌면 앞 끝이 먼저 가서 늘어났다가 반을 훌쩍 넘기면 반대쪽으로 넘어간다.
# 물(WebGL)·유리 굴절·소리·떨어지는 물방울은 빼고, 색은 모두 토큰이다. 이름은 늘 '어둡게', 상태는 켬/끔.
_SUN = ("<svg viewBox='0 0 16 16'><circle cx='8' cy='8' r='2.7'/>"
        "<path d='M8 1.9v1.3M8 12.8v1.3M1.9 8h1.3M12.8 8h1.3M3.7 3.7l.9.9M11.4 11.4l.9.9M3.7 12.3l.9-.9M11.4 4.6l.9-.9'/></svg>")
_MOON = "<svg viewBox='0 0 16 16'><path d='M13 9.7A5.3 5.3 0 1 1 6.3 3a4.2 4.2 0 0 0 6.7 6.7Z'/></svg>"
THEME_BUTTON = ("<button class='theme' id='themeBtn' type='button' role='switch' aria-checked='false'>"
                "<span class='tg' aria-hidden='true'><i class='tg-fill'></i>"
                f"<i class='tg-ico sun'>{_SUN}</i><i class='tg-ico moon'>{_MOON}</i>"
                f"<i class='tg-knob'><i class='k-sun'>{_SUN}</i><i class='k-moon'>{_MOON}</i></i></span>"
                "<span>어둡게</span></button>")
# 글자 로고 'prova' — 웹 UI 사이드바와 같은 선(index.html .wm). 색은 토큰(--accent-blue), 리터럴 없음. hh 11-25.
_WORDMARK = ("<svg class='wm' viewBox='0 0 357.4 100' role='img' aria-label='Prova'>"
             "<path fill-rule='evenodd' d='M10.1 100c-5.4-0.8-9.2-4.7-9.9-10.2c-0.1-1-0.2-14.6-0.2-39.3c0.1-41.9 0-38.4 1.4-41.2c4.1-8.3 15.9-9.4 21.5-2.1l0.8 1 1.4-1.1c14.9-12 38.8-7.8 49.5 8.6c4.5 6.8 6.4 13.7 6.4 22.5c0 14.8-7.2 27.9-18.9 34.5c-9.4 5.3-21 6.1-30.8 2.2c-2.2-0.9-5.8-3-7.1-4.2l-0.5-0.5-0.2 1.3c0 0.8-0.1 5.2-0.1 9.9c0 7.8 0 8.7-0.4 10.1c-1.4 5.6-7.2 9.4-12.9 8.5zM166.3 78.1c-7.4-1-15-4.5-20.3-9.1c-19.3-16.9-16.7-47.9 5.2-62.3c11.2-7.4 25.9-8.6 37-3c1.7 0.9 1.8 0.9 0.8 1.6c-0.8 0.6-3.2 3-4.5 4.6c-1.8 2.2-3.9 6-5.3 9.5c-0.4 0.9-0.7 1.6-0.7 1.6c0 0-0.8-0.1-1.6-0.3c-9.1-1.6-16.9 2.2-20.9 10.2c-5.2 10.2 0.4 22.8 11.5 26.1c2.2 0.7 6.8 0.8 9.2 0.2c8.1-1.9 14.3-9.9 14.3-18.4c0-4.9-1.4-8.8-4.7-12.6l-1.4-1.7 0.4-1.4c1.8-7.5 7.3-13.8 14.1-15.9c3.7-1.1 8.8-1.3 12.3-0.3c5.9 1.6 10.3 5.1 14.8 11.9c2.6 4.1 8 14.4 12.9 24.6c0.6 1.5 1.2 2.6 1.3 2.6c0.1 0 1-1.6 2-3.7c1-2 2.7-5.6 3.9-8c1.2-2.5 2.2-4.5 2.2-4.6c0-0.1 2.4-4.9 8.8-18.1l3-6.1 1.7-1.6c6.9-6.8 18.2-3.7 19.9 5.4c0.2 1.2 0.5 0.5-5.8 13.4c-2.9 5.9-4.9 9.9-8 16.4c-0.7 1.5-2.1 4.4-3.1 6.4c-1 2-2.7 5.5-3.8 7.9c-4.1 8.6-7.6 15.5-8.3 16.6c-3.8 5.6-11.4 7.9-17.8 5.4c-4.3-1.7-6.3-4-9-10.2c-1.9-4.3-3.5-8.1-4.8-11c-0.5-1.3-2.2-5.1-3.7-8.5c-1.4-3.4-3.2-7.5-3.9-9.1c-1.3-3.1-2.3-5-2.6-5c-0.1 0-0.2 2.7-0.3 6c-0.1 6.5-0.3 8.3-1.5 12.4c-3.9 13.4-14.6 23.9-28 27.3c-4 1-11.1 1.4-15.3 0.8zM308.6 78.1c-8-1-14.3-3.8-19.8-8.7c-18.1-16.3-16.4-47.9 3.4-62.4c8.4-6.2 20.1-8.5 30.2-5.9c4 1 7.6 2.8 10.3 5.2l1.8 1.7 1-1.3c1.5-2.2 4.4-4 7.3-4.6c6.3-1.4 12.5 2.3 14.3 8.4c0.6 1.8 0.7 55.8 0.2 58.4c-0.8 4.1-4.1 7.6-8.2 8.8c-1.9 0.6-5.6 0.5-7.3-0.1c-3.8-1.5-6.5-4.3-7.4-7.9c-0.2-0.5-0.3-1-0.3-1c0-0.1-0.7 0.6-1.6 1.5c-5.1 4.9-12.1 7.7-19.9 7.9c-1.8 0-3.6 0-4 0zM92.7 76.1c-4-1-7.3-4.3-8.4-8.4c-0.4-1.4-0.5-53.7-0.1-55.6c0.8-4.1 4-7.8 8.2-9.2c6-2.1 13.1 0.7 15.4 6.1l0.4 0.8 0.9-1c6-6.6 16.8-9.4 23.4-6.2c4.2 2 6.3 5.5 6 10c-0.2 3.6-1.7 6.1-4.9 8.2c-2.3 1.5-3.2 1.6-9.2 1.8c-5.2 0.1-5.3 0.1-7.1 0.7c-5 1.8-8.5 5.9-9.5 11.5c-0.2 0.9-0.3 6-0.4 17.1c-0.1 13.9-0.2 15.9-0.4 16.6c-1.6 3.9-4.5 6.6-8.3 7.6c-1.5 0.4-4.4 0.4-6 0zM319.6 56.9c6.6-1.4 11.9-6.3 13.9-13c0.8-2.5 0.8-7.1 0.1-9.6c-2.5-8.8-10.5-14.5-19.1-13.5c-7.5 0.8-13.3 5.8-15.5 13.3c-0.7 2.3-0.7 7.2 0 9.7c2.4 9 11.7 14.9 20.6 13.1zM43.1 56.5c3.8-0.6 6.6-1.9 9.4-4.6c7.9-7.3 7.9-19.3-0.1-26.6c-8.1-7.4-20.5-5.6-26.4 4c-2 3.2-2.7 6.5-2.5 10.7c0.4 10.1 9.8 18 19.6 16.5z'/></svg>")
# 받기 단추의 그림 — 웹 UI 도구 막대의 ICON.download 와 같은 선 그림.
_ICON_DOWNLOAD = ("<svg viewBox='0 0 16 16' aria-hidden='true'><path d='M8 2.5v8M5 7.5l3 3 3-3M3 13h10'/></svg>")
# PDF 는 서버가 받을 때 만든다(/api/report/<실행>/pdf). 파일로 연 리포트(폴더째 받은 사람)에는 서버가 없어
# 단추를 숨긴 채 둔다 — 서버가 준 주소(/runs/<실행>/report.html)로 열렸을 때만 보인다.
_PDF_BTN_JS = r"""(function () {
  var b = document.getElementById('pdfBtn');
  var m = /\/runs\/([^/]+)\/report\.html$/.exec(location.pathname);
  if (!b || !m || !/^https?:$/.test(location.protocol)) return;
  b.href = '/api/report/' + m[1] + '/pdf'; b.hidden = false;
})();"""

_THEME_BTN_JS = """(function () {
  var btn = document.getElementById('themeBtn'), root = document.documentElement;
  if (!btn) return;
  var knob = btn.querySelector('.tg-knob'), fill = btn.querySelector('.tg-fill');
  var sun = btn.querySelector('.tg-ico.sun'), moon = btn.querySelector('.tg-ico.moon');
  var ks = btn.querySelector('.k-sun'), km = btn.querySelector('.k-moon');
  var still = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  var W = 46, PAD = 2, KW = 24, GROW = 6, TRAVEL = W - 2 * PAD - KW;
  function dark() {
    var set = root.getAttribute('data-theme');
    if (set === 'light' || set === 'dark') return set === 'dark';
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
  function setDark(on) {
    root.setAttribute('data-theme', on ? 'dark' : 'light');
    try { localStorage.setItem('prova-theme', on ? 'dark' : 'light'); } catch (e) {}
    btn.setAttribute('aria-checked', String(on));
  }
  // 손잡이의 두 끝(L·R)이 따로 따라간다. 가는 쪽 끝이 빨라서 움직이는 동안만 늘어난다(임계 감쇠 — 넘치지 않는다).
  // p 는 놓일 자리(0 밝게 · 1 어둡게), q 는 그림이 따라가는 값(해·달이 돌며 바뀐다).
  var s = { L: { x: 0, v: 0 }, R: { x: 0, v: 0 }, p: 0, q: 0, press: false, drag: null, moved: false, raf: 0, last: 0 };
  function goal() {
    var l = PAD + s.p * TRAVEL, r = l + KW;
    if (s.press) { if (s.p < 0.5) r += GROW; else l -= GROW; }   // 누르면 가운데 쪽으로 길어진다
    return [l, r];
  }
  function paint() {
    var l = s.L.x, r = Math.max(s.R.x, l + 12), q = s.q;
    knob.style.width = (r - l) + 'px';
    knob.style.transform = 'translateX(' + l + 'px)';
    fill.style.width = (r + PAD) + 'px';
    fill.style.opacity = Math.min(1, q * 1.4);
    // 손잡이가 늘어나 덮기 시작하면 바탕의 해·달은 잘린 채 보이지 않게 먼저 사라진다
    sun.style.opacity = q * Math.max(0, Math.min(1, (l - 16) / 4));
    moon.style.opacity = (1 - q) * Math.max(0, Math.min(1, (30 - r) / 4));
    ks.style.opacity = 1 - q; km.style.opacity = q;
    ks.style.transform = 'rotate(' + (q * 90) + 'deg) scale(' + (1 - q * 0.5) + ')';
    km.style.transform = 'rotate(' + ((q - 1) * 90) + 'deg) scale(' + (0.5 + q * 0.5) + ')';
  }
  function step(dt) {
    var g = goal(), calm = true;
    [[s.L, g[0], false], [s.R, g[1], true]].forEach(function (e) {
      var b = e[0], x = e[1], lead = e[2] === (x > b.x), w = lead ? 34 : 22;
      var off = b.x - x, slope = b.v + w * off, d = Math.exp(-w * dt);
      b.x = x + (off + slope * dt) * d; b.v = (b.v - w * slope * dt) * d;
      if (Math.abs(b.x - x) > 0.2 || Math.abs(b.v) > 2) calm = false;
    });
    s.q += (s.p - s.q) * Math.min(1, dt * 16);
    if (Math.abs(s.p - s.q) > 0.003) calm = false; else s.q = s.p;
    return calm;
  }
  function go() {
    if (still && still.matches) {
      var g = goal(); s.L.x = g[0]; s.R.x = g[1]; s.L.v = s.R.v = 0; s.q = s.p; paint(); return;
    }
    if (s.raf) return;
    s.last = performance.now();
    var tick = function (now) {
      var dt = Math.min((now - s.last) / 1000, 1 / 30); s.last = now;
      var calm = step(dt); paint();
      s.raf = calm && !s.drag ? 0 : requestAnimationFrame(tick);
    };
    s.raf = requestAnimationFrame(tick);
  }
  function settle() { s.p = dark() ? 1 : 0; go(); }
  btn.addEventListener('pointerdown', function (e) {
    if (e.button !== 0) return;
    s.drag = { id: e.pointerId, x0: e.clientX, p0: s.p }; s.moved = false; s.press = true;
    try { btn.setPointerCapture(e.pointerId); } catch (err) {}
    go();
  });
  btn.addEventListener('pointermove', function (e) {
    if (!s.drag || s.drag.id !== e.pointerId) return;
    var dx = e.clientX - s.drag.x0;
    if (!s.moved && Math.abs(dx) > 3) s.moved = true;
    if (!s.moved) return;
    s.p = Math.max(0, Math.min(1, s.drag.p0 + dx / TRAVEL));
    // 반을 훌쩍 넘기면 그 자리에서 넘어간다 — 되돌아 끌면 다시 넘어온다(0.68 · 0.32 로 사이를 둔다)
    if (!dark() && s.p > 0.68) setDark(true); else if (dark() && s.p < 0.32) setDark(false);
    go();
  });
  function end(e) {
    if (!s.drag || s.drag.id !== e.pointerId) return;
    s.drag = null; s.press = false; settle();
  }
  btn.addEventListener('pointerup', end);
  btn.addEventListener('pointercancel', end);
  btn.addEventListener('click', function () {      // 누름 · 스페이스 · 엔터
    if (s.moved) { s.moved = false; return; }
    setDark(!dark()); settle();
  });
  btn.addEventListener('keydown', function (e) {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault(); setDark(e.key === 'ArrowRight'); settle();
  });
  s.p = s.q = dark() ? 1 : 0;
  var g0 = goal(); s.L.x = g0[0]; s.R.x = g0[1];
  btn.setAttribute('aria-checked', String(dark()));
  paint();
})();"""

CATEGORY_LABELS = {
    "element_not_found": ("화면에서 못 찾음", "화면에서 조작할 요소를 찾지 못했습니다."),
    "input_error": ("입력 불가", "요소를 찾았으나 조작할 수 없었습니다 (가림·비활성)."),
    "assertion_mismatch": ("기획서와 다름", "실행은 됐으나 기획서의 기대와 다릅니다."),
    "timeout": ("시간 초과", "대기 시간을 초과했습니다."),
    "page_error": ("페이지 오류", "페이지를 열지 못했거나(접속 실패·HTTP 오류) JS 콘솔 예외가 있습니다."),
    "unknown": ("원인 미분류", "규칙으로 분류되지 않았습니다."),
    "unverifiable": ("확인 불가", "결과를 확인할 근거를 얻지 못했습니다 (조작 전부터 있던 "
                     "문구, 읽지 못한 선택 항목 등). 결함도 통과도 아닙니다."),
    "precondition_failed": ("전제 미충족", "전제(로그인)를 세우지 못했습니다. 이 화면의 결함이 "
                            "아닙니다 — 로그인 화면의 결과를 먼저 확인하세요."),
}


def build_report(
    run_id: str,
    target_url: str,
    verdicts: list[Verdict],
    doc: SpecDocument | None = None,
    coverage: list[str] | None = None,
    spec_source: str = "",
    backend: str = "",
    selection: CaseSelection | None = None,
    design_mismatches: list[str] | None = None,
    session_file: str = "",
    plan: dict | None = None,
    sut_build: str = "",
    url_note: str = "",
    vlm: str | None = None,
) -> TestReport:
    """판정 목록을 TestReport 로 집계한다."""
    summary = TestReport.summarize(verdicts)
    # 실패 중 진짜 결함(기획서와 다름)의 수. 나머지는 실행 문제다 — 웹 UI 가 이 수로
    # 빨강(결함)과 보라(실행 문제)를 가른다. 전부 빨강이면 개발사에 잘못 따진다.
    summary["defects"] = sum(1 for v in verdicts if v.verdict == "FAIL"
                             and v.failure_category == "assertion_mismatch")
    # 확인 불가는 결함도 실행 문제도 아니다(요구서 4절 2번) — 따로 세어 회색으로 보인다.
    summary["unverifiable"] = sum(1 for v in verdicts if v.verdict == "FAIL"
                                  and v.failure_category == "unverifiable")

    # 어떤 백엔드로 실행했는지 남긴다. mock 으로 돌린 리포트를 실제 실행 결과로
    # 착각하면 QA 도구로서 최악의 사고가 된다.
    summary["llm_backend"] = backend
    if doc is not None:
        # 문서 경고와 화면별 경고를 한 곳에 모은다. 화면이 여럿이면 경고 앞에
        # [화면 ID] 가 붙어 어디를 고쳐야 하는지가 드러난다 (all_warnings 참고).
        summary["spec_warnings"] = doc.all_warnings
        summary["screen_names"] = {s.screen_id: s.screen_name for s in doc.screens}
        if doc.screens and all(s.source_kind == "figma" for s in doc.screens):
            # 입력 출처를 리포트가 말해야 한다 — figma 입력은 검증 규칙·성공
            # 조건을 담지 않으므로, 초록불이 '전부 확인됨' 으로 읽히면 안 된다.
            # 전체가 figma 일 때만이다 — 병합 문서는 규칙 검증이 있으므로
            # '정적 대조만' 상자가 거짓말이 된다(불일치 상자가 따로 말한다).
            summary["input_kind"] = "figma"
    # 확인하지 않은 것. 통과율과 나란히 놓여야 '통과' 의 범위를 알 수 있다.
    if coverage:
        summary["coverage_gaps"] = list(coverage)
    # 기획↔디자인 불일치 (병합 모드). 케이스가 전부 초록이어도 보여야 한다 —
    # 구현을 고치기 전에 입력끼리의 모순부터 정리해야 하므로.
    if design_mismatches:
        summary["design_mismatches"] = list(design_mismatches)
    # 세션 파일로 실행됐다는 사실 — 판정의 전제 조건이므로 리포트가 말해야 한다.
    if session_file:
        summary["session_file"] = session_file
    # 두 단계 실행(계획 저장 → 재개) 기록. 추출과 실행이 다른 시점·다른 서버에서
    # 일어났다는 사실은 판정의 전제이므로 리포트가 말해야 한다.
    if plan:
        summary["plan"] = dict(plan)
    # 무엇을 상대로 쟀는가. 어긋남은 실행 자체를 막으므로 여기 남는 값은 '일치'
    # 아니면 '확인 불가' 인데, 그 둘의 구별이 나중에 "이 FAIL 이 구현 결함인가
    # 낡은 대상인가" 를 되물을 때의 답이다. 확인을 안 한 실행은 칸을 만들지
    # 않는다 — '확인했더니 도장이 없더라' 와 다른 사실이다.
    if sut_build:
        summary["sut_build"] = sut_build
    if url_note:
        summary["url_note"] = url_note
    # 2차 경로(화면 이미지로 찾기)를 켰는가. '탐지 실패' 가 이미지로도 못 찾은
    # 것인지, 시도하지 않은 것인지는 이 칸이 가른다. 꺼진 것('')도 남긴다 —
    # 칸이 없는 것은 '기록되기 전의 리포트' 라는 다른 사실이다.
    if vlm is not None:
        summary["vlm"] = vlm
    # 2차 경로를 끈 채로 요소를 못 찾은 케이스의 수. 끈 실행은 필요한 상황이 와도 스스로
    # 켜지지 않으므로, '켜서 다시 돌려 볼 만하다' 는 것을 리포트가 말해 준다. 0 이면 칸을
    # 만들지 않는다. 기록이 없는 옛 리포트(vlm 이 None)에서는 끈 것인지 알 수 없어 세지 않는다.
    if vlm == "":
        missed = sum(1 for v in verdicts
                     if v.verdict == "FAIL" and v.failure_category == "element_not_found")
        if missed:
            summary["not_found_without_vlm"] = missed

    return TestReport(
        run_id=run_id,
        target_url=target_url,
        spec_source=spec_source,
        summary=summary,
        cases=verdicts,
        created_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        selection=selection,
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

# 색·간격·서체는 theme.TOKENS_CSS 가 유일한 출처다. 여기서 색을 새로 만들면
# 웹 UI 안에 iframe 으로 떴을 때 같은 화면에 파란색이 두 가지가 된다.
_CSS = TOKENS_CSS + """
/* 리포트 글꼴 — 리포트 폴더의 fonts/ 에 함께 둔 Pretendard 가변 글꼴(save_html 이 복사한다). 받는 사람 PC 에
   깔려 있으면 그것을 먼저 쓴다. 인터넷에서 내려받지 않는다 — 스크린샷처럼 폴더째 따라간다(디자인 기준 4번). */
@font-face { font-family:"Pretendard Variable"; font-style:normal; font-weight:45 920; font-display:swap;
             src:local("Pretendard Variable"), url("fonts/PretendardVariable.woff2") format("woff2-variations"),
                 url("fonts/PretendardVariable.woff2") format("woff2"); }
/* 검수 문서처럼 읽히게 한다 — 상자 대신 가는 선, 색은 판정에만 쓴다.
   기획자가 개발사에 그대로 보내는 문서라서 화면보다 종이에 가깝게 잡았다. */
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text);
       font-family:var(--font-doc); font-size:var(--tx-base); line-height:var(--lh-normal);
       -webkit-font-smoothing:antialiased; }
a { color:inherit; text-underline-offset:2px; }
/* 폭과 바깥 여백은 웹 UI 의 무대(.app)와 같다 — 파일로 열어도 같은 자리에 선다. */
.wrap { max-width:1148px; margin:0 auto; padding:var(--sp-8) var(--sp-6) var(--sp-12); }
/* 웹 UI 안에 들어가면 바깥 여백을 UI 가 준다 — 두 번 주면 좌우 선이 어긋난다. */
.embedded .wrap { max-width:none; padding:var(--sp-2) 0 var(--sp-8); }

/* 리포트 파일의 머리는 웹 UI 결과 화면과 같은 부품을 같은 순서로 쓴다 — 위쪽 막대, 결론 제목,
   비율 막대, 집계 한 줄. 기획자가 화면에서 본 것과 개발사에 보낸 파일이 같은 문서로 읽힌다.
   규칙은 app.css 의 .topbar · .result-head · .btn · .meter · .tally 와 값을 맞춘다. */
/* 위쪽 막대 — 웹 UI 의 창 도구 막대와 같은 재질(--bg-bar)·높이. 왼쪽 이름, 가운데 기획서 → 대상, 오른쪽 때. */
.topbar { display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:var(--sp-4);
          height:52px; padding:0 var(--sp-6); border-bottom:1px solid var(--sep); background:var(--bg-bar);
          font-size:var(--tx-sm); line-height:var(--lh-sm); position:sticky; top:0; z-index:5;
          -webkit-backdrop-filter:saturate(1.6) blur(20px); backdrop-filter:saturate(1.6) blur(20px); }
.crumbs { display:flex; gap:var(--sp-2); align-items:center; min-width:0; color:var(--muted); }
.crumbs > * { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.crumbs b { color:var(--text); font-weight:600; flex:none; max-width:100%; }
.topbar .name { order:-1; display:flex; align-items:center; align-self:stretch;
                padding-right:var(--sp-4); border-right:1px solid var(--sep); }
/* 글자 로고 18px — x-height 가운데가 막대 가운데에 오도록 조금 내린다 */
.topbar .name .wm { display:block; width:64px; height:18px; margin-top:4px; fill:var(--accent-blue); }
.topbar .when { justify-self:end; color:var(--muted); font-variant-numeric:tabular-nums;
                display:flex; align-items:center; gap:var(--sp-3); white-space:nowrap; }
/* 어둡게 스위치 — 이름표 + 스위치(46×26). 켜진 쪽은 강조색이 손잡이 뒤를 따라 찬다.
   움직임은 _THEME_BTN_JS. 아래 [aria-checked] 규칙은 스크립트가 그리기 전의 모습. */
button.theme { display:inline-flex; align-items:center; gap:var(--sp-2); height:var(--ctl-md); padding:0 2px;
               border:0; background:none; font:inherit; font-size:var(--tx-sm); font-weight:500; color:var(--text);
               cursor:pointer; touch-action:pan-y; -webkit-user-select:none; user-select:none; }
button.theme:focus-visible { outline:none; }
button.theme:focus-visible .tg { box-shadow:var(--focus-ring); }
.tg { position:relative; flex:none; width:46px; height:26px; border-radius:var(--r-full); overflow:hidden;
      background:var(--fill-track); box-shadow:inset 0 0 0 0.5px var(--fill-hover); }
.tg i { position:absolute; display:block; }
.tg-fill { left:0; top:0; bottom:0; width:28px; border-radius:inherit; background:var(--accent-solid); opacity:0; }
.tg-ico { top:6px; width:14px; height:14px; color:var(--fg-muted); }
.tg-ico.sun { left:6px; color:var(--fg-onaccent); opacity:0; }
.tg-ico.moon { right:6px; }
.tg-knob { left:0; top:2px; width:24px; height:22px; border-radius:var(--r-full); background:var(--fg-onaccent);
           box-shadow:var(--shadow-control); transform:translateX(2px); }
.tg-knob > i { inset:0; margin:auto; width:14px; height:14px; }
.tg-knob .k-sun { color:var(--fg-muted); }
.tg-knob .k-moon { color:var(--accent-solid); opacity:0; }
.tg svg { display:block; width:100%; height:100%; fill:none; stroke:currentColor; stroke-width:1.5;
          stroke-linecap:round; stroke-linejoin:round; }
button.theme[aria-checked='true'] .tg-knob { transform:translateX(20px); }
button.theme[aria-checked='true'] .tg-fill { width:46px; opacity:1; }
button.theme[aria-checked='true'] .tg-ico.sun, button.theme[aria-checked='true'] .k-moon { opacity:1; }
button.theme[aria-checked='true'] .tg-ico.moon, button.theme[aria-checked='true'] .k-sun { opacity:0; }
.result-head { display:flex; justify-content:space-between; align-items:flex-start; gap:var(--sp-4);
               flex-wrap:wrap; margin-bottom:var(--sp-5); }
/* 결론 한 줄 — 웹 UI 결과 화면의 .verdict-line 과 같은 크기. 판정 부분은 바탕 없이 판정 색 글자. */
h1 { font-size:var(--tx-xl); line-height:var(--lh-xl); font-weight:700; letter-spacing:-0.015em; margin:0;
     word-break:keep-all; text-wrap:balance; }
h1 mark { background:none; padding:0; color:inherit; }
h1 mark.fail { color:var(--fail-fg); } h1 mark.infra { color:var(--note-fg); }
h1 mark.unv { color:var(--unv-fg); } h1 mark.pass { color:var(--pass-fg); }
.result-head .cond { font-size:var(--tx-md); line-height:var(--lh-para); color:var(--muted); margin-top:6px; }
.actions { display:flex; gap:var(--sp-2); flex-wrap:wrap; }
.btn { display:inline-flex; align-items:center; gap:6px; font:inherit; font-size:var(--tx-md); font-weight:500;
       height:var(--ctl-lg); padding:0 14px; border-radius:var(--r-full); border:0;
       background:var(--bg-raised); color:var(--text); box-shadow:var(--shadow-control);
       text-decoration:none; white-space:nowrap; cursor:pointer; transition:background-color var(--dur-1) var(--ease-out); }
.btn svg { width:16px; height:16px; fill:none; stroke:currentColor; stroke-width:1.4; stroke-linecap:round; stroke-linejoin:round; }
.btn:hover { background:var(--bg-hover); }
.btn[hidden] { display:none; }
.btn:focus-visible { outline:none; box-shadow:var(--focus-ring); }
/* 원형차트(도넛) + 이름표 — 결함 · 실행 문제 · 확인 불가 · 약한 확인 · 통과 순, 12시에서 시계 방향.
   웹 UI 결과 화면(.donut)과 같은 그림이다. 숫자는 이름표와 아래 한 줄이 글자로 말한다. */
/* 웹 UI 결과 화면의 숫자 칸(.tiles)과 같은 모양 — 도넛 칸 하나 + 판정마다 칸 하나. 칸은 묶음 상자
   (3% 채움, 모서리 12). 이름표가 칸이 된다: 색 점 + 이름 위, 큰 수 아래, 비율은 수 옆에 작게. */
.chart { display:grid; grid-template-columns:auto minmax(0,1fr); gap:var(--sp-3); margin-bottom:var(--sp-5); }
.chart svg { flex:none; display:block; width:88px; height:88px; }
.chart > svg { box-sizing:content-box; padding:14px var(--sp-5); border-radius:var(--r-card);
               background:var(--fill-group); box-shadow:inset 0 0 0 0.5px var(--fill-hover); }
.chart text { text-anchor:middle; fill:var(--text); font-variant-numeric:tabular-nums; }
/* 도넛은 132 칸 그림을 88px 로 줄여 놓는다 — 글자 크기는 그림 단위라 2/3 로 줄어든다(32→21px, 16→11px). */
.chart .big { font-size:32px; font-weight:700; letter-spacing:-0.02em; }
.chart .small { font-size:16px; fill:var(--muted); }
.chart .track { stroke:var(--fill-track); }
.chart .seg.defect { stroke:var(--chart-defect); } .chart .seg.infra { stroke:var(--chart-infra); }
.chart .seg.unv { stroke:var(--chart-unv); } .chart .seg.weak { stroke:var(--chart-weak); }
.chart .seg.pass { stroke:var(--chart-pass); }
/* 이름표 칸들은 도넛 칸과 같은 줄, 집계 한 줄은 그 아래 전체 폭 */
.chart .side { display:contents; }
.chart .tally, .chart p.ms { grid-column:1 / -1; margin:0; }
.legend li.zero b { color:var(--muted); }
.legend { list-style:none; margin:0; padding:0; display:grid; gap:var(--sp-3);
          grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); }
.legend li { display:flex; flex-wrap:wrap; align-items:baseline; align-content:space-between; column-gap:6px;
             padding:14px var(--sp-4) var(--sp-4); border-radius:var(--r-card);
             background:var(--fill-group); box-shadow:inset 0 0 0 0.5px var(--fill-hover);
             font-variant-numeric:tabular-nums; min-width:0; }
.legend li > .swatch { align-self:center; flex:none; }
/* 이름이 첫 줄을 다 쓴다 — 수와 비율은 둘째 줄로 내려간다 */
.legend li > span:not(.ms) { flex:1 0 calc(100% - 14px); font-size:var(--tx-xs); line-height:var(--lh-xs);
                             color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.legend b { margin-top:6px; font-size:var(--tx-2xl); line-height:36px; font-weight:700; letter-spacing:-0.02em; }
.legend .ms { font-size:var(--tx-sm); color:var(--muted); }
.swatch { width:8px; height:8px; border-radius:var(--r-full); }
.swatch.defect { background:var(--chart-defect); } .swatch.infra { background:var(--chart-infra); }
.swatch.unv { background:var(--chart-unv); } .swatch.weak { background:var(--chart-weak); }
.swatch.pass { background:var(--chart-pass); }
.tally { font-size:var(--tx-md); font-variant-numeric:tabular-nums; color:var(--muted); }
.chart p { margin:var(--sp-1) 0 0; }
/* 웹 UI 가 위쪽 막대·결론·숫자·같은 알림을 이미 보인다 — 한 화면에 두 번 나오지 않게 한다. */
.embedded .topbar, .embedded .result-head, .embedded .chart, .embedded .dup,
.embedded .meta, .embedded .metanote { display:none; }
/* 실행 조건 — 다시 돌려 볼 사람이 찾는 값이라 문서 끝에 둔다. 이름과 값을 한 칸씩 나눈 격자. */
.meta { display:grid; grid-template-columns:repeat(auto-fill, minmax(200px, 1fr)); gap:0 24px;
        margin-top:var(--sp-12); padding-top:6px; border-top:1px solid var(--line); }
.mi { padding:8px 0; min-width:0; color:var(--muted); font-size:12px; }
.mi code { display:block; margin-top:2px; font-family:var(--font-mono); font-size:13px;
           color:var(--text); word-break:break-all; }
.metanote { color:var(--muted); font-size:13px; margin:10px 0 0; }
/* 틀린 곳 목록 — 한 줄에 번호 · 항목 이름 · 일어난 일 · 어긴 규칙. 번호는 아래 카드의 번호와 같다. */
.flist { margin:var(--sp-8) 0 0; }
.flist .cap { font-size:var(--tx-base); font-weight:650; padding-bottom:var(--sp-2);
              border-bottom:1px solid var(--text); }
.flist.defect .cap { color:var(--fail); }
.flist.infra .cap { color:var(--note-fg); }
.flist.unv .cap { color:var(--muted); }
.frow { display:grid; grid-template-columns:28px 130px minmax(0,1fr) auto; gap:12px; align-items:baseline;
        padding:9px 0; border-bottom:1px solid var(--line); color:inherit; text-decoration:none; }
.frow:hover { background:var(--bg-hover); }
.frow .who { font-weight:600; word-break:keep-all; }
.frow .rule { font-size:var(--tx-md); color:var(--muted); }
/* 멈춘 이유가 같은 건의 묶음 — 이유는 머리에 한 번, 줄에는 확인하려던 것. */
.fwhy { padding:10px 0 6px; font-size:var(--tx-md); color:var(--muted); line-height:1.6; }
.fwhy b { color:var(--note-fg); font-weight:650; margin-right:8px; }
.fgroup { border-bottom:1px solid var(--line); }
.fgroup .frow { padding-left:12px; }
.fgroup .frow:last-child { border-bottom:0; }
/* 화면별 확인 범위 — 화면마다 그림 한 장과 그 화면의 결과·못 본 것·주의. */
.scope-note { color:var(--muted); font-size:13px; margin:0 0 8px; }
.scope { border-top:1px solid var(--line); }
.scr { display:grid; grid-template-columns:112px minmax(0,1fr); gap:16px; padding:12px 0;
       border-bottom:1px solid var(--line); align-items:start; }
.shots.scr-t { display:block; margin:0; }
.shots.scr-t img { display:block; width:112px; height:70px; object-fit:cover; object-position:top; }
.shots.scr-t .cap { display:none; }
.scr-t.none { width:112px; height:70px; border:1px dashed var(--line); border-radius:var(--r-sm); }
.scr.unseen .scr-t img { opacity:.55; }
.scr-h { display:flex; flex-wrap:wrap; gap:4px 14px; align-items:baseline; }
.scr-h > b { font-weight:650; }
.scr-n { font-size:13px; color:var(--muted); }
.scr-n .n.defect { color:var(--fail); font-weight:600; }
.scr-n .n.infra { color:var(--note-fg); font-weight:600; }
.scr-n .unseen { color:var(--text); font-weight:650; }
.scr-l { font-size:13px; margin-top:4px; line-height:1.6; }
.scr-l b { font-weight:600; margin-right:6px; }
.scr-more { margin-top:6px; font-size:13px; color:var(--muted); line-height:1.6; }
.scr-more > summary { cursor:pointer; }
.scr-more[open] > summary { margin-bottom:4px; }
.scr-more.all { margin:12px 0 0; }
@media (max-width:640px) { .scr { grid-template-columns:72px minmax(0,1fr); gap:10px; }
  .shots.scr-t img, .scr-t.none { width:72px; height:46px; } }
/* 이름 대조 — 못 찾은 이름과 찾은 이름. */
.cmp .src .miss { color:var(--fail); font-weight:600; }
/* 시안·화면 쌍 — 판정하지 않고 나란히 둔다. */
.shots.pair { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin:8px 0 20px; }
.shots.pair img { width:100%; height:auto; aspect-ratio:16/10; object-fit:cover; object-position:top; }
.shots.pair .cap { text-align:left; font-size:12px; }
@media (max-width:640px) { .shots.pair { grid-template-columns:1fr; } }
.no { font-weight:700; font-variant-numeric:tabular-nums; }
.no.defect { color:var(--fail); } .no.infra { color:var(--note-fg); } .no.unv { color:var(--muted); }
@media (max-width:640px) { .frow { grid-template-columns:28px minmax(0,1fr); }
  .frow .what, .frow .rule { grid-column:2; } }
.case { scroll-margin-top:16px; }
button.copy { font:inherit; font-size:var(--tx-sm); font-weight:500; margin-left:auto; height:var(--ctl-md); padding:0 12px;
              border-radius:var(--r-full); transition:background-color var(--dur-1) var(--ease-out);
              border:0; box-shadow:var(--shadow-control); background:var(--bg-raised); color:var(--text); cursor:pointer; }
button.copy:hover { background:var(--bg-hover); }
button.copy:focus-visible { outline:none; box-shadow:var(--focus-ring); }
@media (prefers-reduced-motion: reduce) { button.copy, button.copy:hover, button.copy:active { transition:none; transform:none; } }
/* 통과는 접어 둔다 — 확인할 것이 없는 줄이 실패와 같은 무게로 이어지지 않게. */
details.passfold > summary { list-style:none; cursor:pointer; display:flex; align-items:baseline; gap:12px;
                             border-bottom:1px solid var(--sep); margin-top:var(--sp-10); }
details.passfold > summary:hover .ms { color:var(--text); }
details.passfold > summary:focus-visible { outline:none; box-shadow:var(--focus-ring); border-radius:var(--r-sm); }
details.passfold > summary::-webkit-details-marker { display:none; }
details.passfold > summary h2 { border:none; margin:0; padding-bottom:8px; }
details.passfold[open] .ms { visibility:hidden; }
/* 섹션 머리 — 웹 UI 의 묶음 머리줄과 같은 크기, 아래 굵은 선. */
h2 { font-size:var(--tx-base); line-height:var(--lh-title); font-weight:700; margin:var(--sp-10) 0 0;
     padding-bottom:var(--sp-2); border-bottom:1px solid var(--sep); }
/* 케이스는 상자가 아니라 줄이다 — 계획 화면의 목록과 같은 모양. */
.case { border-bottom:1px solid var(--line); }
.case > summary { padding:12px 0; cursor:pointer; display:flex; gap:8px;
                  align-items:center; list-style:none; }
.case > summary::-webkit-details-marker { display:none; }
/* 꼬리표 — 웹 UI 와 같은 알약(높이 20). 판정 꼬리표만 판정 색이고, 규칙 이름은 회색. */
.tag { display:inline-block; height:20px; line-height:20px; padding:0 8px; border-radius:var(--r-full);
       font-size:var(--tx-xs); font-weight:500; white-space:nowrap; vertical-align:middle; }
.tag.PASS { background:var(--pass-bg); color:var(--pass); }
.tag.FAIL { background:var(--fail-bg); color:var(--fail); }
.tag.rule { background:var(--fill-hover); color:var(--muted); }
.tag.cat.defect { background:var(--fail-bg); color:var(--fail-fg); font-weight:600; }
/* 실행 문제는 보라다 — 비율 막대의 '실행 문제' 와 같은 색이어야 한다. */
.tag.cat.infra { background:var(--note-bg); color:var(--note-fg); font-weight:600; }
.tag.cat.weak { background:var(--warn-bg); color:var(--warn-fg); }
/* 확인 불가 — 결함(빨강)도 실행 문제(보라)도 아니다. 무채색 + 점선 테두리로 '판정 없음' 을 보인다. */
.tag.cat.unv { background:var(--bg-inset); color:var(--text); box-shadow:inset 0 0 0 1px var(--line); }
.tag.revised { background:var(--bg-inset); color:var(--text); }
.breakdown { color:var(--muted); font-size:13px; margin:-8px 0 16px; }
.title { flex:1; }
.ms { color:var(--muted); font-size:12px; font-variant-numeric:tabular-nums; }
.body { padding:0 0 24px; }
/* 화면 흐름 지도 — 흐름 실패 카드 맨 위. 웹 화면(app.css .flowmap)과 같은 모양이고 끊긴 곳만 판정 색 + 글자.
   실선 = 요소를 눌러 옮김, 점선 = 주소로 바로 들어감(잇는 요소는 확인하지 않음). */
.flowmap { list-style:none; margin:0 0 var(--sp-4); padding:var(--sp-3) 0; display:flex; align-items:center;
           overflow-x:auto; }
.fm-node { flex:none; position:relative; display:grid; gap:2px; min-width:104px; padding:var(--sp-2) var(--sp-3);
           border:1px solid var(--border-strong); border-radius:var(--r-md); background:var(--card); }
.fm-node b { font-size:13px; font-weight:640; white-space:nowrap; }
.fm-node i, .fm-edge i { font-style:normal; font-size:11px; font-weight:600; }
.fm-node:not(:first-child)::before, .fm-node:not(:last-child)::after { content:""; position:absolute; top:50%;
           width:7px; height:7px; margin-top:-4px; border:1px solid var(--border-strong); border-radius:var(--r-full);
           background:var(--card); }
.fm-node:not(:first-child)::before { left:-4px; } .fm-node:not(:last-child)::after { right:-4px; }
.fm-edge { flex:1 1 0; min-width:128px; max-width:240px; position:relative; display:grid; grid-template-rows:1fr 1fr;
           justify-items:center; height:56px; padding:0 var(--sp-3); }
.fm-edge::before { content:""; position:absolute; left:4px; right:5px; top:50%; border-top:1px solid var(--fg-subtle); }
.fm-edge::after { content:""; position:absolute; right:6px; top:50%; width:6px; height:6px; margin-top:-3px;
           border-top:1px solid var(--fg-subtle); border-right:1px solid var(--fg-subtle); transform:rotate(45deg); }
/* 이동 방법은 선 위, 끊김 표시는 선 아래 — 바탕을 칠해 선을 끊지 않는다 */
.fm-edge span { align-self:end; margin-bottom:5px; padding:0 var(--sp-2); font-size:12px; white-space:nowrap; }
.fm-edge i { grid-row:2; align-self:start; margin-top:5px; }
.fm-edge[data-via="url"]::before { border-top-style:dashed; }
.fm-edge[data-via="url"] span { color:var(--muted); }
.fm-node[data-state="ok"] i { color:var(--pass-fg); }
.fm-node[data-state="unreached"] { border-style:dashed; border-color:var(--line); }
.fm-node[data-state="unreached"] b, .fm-node[data-state="unreached"] i { color:var(--muted); font-weight:500; }
.fm-edge[data-state="unreached"]::before, .fm-edge[data-state="unreached"]::after { border-color:var(--line); }
/* 끊긴 곳 — 카드의 실패 분류와 같은 색(결함 빨강, 실행 문제 보라, 확인 불가 회색) */
.flowmap { --fm-hit:var(--fail); --fm-hit-bg:var(--fail-bg); }
.flowmap.infra { --fm-hit:var(--note-fg); --fm-hit-bg:var(--note-bg); }
.flowmap.unv { --fm-hit:var(--text); --fm-hit-bg:var(--bg-inset); }
.fm-node[data-state="broken"] { border-color:var(--fm-hit); background:var(--fm-hit-bg); }
.fm-node[data-state="broken"] i, .fm-edge[data-state="broken"] span, .fm-edge[data-state="broken"] i { color:var(--fm-hit); }
.fm-edge[data-state="broken"]::before { border-top:2px solid var(--fm-hit); margin-top:-1px; }
.fm-edge[data-state="broken"][data-via="url"]::before { border-top-style:dashed; }
.fm-edge[data-state="broken"]::after { border-color:var(--fm-hit); }
@media (max-width:640px) {
  .flowmap { flex-direction:column; align-items:stretch; overflow:visible; }
  .fm-node::before, .fm-node::after { display:none; }
  .fm-edge { min-width:0; max-width:none; height:auto; min-height:44px; justify-items:start;
             grid-template-rows:none; align-content:center; padding:var(--sp-2) 0 var(--sp-2) var(--sp-8); }
  .fm-edge span, .fm-edge i { grid-row:auto; align-self:auto; margin:0; padding:0; }
  .fm-edge::before { left:var(--sp-5); right:auto; top:0; bottom:2px; border-top:0; border-left:1px solid var(--fg-subtle); }
  .fm-edge[data-via="url"]::before { border-left-style:dashed; }
  .fm-edge[data-state="broken"]::before { border-top:0; border-left:2px solid var(--fm-hit); margin:0 0 0 -1px; }
  .fm-edge[data-state="broken"][data-via="url"]::before { border-left-style:dashed; }
  .fm-edge[data-state="unreached"]::before { border-color:var(--line); }
  .fm-edge::after { left:calc(var(--sp-5) - 3px); right:auto; top:auto; bottom:3px; transform:rotate(135deg); }
}
/* 실패 카드 — 대제목이 맨 위, 분류·규칙 꼬리표와 케이스 제목은 그 아래 작은 한 줄. */
/* 번호는 왼쪽 칸에 따로 선다 — 제목·꼬리표·비교 칸이 같은 세로선에서 시작한다. */
.case.failed > summary { flex-wrap:wrap; row-gap:8px; padding:var(--sp-6) 0 var(--sp-3) 36px; position:relative;
                          align-items:center; }
.case.failed > summary .no { position:absolute; left:0; top:var(--sp-6); font-size:var(--tx-lg); line-height:26px; }
.case.failed > .body { padding-left:36px; }
@media (max-width:640px) { .case.failed > .body { padding-left:0; } }
.case .head { word-break:keep-all; flex:1 1 calc(100% - 160px); font-size:var(--tx-lg); font-weight:700; line-height:26px;
              letter-spacing:-0.01em; }
.case.failed .title { color:var(--muted); font-size:var(--tx-sm); }
table.kv { width:100%; border-collapse:collapse; margin-bottom:12px; }
table.kv th { text-align:left; width:110px; vertical-align:top; color:var(--muted);
              font-weight:400; padding:5px 8px 5px 0; font-size:13px; }
table.kv td { padding:5px 0; word-break:break-all; }
table.kv code { font-family:var(--font-mono); font-size:12px; }
.steps, .screens { border-collapse:collapse; font-size:13px; }
.steps { width:100%; }
.screens { margin:14px 0 4px; }
.steps th, .steps td, .screens th, .screens td {
  border-bottom:1px solid var(--sep); padding:7px 16px 7px 0; text-align:left; font-variant-numeric:tabular-nums; }
.steps th, .screens th { font-weight:600; font-size:var(--tx-xs); color:var(--muted);
                         border-bottom-color:var(--border-default); }
.steps td.err { color:var(--fail); }
.steps td.val { font-family:var(--font-mono); font-size:12px; word-break:break-all; }
/* 요약 줄 — 분류 꼬리표가 있으면 FAIL 은 겹치는 말이다. 소요 시간은 기획자가 읽지 않는다. */
.case summary .tag.FAIL:has(+ .tag.cat) { display:none; }
.case > summary .ms { display:none; }
details.raw { margin-top:12px; overflow-x:auto; }
details.raw > summary { cursor:pointer; color:var(--muted); font-size:var(--tx-sm); padding:6px 0; width:max-content; }
details.raw > summary:hover { color:var(--text); }
details.raw .url { font-size:12px; color:var(--muted); margin:6px 0 10px; }
details.raw .url code { font-family:var(--font-mono); }
h4 { font-size:var(--tx-xs); line-height:var(--lh-xs); color:var(--muted); font-weight:600; margin:0 0 6px; }
/* 기획서와 실제 화면을 나란히 — 이 도구가 하는 대조를 그대로 보여 준다.
   왼쪽 칸에 기대·근거·재현 절차, 오른쪽 칸에 관찰·판정한 화면·그때의 주소가 든다. */
/* 두 칸은 웹 UI 결과 화면의 '기대' · '실제' 상자와 같다 — 왼쪽 묶음 상자(3% 채움), 오른쪽은 판정 색 바탕.
   선으로 가른 한 상자가 아니라 떨어진 두 상자다. */
.cmp { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:var(--sp-3); margin:var(--sp-1) 0 var(--sp-4);
       align-items:start; }
.cmp > div { padding:14px var(--sp-4) var(--sp-4); min-width:0; border-radius:var(--r-card);
             background:var(--fill-group); box-shadow:inset 0 0 0 0.5px var(--fill-hover); }
.cmp.FAIL > .got { background:var(--fail-bg); box-shadow:none; }
.cmp.infra > .got { background:var(--note-bg); }
.cmp.unv > .got { background:var(--fill-hover); }
.cmp p { margin:0; word-break:break-word; }
.cmp h4 + p { font-size:var(--tx-base); line-height:var(--lh-para); word-break:keep-all; overflow-wrap:anywhere; }
.cmp h4 ~ h4 { margin-top:var(--sp-5); }
.cmp.defect > .got > h4:first-child { color:var(--fail-fg); }
.cmp.infra > .got > h4:first-child { color:var(--note-fg); }
/* 기획서 근거 — 기획서 표의 그 줄을 표 모양 그대로 옮긴다. 판정에 쓴 칸만 진하게. */
table.src { width:100%; margin-top:var(--sp-3); border-collapse:separate; border-spacing:0;
            font-size:var(--tx-xs); line-height:var(--lh-xs); border-radius:var(--r-sel); overflow:hidden;
            background:var(--bg-surface); box-shadow:inset 0 0 0 1px var(--border-default); }
table.src caption { text-align:left; color:var(--muted); padding-bottom:6px; }
table.src caption b { font-weight:600; color:var(--text); margin-right:6px; }
table.src td { padding:6px 8px; vertical-align:top; color:var(--muted); border-left:1px solid var(--border-default);
               word-break:keep-all; overflow-wrap:break-word; }
table.src td:first-child { border-left:0; }
table.src td.hit { color:var(--text); font-weight:600; background:var(--fill-hover); }
@media (max-width:640px) { table.src, table.src caption, table.src tbody, table.src tr { display:block; }
  table.src td { display:inline-block; margin:0 -1px -1px 0; } }
.cmp .src { font-size:var(--tx-sm); line-height:var(--lh-sm); color:var(--muted); margin-top:10px; }
.cmp .src b { font-weight:600; margin-right:6px; }
.cmp code { font-family:var(--font-mono); font-size:12px; word-break:break-all; }
@media (max-width:640px) { .cmp { grid-template-columns:1fr; }
  .cmp > .got { border-left:0; border-top:1px solid var(--line); } }
.repro { margin:var(--sp-1) 0 0; padding-left:22px; font-size:var(--tx-md); line-height:var(--lh-para); color:var(--muted); }
.repro li { padding:1px 0; }
.repro li::marker { font-variant-numeric:tabular-nums; }
/* 여덟 단계 가운데 일곱은 케이스마다 같다 — 기획서를 어긴 단계만 진하게 둔다. */
.repro li.broke { color:var(--text); font-weight:600; }
.repro em.broke { font-size:var(--tx-2xs); font-weight:600; background:var(--fail-bg); padding:1px 7px;
                  border-radius:var(--r-full); margin-left:4px; white-space:nowrap; }
.repro .pre { font-size:11px; color:var(--muted); border:1px solid var(--line); border-radius:var(--r-sm); padding:0 5px; }
.repro em { font-style:normal; font-size:13px; color:var(--fail); }
/* 멈춘 단계 — 어긴 단계와 같은 무게. 꼬리표는 실행 문제의 색(보라)이다. 뒤의 단계는 실행하지 못했다. */
.repro em.stop { font-size:var(--tx-2xs); font-weight:600; color:var(--note-fg); background:var(--note-bg);
                 padding:1px 7px; border-radius:var(--r-full); margin-left:4px; white-space:nowrap; }
.repro li.todo { opacity:.55; }
.repro-note { font-size:12px; color:var(--muted); margin:6px 0 0 22px; }
/* 다시 돌릴 때의 요령처럼 판정을 바꾸지 않는 안내 — 상자 없이 작은 글씨. */
.smallnote { font-size:13px; line-height:1.6; color:var(--muted); margin:12px 0 0; word-break:keep-all; }
.smallnote b { color:var(--text); font-weight:600; }
.smallnote + .warn, .smallnote + .heal, .smallnote + .gap { margin-top:32px; }
/* 참고 — 실패·통과 케이스 아래의 압축판. 이름 한 칸, 내용 한 칸, 상자 없음. */
h2.brief-h { margin-top:var(--sp-12); }
ul.brief { list-style:none; margin:0; padding:0; font-size:var(--tx-md); line-height:var(--lh-para); }
ul.brief li { display:grid; grid-template-columns:200px minmax(0,1fr); gap:4px 16px; padding:10px 0;
              border-bottom:1px solid var(--sep); word-break:keep-all; color:var(--muted); }
ul.brief li > b { color:var(--text); font-weight:600; }
ul.brief .nos a { color:inherit; }
@media (max-width:640px) { ul.brief li { grid-template-columns:1fr; } }
details.pairfold { margin-top:16px; }
details.pairfold > summary { cursor:pointer; font-size:14px; color:var(--muted); padding:6px 0; }
details.pairfold > summary:focus-visible { outline:none; box-shadow:var(--focus-ring); }
details.pairfold h2 { display:none; }
.shots.last { margin-top:12px; }
.shots.last a { display:block; width:max-content; max-width:100%; }
/* 판정한 화면 — 칸 폭에 맞추되 높이는 240px 까지. 넘치면 줄여 담는다(누르면 원본). 오른쪽 칸만 길어져
   왼쪽 기획서 칸 아래가 비던 것을 줄인다. */
.shots.last a > img { display:block; width:auto; max-width:100%; height:auto; max-height:240px;
                      border:1px solid var(--border-default); border-radius:var(--r-sel); }
.shots.last .cap { text-align:left; font-size:var(--tx-xs); margin-top:6px; }
.shots { display:flex; gap:10px; flex-wrap:wrap; margin-top:14px; }
.shots a { display:block; cursor:zoom-in; text-decoration:none; }
.shots img { height:120px; border:0; border-radius:var(--r-sel); box-shadow:inset 0 0 0 1px var(--border-default);
             background:var(--gray-0); display:block; }
.shots .cap { font-size:11px; color:var(--muted); text-align:center; margin-top:3px; }
/* 단계 되짚기 — 21st.dev Agent Trace 에서. 단계 한 줄, 시간 축 막대, 끄는 재생선. 색은 토큰만.
   이름 칸 · 막대 칸 · 시간 칸. 재생선과 끄는 면은 막대 칸에만 겹친다. */
.trace { --tr-hit:var(--fail); --gut:9.5rem; --msw:3.4rem; --gap:8px; }
.trace.infra { --tr-hit:var(--note-fg); }
.trace.unv { --tr-hit:var(--muted); }
.tr-body { position:relative; margin-top:12px; }
.tr-rows { list-style:none; margin:0; padding:0; }
.tr-rows > li { display:grid; grid-template-columns:var(--gut) minmax(0,1fr) var(--msw); gap:var(--gap);
                align-items:center; height:24px; font-size:var(--tx-xs); }
.tr-name { font:inherit; color:var(--text); background:none; border:0; margin:0; padding:2px 6px 2px 2px;
           text-align:left; cursor:pointer; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
           border-radius:var(--r-sm); transition:background-color .15s ease-out, color .15s ease-out; }
.tr-name .n { display:inline-block; min-width:2.6em; color:var(--muted); font-variant-numeric:tabular-nums; }
button.tr-name:hover, .tr-rows > li[data-on] .tr-name { background:var(--bg-inset); }
.tr-rows > li[data-on] .tr-name { font-weight:600; }
button.tr-name:focus-visible, .tr-scrub:focus-visible { outline:none; box-shadow:var(--focus-ring); }
.tr-track { position:relative; height:100%; }
.tr-bar { position:absolute; top:50%; height:8px; margin-top:-4px; min-width:3px; border-radius:4px;
          background:var(--bg-inset); overflow:hidden; }
.tr-bar > i { position:absolute; inset:0; transform-origin:left center; transform:scaleX(var(--p,1));
              background:var(--muted); }
.tr-rows > li.setup .tr-bar > i { background:var(--border-strong); }
.tr-rows > li[data-fin='error'] .tr-bar > i, .tr-rows > li[data-state='error'] .tr-bar > i { background:var(--tr-hit); }
.tr-ms { text-align:right; font-family:var(--font-mono); font-size:11px; color:var(--muted);
         font-variant-numeric:tabular-nums; transition:opacity .15s ease-out; }
.tr-rows > li[data-state='error'] .tr-ms { color:var(--tr-hit); font-weight:600; }
.tr-rows > li[data-state='queued'] .tr-name, .tr-rows > li[data-state='skip'] .tr-name { color:var(--muted); }
.tr-rows > li[data-state='queued'] .tr-ms { opacity:0; }
.tr-rows > li[data-state='skip'] .tr-name { cursor:default; }
.tr-head, .tr-scrub { position:absolute; top:0; bottom:0; left:calc(var(--gut) + var(--gap));
                      right:calc(var(--msw) + var(--gap)); }
.tr-head { pointer-events:none; }
.tr-head > i { position:absolute; top:-6px; bottom:0; left:calc(var(--t,1) * 100%); width:1px; background:var(--text); }
.tr-head > i::before { content:""; position:absolute; top:0; left:-3px; width:7px; height:7px;
                       background:var(--text); transform:rotate(45deg); }
.tr-scrub { cursor:ew-resize; touch-action:none; border-radius:var(--r-sm); }
.tr-foot { display:flex; justify-content:space-between; font-family:var(--font-mono); font-size:11px;
           color:var(--muted); margin:2px calc(var(--msw) + var(--gap)) 0 calc(var(--gut) + var(--gap)); }
.tr-rows > li.broke .tr-name { color:var(--tr-hit); font-weight:600; }
@media (max-width:640px) { .trace { --gut:7.5rem; } }
@media print { .tr-head, .tr-scrub { display:none; } }
/* 알림 상자 — 색 블록 하나, 테두리 없음. 종류는 색과 굵은 첫 줄이 함께 말한다. */
/* 웹 UI 의 알림 상자(.alert)와 같다 — 모서리 12, 바탕 색 한 겹, 테두리 없음. 숨기거나 접지 않는다. */
.heal, .gap, .warn { border-radius:var(--r-card); padding:14px var(--sp-4); margin-bottom:var(--sp-3);
                     font-size:var(--tx-md); line-height:var(--lh-para); }
.warn b, .heal b, .gap b { font-size:var(--tx-md); font-weight:600; }
/* 주의 알림의 세모 — 웹 UI 알림과 같은 그림. 색은 토큰으로 칠하고 그림은 가리개로만 쓴다. */
.warn { position:relative; padding-left:44px; }
.warn::before { content:""; position:absolute; left:16px; top:17px; width:16px; height:16px;
                background:var(--warn-fg); -webkit-mask:var(--warn-icon) center / contain no-repeat;
                mask:var(--warn-icon) center / contain no-repeat; }
:root { --warn-icon:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='none' stroke='black' stroke-linejoin='round' stroke-linecap='round'%3E%3Cpath d='M8 2.2l6 10.6H2z' stroke-width='1.4'/%3E%3Cpath d='M8 6.4v3M8 11.2v.1' stroke-width='1.6'/%3E%3C/svg%3E"); }
.heal { background:var(--note-bg); }
.heal b { color:var(--note-fg); }
.gap { background:var(--info-bg); }
/* 주의 알림 — 웹 UI 의 .alert.warn 과 같은 옅은 주의 바탕. 세모는 주의 색. */
.warn { background:var(--warn-bg); }
.warn b { display:block; margin-bottom:2px; }
.heal .why, .gap .why { color:var(--muted); margin:2px 0 8px; }
.empty { color:var(--muted); padding:12px 0; }
.screens td.n { text-align:right; font-variant-numeric:tabular-nums; }
.screens td.f { color:var(--fail); font-weight:700; }
.screens td.k { color:var(--muted); font-size:12px; }
.screens code { font-family:var(--font-mono); font-size:12px; color:var(--muted); }
h3.grp { font-size:13px; margin:20px 0 0; color:var(--muted); font-weight:650; }
@media (max-width:640px) {
  .wrap { padding:var(--sp-6) var(--sp-4) var(--sp-10); }
  h1 { font-size:25px; }
  .topbar { grid-template-columns:minmax(0,1fr) auto; padding:var(--sp-3) var(--sp-4); }
  .topbar .name { order:-1; } .topbar .when > span, .crumbs span { display:none; } .crumbs { display:none; }
}
@media (prefers-reduced-motion: reduce) { .btn, .btn:hover, .btn:active { transition:none; transform:none; } }
/* 인쇄 — 실패 카드는 한 쪽보다 길 때가 많아 카드째 끊지 않으면 앞 쪽이 빈다. 카드 안의 덩어리만 지킨다
   (PDF 받기도 같은 규칙, pdf_export._PDF_CSS). */
@media print { .actions, button.copy, button.theme { display:none; }
  .topbar { position:static; background:none; -webkit-backdrop-filter:none; backdrop-filter:none; }
  h2, h3.grp, .case > summary, h4 { break-after:avoid; }
  .chart, .warn, .cmp > div > p, table.src, .repro li, .trace, .shots.last, .shots a, .steps tr,
  .case:not([open]) { break-inside:avoid; } }
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
    # '오류' 칸은 오류가 있을 때만 그린다 — 늘 비어 있는 칸은 표만 넓힌다.
    has_err = any(r.error_detail for r in verdict.step_results)
    for r in verdict.step_results:
        detail = r.error_detail or ""
        # 원시 전략 이름(label·role·vlm)을 그대로 찍으면 코드를 아는 사람만 읽는다.
        strategy = strategy_label(r.location.strategy if r.location else None)
        cls = " class='err'" if r.status == "error" else ""
        # DOM 스냅샷을 링크한다. 스텝마다 저장하면서 리포트에 링크가 없어 아무도
        # 열어 볼 수 없었다 — 탐지 실패를 조사할 때 가장 필요한 자료다.
        evidence = (f"<a href='{_esc(r.dom_snapshot)}'>화면 구조</a>"
                    if r.dom_snapshot else "")
        # 전제(setup)와 본 스텝(test)을 구분해 보여준다. 둘 다 seq 가 1부터
        # 따로 매겨지므로(nodes._run_case_steps 참고) 열이 없으면 "스텝 3" 이
        # 어느 단계의 3번인지 표만 봐서는 알 수 없다 — models.py 의 phase
        # 필드가 "리포트가 구분해 보여준다" 고 약속한 자리가 여기다.
        phase_label = "준비" if r.phase == "setup" else "실행"
        rows.append(
            f"<tr><td>{_esc(phase_label)}</td><td>{r.seq}</td>"
            f"<td>{_esc(ACTION_LABELS.get(r.action, r.action))}</td><td>{_esc(r.target)}</td>"
            # 넣은 값. 없으면 실패를 개발자에게 넘길 때 손으로 재현할 수 없다.
            f"<td class='val'>{_esc(r.value) if r.value is not None else ''}</td>"
            f"<td>{_esc(strategy)}</td><td{cls}>{_esc(STATUS_LABELS.get(r.status, r.status))}</td>"
            f"<td>{r.elapsed_ms}ms</td>"
            + (f"<td{cls}>{_esc(detail)}</td>" if has_err else "") +
            f"<td>{evidence}</td></tr>"
        )
    return (
        "<table class='steps'><thead><tr><th>단계</th><th>#</th><th>동작</th><th>대상</th><th>값</th>"
        "<th>찾은 방법</th><th>결과</th><th>소요</th>"
        + ("<th>오류</th>" if has_err else "") + "<th>자료</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


# 스크린샷을 누르면 새 탭이 아니라 화면 위에 크게 띄운다 (2026-11-12).
#
# 실패 카드를 읽다가 캡처를 확인하려고 탭을 오가면 어느 케이스를 보던 중인지 놓친다.
# 그래서 같은 화면 위에 겹쳐 띄우고 Esc · × · 바깥 누르기로 닫는다. 좌우 화살표로 같은
# 케이스의 앞뒤 스텝을 넘긴다.
#
# 웹 UI 는 리포트를 iframe 안에 넣는다. iframe 안에서만 띄우면 리포트 칸 크기에 갇히므로,
# 같은 출처의 바깥 문서에 닿을 수 있으면 거기에 띄워 브라우저 창 전체를 쓴다. 닿지 못하면
# (파일로 열었거나 다른 출처에 끼워 넣은 경우) 리포트 자기 문서에 띄운다.
#
# 바깥 문서에는 리포트의 CSS 가 없으므로 모양은 전부 요소에 직접 적는다. 링크의 href 는
# 그대로 둔다 — 스크립트가 막힌 곳에서는 예전처럼 새 탭으로 열리고, Ctrl·가운데 버튼으로
# 누르면 지금도 새 탭이다.
# 웹 UI 에서 밝게/어둡게를 골랐으면 리포트도 같은 쪽으로 연다. 같은 서버에서 열릴 때만
# 저장소가 보이므로, 파일로 받아 연 리포트는 전처럼 보는 사람의 화면 설정을 따른다.
_THEME_JS = (
    'try{var t=localStorage.getItem("prova-theme");'
    'if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}'
    'catch(e){}'
)

# 실패 카드의 단계 되짚기(_trace_html). 시각 하나(t)에서 모든 줄의 찬 정도·상태·캡처를 정한다 —
# 줄마다 따로 상태를 들고 있지 않다. 처음과 인쇄 때는 끝(t = 합계)이다.
_TRACE_JS = r"""
(function () {
  document.querySelectorAll('.trace').forEach(function (tr) {
    var total = +tr.dataset.total || 1;
    var rows = Array.prototype.slice.call(tr.querySelectorAll('.tr-rows > li[data-start]'));
    var img = tr.querySelector('.shots img'), link = tr.querySelector('.shots a');
    var cap = tr.querySelector('.shots .cap'), scrub = tr.querySelector('.tr-scrub');
    if (!rows.length || !img || !scrub) return;
    var endCap = cap.textContent, endShot = img.getAttribute('src'), on = null;
    rows.forEach(function (r) { r.dataset.fin = r.dataset.state; });
    function seek(v) {
      var t = Math.max(0, Math.min(total, v)), at = 0;
      tr.style.setProperty('--t', (t / total).toFixed(4));
      rows.forEach(function (r, i) {
        var s = +r.dataset.start, e = +r.dataset.end, d = e - s;
        var p = d > 0 ? Math.max(0, Math.min(1, (t - s) / d)) : (t >= s ? 1 : 0);
        r.style.setProperty('--p', p.toFixed(3));
        r.dataset.state = (t < s || (p === 0 && d > 0)) ? 'queued' : p < 1 ? 'running' : r.dataset.fin;
        if (t > s || (t === s && d === 0)) at = i;
      });
      var end = t >= total, k = at;
      while (k > 0 && !rows[k].dataset.shot) k--;
      var shot = end ? endShot : rows[k].dataset.shot, text = end ? endCap : rows[at].dataset.cap + ' 화면';
      if (img.getAttribute('src') !== shot) { img.setAttribute('src', shot); link.setAttribute('href', shot); }
      if (cap.textContent !== text) cap.textContent = text;
      if (on) on.removeAttribute('data-on');
      on = end ? null : rows[at]; if (on) on.setAttribute('data-on', '');
      scrub.setAttribute('aria-valuenow', String(Math.round(t)));
      scrub.setAttribute('aria-valuetext', end ? '끝, 판정한 화면' : text);
      tr.t = t;
    }
    function fromX(x) {
      var b = scrub.getBoundingClientRect();
      if (b.width > 0) seek((x - b.left) / b.width * total);
    }
    scrub.addEventListener('pointerdown', function (e) { scrub.setPointerCapture(e.pointerId); fromX(e.clientX); });
    scrub.addEventListener('pointermove', function (e) { if (scrub.hasPointerCapture(e.pointerId)) fromX(e.clientX); });
    scrub.addEventListener('pointerup', function (e) {
      if (scrub.hasPointerCapture(e.pointerId)) scrub.releasePointerCapture(e.pointerId);
    });
    // 화살표는 단계 경계로 옮긴다 — 시간 몇 퍼센트씩보다 '다음 단계' 가 쓸모 있다.
    var ends = rows.map(function (r) { return +r.dataset.end; });
    scrub.addEventListener('keydown', function (e) {
      var t = tr.t == null ? total : tr.t, n = null;
      if (e.key === 'ArrowRight' || e.key === 'ArrowUp') n = ends.filter(function (x) { return x > t; })[0];
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') n = ends.filter(function (x) { return x < t; }).pop();
      else if (e.key === 'Home') n = ends[0];
      else if (e.key === 'End') n = total;
      else return;
      e.preventDefault();
      if (n != null) seek(n);
    });
    rows.forEach(function (r) {
      var b = r.querySelector('.tr-name');
      if (b) b.addEventListener('click', function () { seek(+r.dataset.end); });
    });
    window.addEventListener('beforeprint', function () { seek(total); });
  });
})();
"""


_LIGHTBOX_JS = r"""
(function () {
  var host = document;
  try {
    if (window.parent !== window && window.parent.document.body) host = window.parent.document;
  } catch (e) { host = document; }

  var box = null, img = null, cap = null, links = [], at = 0, opener = null, prevOverflow = '';

  function el(tag, css, text) {
    var n = host.createElement(tag);
    n.style.cssText = css;
    if (text) n.textContent = text;
    return n;
  }

  function button(label, text, css, onClick) {
    var b = el('button', 'position:absolute;border:0;border-radius:6px;cursor:pointer;' +
      'background:rgba(255,255,255,.14);color:white;font:inherit;line-height:1;' + css, text);
    b.type = 'button';
    b.setAttribute('aria-label', label);
    b.addEventListener('click', function (e) { e.stopPropagation(); onClick(); });
    return b;
  }

  function show(i) {
    at = (i + links.length) % links.length;
    var a = links[at];
    var label = a.querySelector('.cap');
    var text = label ? label.textContent : '';
    img.src = a.href;
    img.alt = text;
    cap.textContent = links.length > 1 ? text + '  ·  ' + (at + 1) + ' / ' + links.length : text;
  }

  function onKey(e) {
    if (!box) return;
    if (e.key === 'Escape') close();
    else if (e.key === 'ArrowLeft' && links.length > 1) show(at - 1);
    else if (e.key === 'ArrowRight' && links.length > 1) show(at + 1);
    else return;
    e.preventDefault();
  }

  function close() {
    if (!box) return;
    host.removeEventListener('keydown', onKey);
    if (host !== document) document.removeEventListener('keydown', onKey);
    host.documentElement.style.overflow = prevOverflow;
    if (box.parentNode) box.parentNode.removeChild(box);
    box = null;
    if (opener && opener.focus) { try { opener.focus(); } catch (e) {} }
  }

  function open(a) {
    close();
    opener = a;
    var group = a.closest('.shots');
    links = Array.prototype.slice.call((group || document).querySelectorAll('a'));
    box = el('div', 'position:fixed;inset:0;z-index:2147483000;background:rgba(15,18,24,.88);' +
      'display:flex;flex-direction:column;align-items:center;justify-content:center;' +
      'padding:48px 64px 20px;box-sizing:border-box;' +
      'font:14px/1.4 system-ui,-apple-system,"Segoe UI","Malgun Gothic",sans-serif;');
    box.id = 'prova-lightbox';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.setAttribute('aria-label', '스크린샷 크게 보기');
    box.addEventListener('click', function (e) { if (e.target === box) close(); });

    img = el('img', 'max-width:100%;max-height:calc(100% - 36px);object-fit:contain;' +
      'background:var(--gray-0, white);border-radius:4px;box-shadow:0 8px 40px rgba(0,0,0,.5);');
    cap = el('div', 'color:white;margin-top:12px;min-height:20px;text-align:center;');
    var x = button('닫기', '×', 'top:10px;right:14px;width:36px;height:36px;font-size:24px;', close);
    box.appendChild(img);
    box.appendChild(cap);
    box.appendChild(x);
    if (links.length > 1) {
      var side = 'top:50%;transform:translateY(-50%);width:40px;height:64px;font-size:28px;';
      box.appendChild(button('이전 스크린샷', '‹', 'left:12px;' + side, function () { show(at - 1); }));
      box.appendChild(button('다음 스크린샷', '›', 'right:12px;' + side, function () { show(at + 1); }));
    }
    show(Math.max(0, links.indexOf(a)));

    prevOverflow = host.documentElement.style.overflow;
    host.documentElement.style.overflow = 'hidden';
    host.body.appendChild(box);
    host.addEventListener('keydown', onKey);
    if (host !== document) document.addEventListener('keydown', onKey);
    x.focus();
  }

  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('.shots a') : null;
    if (!a || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    open(a);
  });
  // 리포트가 바뀌거나 닫히면 바깥 문서에 띄운 것도 같이 치운다.
  window.addEventListener('pagehide', close);
})();
"""


# '재현 절차 복사' — 클립보드가 막힌 곳(오래된 브라우저·권한 거부)에서는 글을 골라 둔다.
_COPY_JS = r"""
// 틀린 곳 목록의 '보기' — 카드의 대제목이 화면 맨 위에 오게 한다. 웹 UI 안(iframe)에서는
// 브라우저가 바깥 페이지를 대신 스크롤하는데, 위에 붙은 Prova 막대를 모르고 그 밑으로
// 대제목을 밀어 넣는다. 그래서 바깥 페이지를 막대 높이만큼 덜 내려 직접 스크롤한다.
document.addEventListener('click', function (e) {
  var a = e.target.closest && e.target.closest('a.frow');
  if (!a) return;
  var card = document.getElementById(a.getAttribute('href').slice(1));
  if (!card) return;
  e.preventDefault();
  card.open = true;
  var gap = 16, how = matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
  try {
    if (self !== top && window.frameElement) {
      var pw = parent, bar = pw.document.querySelector('.topbar');
      var barH = bar ? bar.getBoundingClientRect().height : 0;
      var y = window.frameElement.getBoundingClientRect().top + pw.scrollY
            + card.getBoundingClientRect().top - barH - gap;
      pw.scrollTo({ top: y, behavior: how });
      return;
    }
  } catch (err) { /* 다른 출처에 들어간 경우 — 아래의 기본 이동 */ }
  window.scrollTo({ top: card.getBoundingClientRect().top + window.scrollY - gap, behavior: how });
});

document.addEventListener('click', function (e) {
  var b = e.target.closest && e.target.closest('button.copy');
  if (!b) return;
  e.preventDefault();
  var text = b.getAttribute('data-copy'), label = b.textContent;
  function done(msg) { b.textContent = msg; setTimeout(function () { b.textContent = label; }, 1800); }
  function fallback() {
    var t = document.createElement('textarea');
    t.value = text; document.body.appendChild(t); t.select();
    var ok = false; try { ok = document.execCommand('copy'); } catch (err) {}
    t.remove(); done(ok ? '복사했습니다' : '복사하지 못했습니다');
  }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(function () { done('복사했습니다'); }, fallback);
  } else { fallback(); }
});
"""


def _shots_html(verdict: Verdict, last: bool = False) -> str:
    shots = [(r.seq, r.screenshot, r.phase) for r in verdict.step_results if r.screenshot]
    # 실패 카드는 판정이 난 마지막 화면 하나만 바로 보인다 — 앞 단계 캡처는 거의 같은 그림이다.
    if last:
        shots = shots[-1:]
    if not shots:
        return ""
    if last:
        # 판정한 순간의 화면 하나를 읽을 수 있는 크기로 — 화면 전체를 줄이면 글자가 안 보인다.
        # 가운데 윗부분을 잘라 보이고, 누르면 원본이 뜬다(라이트박스).
        seq, path, phase = shots[0]
        return (f"<div class='shots last'><a href='{_esc(path)}' target='_blank'>"
                f"<img src='{_esc(path)}' alt='판정한 화면'>"
                f"<div class='cap'>판정한 화면: {'준비 ' if phase == 'setup' else ''}{seq}단계 뒤, 누르면 크게 보기</div></a></div>")
    items = "".join(
        f"<a href='{_esc(path)}' target='_blank'>"
        f"<img src='{_esc(path)}' alt='{seq}단계 화면'>"
        # 준비(setup) 스텝의 스크린샷임을 캡션에서 밝힌다 — steps 표와 같은
        # 이유다. 준비·실행 둘 다 step1.png 부터 다시 시작하므로("step 1"이
        # 두 번 나온다) 접두어가 없으면 어느 단계의 캡처인지 구분할 수 없다.
        f"<div class='cap'>{'준비 ' if phase == 'setup' else ''}{seq}단계</div></a>"
        for seq, path, phase in shots
    )
    return f"<div class='shots'>{items}</div>"


def _trace_html(verdict: Verdict, kind: str, names: dict | None = None) -> str:
    """실패 카드의 '판정한 화면' 자리 — 단계마다 걸린 시간을 한 축에 놓고, 끌면 그 단계 뒤 화면이 뜬다.

    21st.dev Agent Trace 에서 가져온 것: 단계 하나가 한 줄, 시작·끝을 시간 축에 놓은 막대, 축을
    끌면(재생 막대) 그 시각까지 끝난 만큼만 막대가 차고 그 단계 뒤 캡처로 바뀐다. 이름을 누르면
    그 단계로 간다. 화살표 키는 단계 경계로 옮긴다. 버린 것: 자동 재생·반복, 토큰 수, 아이콘,
    그림자 카드.

    처음 모습은 끝난 실행이다 — 판정한 화면과 꽉 찬 막대. 스크립트가 없거나 인쇄할 때도 그 모습이다.
    멈춘 뒤 하지 못한 단계는 막대 없이 '못 함' 으로 남긴다. 캡처가 두 장 미만이면 그릴 것이 없으니
    예전처럼 판정한 화면 한 장만 둔다.
    """
    steps = verdict.step_results
    shots = [r for r in steps if r.screenshot]
    if len(steps) < 2 or len(shots) < 2:
        return _shots_html(verdict, last=True)
    total = max(1, sum(max(r.elapsed_ms, 0) for r in steps))
    last = shots[-1]
    # 재현 절차(_repro_html)가 '기획서를 어긴 단계' 로 진하게 두는 단계와 같은 줄을 짚는다.
    broke = verdict.target_label if kind == "defect" and verdict.violates else None
    names = names or {}

    def what(action: str, target: str) -> str:
        # 흐름 케이스의 화면 경계('signup 성공')는 기획서의 화면 이름으로 — 지도와 같은 말.
        m = _FLOW_MARK.match(target or "")
        if m and m.group(1) in names:
            target = f"{names[m.group(1)]} {m.group(2)}"
        return f"{target or ''} {ACTION_LABELS.get(action, action or '')}".strip()

    rows, t = [], 0
    for i, r in enumerate(steps):
        dur = max(r.elapsed_ms, 0)
        state = "error" if r.status == "error" else "done"
        pre = "준비 " if r.phase == "setup" else ""
        name = what(r.action, r.target)
        hit = bool(broke) and r.phase != "setup" and r.target == broke and r.action != "click"
        cls = " ".join(c for c in ("setup" if r.phase == "setup" else "", "broke" if hit else "") if c)
        rows.append(
            f"<li data-state='{state}' data-start='{t}' data-end='{t + dur}'"
            f"{f' data-shot={chr(39)}{_esc(r.screenshot)}{chr(39)}' if r.screenshot else ''}"
            f" data-cap='{_esc(pre)}{r.seq}단계 뒤' class='{cls}' style='--p:1'>"
            f"<button type='button' class='tr-name'><span class='n'>{_esc(pre)}{r.seq}</span>{_esc(name)}</button>"
            f"<span class='tr-track'><span class='tr-bar' style='left:{t / total * 100:.3f}%;"
            f"width:{dur / total * 100:.3f}%'><i></i></span></span>"
            f"<span class='tr-ms'>{dur}ms</span></li>")
        t += dur
    for k, p in enumerate(verdict.pending_steps or []):
        pre = "준비 " if p.get("phase") == "setup" else ""
        name = what(p.get("action") or "", p.get("target") or "")
        rows.append(f"<li data-state='skip'><span class='tr-name'><span class='n'>·</span>{_esc(name)}</span>"
                    f"<span class='tr-track'></span><span class='tr-ms'>못 함</span></li>")
    cap = f"판정한 화면: {'준비 ' if last.phase == 'setup' else ''}{last.seq}단계 뒤, 누르면 크게 보기"
    return (
        f"<div class='trace {kind}' data-total='{total}' style='--t:1'>"
        f"<div class='shots last'><a href='{_esc(last.screenshot)}' target='_blank'>"
        f"<img src='{_esc(last.screenshot)}' alt='판정한 화면'>"
        f"<div class='cap' aria-live='polite'>{_esc(cap)}</div></a></div>"
        f"<div class='tr-body'><ol class='tr-rows' aria-label='단계별 걸린 시간'>{''.join(rows)}</ol>"
        f"<div class='tr-head' aria-hidden='true'><i></i></div>"
        f"<div class='tr-scrub' role='slider' tabindex='0' aria-label='단계 되짚기 — 끌거나 화살표 키로'"
        f" aria-valuemin='0' aria-valuemax='{total}' aria-valuenow='{total}'"
        f" aria-valuetext='끝, 판정한 화면'></div></div>"
        f"<div class='tr-foot'><span>0</span><span>합계 {total}ms</span></div></div>"
    )


def is_weak_pass(verdict: Verdict) -> bool:
    """성공 조건 없이 '에러가 안 떴다' 만 보고 통과한 케이스인가 (WEAK_PASS_REASON).

    판정은 PASS 로 둔다 — 약하게나마 확인한 것이다. 다만 경로·문구로 확인한 통과와
    같은 모양이면 읽는 사람은 둘을 구별하지 못한다. saucedemo 실측에서는 로그인하지
    않고도 이 모양으로 통과했다(2026-09-23).
    """
    from prova.s5_verifier.assertion_engine import WEAK_PASS_REASON

    return (verdict.verdict == "PASS"
            and (verdict.evidence or {}).get("actual") == WEAK_PASS_REASON)


@dataclass(frozen=True)
class ChartSegment:
    """원형차트 한 조각. 이름은 케이스 카드의 꼬리표와 같은 말을 쓴다."""

    key: str
    label: str
    count: int


def fail_kind(v: Verdict) -> str:
    """실패의 세 갈래 — 기획서와 다름(빨강) · 실행 문제(보라) · 확인 불가(회색)."""
    if v.failure_category == "assertion_mismatch":
        return "defect"
    return "unv" if v.failure_category == "unverifiable" else "infra"


def chart_segments(verdicts: list[Verdict]) -> list[ChartSegment]:
    """판정을 네 조각으로 나눈다. 없는 조각은 뺀다.

    통과·실패 두 조각이면 결함과 도구 실패가 한 색이 되고, 약한 확인이 강한 확인과
    같은 색이 된다. 기획자가 차트만 보고 넘겨도 그 구분은 남아야 한다.
    """
    counts = {"pass": 0, "weak": 0, "defect": 0, "infra": 0, "unv": 0}
    for v in verdicts:
        if v.verdict == "PASS":
            counts["weak" if is_weak_pass(v) else "pass"] += 1
        else:
            counts[fail_kind(v)] += 1
    labels = {"pass": "통과", "weak": "약한 확인", "defect": "기획서와 다름", "infra": "실행 문제",
              "unv": "확인 불가"}
    return [ChartSegment(k, labels[k], n) for k, n in counts.items() if n]


def _donut_svg(n: dict[str, int], labels: dict[str, str], size: int = 132) -> str:
    """도넛 한 개. 외부 라이브러리 없이 SVG 를 문서에 넣는다 (file:// 로 열린다).

    조각 순서는 결함 → 실행 문제 → 확인 불가 → 약한 확인 → 통과, 12시에서 시계 방향.
    조각이 하나면 틈을 두지 않는다 — 끊긴 고리가 뭔가 빠진 것처럼 보인다.
    """
    total = sum(n.values())
    c = size / 2
    width = 16.0
    radius = c - width / 2 - 1
    length = 2 * math.pi * radius
    keys = [k for k in n if n[k]]
    gap = 2.0 if len(keys) > 1 else 0.0
    arcs, offset = [], 0.0
    for k in keys:
        arc = n[k] / total * length
        drawn = max(arc - gap, 0.5)
        tip = f"{labels[k]} {n[k]}건 ({n[k] / total:.0%})"
        arcs.append(
            f"<circle class='seg {k}' cx='{c:g}' cy='{c:g}' r='{radius:.2f}' fill='none' "
            f"stroke-width='{width:g}' stroke-dasharray='{drawn:.2f} {length - drawn:.2f}' "
            f"stroke-dashoffset='{-offset:.2f}'><title>{_esc(tip)}</title></circle>")
        offset += arc
    summary = ", ".join(f"{labels[k]} {n[k]}건" for k in keys)
    return (
        f"<svg viewBox='0 0 {size} {size}' width='{size}' height='{size}' role='img' "
        f"aria-label='전체 {total}건 — {_esc(summary)}'>"
        f"<circle class='track' cx='{c:g}' cy='{c:g}' r='{radius:.2f}' fill='none' stroke-width='{width:g}'/>"
        f"<g transform='rotate(-90 {c:g} {c:g})'>{''.join(arcs)}</g>"
        f"<text x='{c:g}' y='{c + 6:g}' class='big'>{total}</text>"
        f"<text x='{c:g}' y='{c + 27:g}' class='small'>케이스</text></svg>")


def _chart_html(verdicts: list[Verdict], unchecked: int, excluded: int, rate=None) -> str:
    """원형차트(도넛)와 이름표, 집계 한 줄 — 웹 UI 결과 화면의 도넛(.donut)과 같은 그림이다.

    2026-11-18 에 비율 막대로 바꿨다가 11-24 에 원형차트로 되돌렸다(디자인 담당 요청 —
    검사 뒤 결과의 구성이 한눈에 보이던 것이 사라졌다).

    색은 토큰이고 이름과 수가 늘 곁에 글자로 있다. 색만으로 뜻을 전하면 인쇄물과
    색각 이상 독자에게 조각이 구별되지 않는다. 조각에 들어가지 않는 것(실행하지 않은
    것)은 조각으로 만들지 않고 글로 쓴다 — 도넛의 합은 실행한 케이스뿐이어서, 이 줄이
    없으면 온통 초록인 차트가 '전부 확인됨' 으로 읽힌다.
    """
    segments = {s.key: s for s in chart_segments(verdicts)}
    if not segments:
        return ""
    total = sum(s.count for s in segments.values())
    order = ("defect", "infra", "unv", "weak", "pass")
    n = {k: segments[k].count if k in segments else 0 for k in order}
    labels = {k: segments[k].label for k in segments}
    # 이름표는 웹 UI 결과 화면의 숫자 칸과 같은 칸이다. 기획서와 다름·실행 문제·통과는 0 이어도 칸을 둔다
    # — '없다' 도 읽는 사람이 찾는 답이다(아래 집계 줄과 같은 규칙). 0 인 칸은 흐린 글자.
    names = {"defect": "기획서와 다름", "infra": "실행 문제", "unv": "확인 불가", "weak": "약한 확인", "pass": "통과"}
    legend = "".join(
        (f"<li><i class='swatch {k}'></i><span>{_esc(labels[k])}</span>"
         f"<b>{n[k]}</b><span class='ms'>{n[k] / total:.0%}</span></li>") if n[k] else
        (f"<li class='zero'><i class='swatch {k}'></i><span>{names[k]}</span><b>0</b></li>")
        for k in order if n[k] or k in ("defect", "infra", "pass"))
    # 기획서와 다름·실행 문제는 0이어도 적는다 — '없다' 도 읽는 사람이 찾는 답이다 (웹 UI 와 같다).
    parts = [f"기획서와 다름 {n['defect']}", f"실행 문제 {n['infra']}"]
    if n["unv"]:
        parts.append(f"확인 불가 {n['unv']}")
    parts.append(f"통과 {n['pass'] + n['weak']}" + (f" (약한 확인 {n['weak']} 포함)" if n["weak"] else ""))
    if rate is not None:
        parts.append(f"통과율 {rate}%")
    outside = []
    if unchecked:
        outside.append(f"기획서에 적혔으나 확인하지 않은 것 {unchecked}건")
    if excluded:
        outside.append(f"이번 실행에서 제외한 케이스 {excluded}건")
    note = (f"<p class='ms'>차트에 없는 것: {_esc(' · '.join(outside))}</p>" if outside else "")
    return (
        "<div class='chart'>"
        f"{_donut_svg(n, labels)}"
        f"<div class='side'><ul class='legend'>{legend}</ul>"
        f"<div class='tally'>{_esc(' · '.join(parts))}</div>{note}</div></div>"
    )


def _headline(verdict: Verdict) -> tuple[str, str]:
    """실패 카드의 대제목과 사유의 나머지.

    막혀야 하는 입력이 막히지 않은 결함은 실제로 일어난 일로 쓴다('…입력해도 막히지 않습니다').
    그 밖에는 사유의 첫 문장을 쓴다.
    """
    if verdict.verdict != "FAIL" or not verdict.failure_detail:
        return "", ""
    first, _, rest = verdict.failure_detail.partition(". ")
    first = first.removeprefix("기획서에 적힌 ").rstrip(".") + "."
    if verdict.failure_category == "assertion_mismatch" and verdict.plain:
        happened = not_blocked_sentence(verdict.plain)
        if happened:
            return happened + ".", ""
    return first, rest.strip()


def _source_html(source, expected: str, label: str | None = None) -> str:
    """기획서 근거 한 곳 — 기대가 기획서 어디에 적혀 있는지. "그런 말이 어디 있느냐" 에 리포트가 답한다.

    표 행은 표 모양 그대로 옮긴다. 가운뎃점으로 이은 한 줄보다 기획서의 그 줄을 찾기 쉽다.
    """
    sentence = source_sentence(source)
    cells = source_cells(source)
    if not cells:
        return f"<p class='src'><b>기획서 근거</b> {_esc(sentence)}</p>"
    # ponytail: 기대 문장이 따옴표로 그대로 옮긴 칸만 진하게 한다(항목 이름 칸은 뺀다 — 어느
    # 줄인지일 뿐 판정에 쓴 값이 아니다). 선택 목록처럼 문장이 칸을 풀어 쓴 경우는 못 찾아
    # 강조 없이 둔다 — 추출 단계가 칸 위치를 넘겨주면 그것으로 바꾼다.
    hit = max((c for c in cells if c != label and f"'{c}'" in expected), key=len, default=None)
    tds = "".join(f"<td{' class=hit' if c == hit else ''}>{_esc(c)}</td>" for c in cells)
    return (f"<table class='src' aria-label='{_esc(sentence)}'><caption><b>기획서 근거</b>"
            f"{source.page}쪽 표</caption><tr>{tds}</tr></table>")


def _compare_html(verdict: Verdict, kind: str = "", shot: str = "", repro: str = "") -> str:
    """기획서가 말한 것과 실제 화면을 나란히 놓는다.

    표의 두 줄('기대'·'실제')로 두면 위아래로 읽어 견줘야 한다. 이 도구가 하는 일이 바로
    그 대조이므로 한눈에 좌우로 보이게 한다. 기획서 쪽에는 어느 쪽 어느 줄인지(근거)와
    그 기대에 이르는 절차를, 실제 쪽에는 판정한 화면과 그때의 주소를 붙인다 — 캡처를 칸 밖에
    따로 두면 오른쪽 절반이 비고 카드가 한 화면을 넘겼다.

    """
    ev = verdict.evidence or {}
    expected = ev.get("expected")
    sources = "".join(_source_html(s, str(expected or ""), verdict.target_label)
                      for s in verdict.spec_sources)
    url = (f"<p class='src'><b>그때의 주소</b> <code>{_esc(ev.get('url'))}</code></p>"
           if ev.get("url") else "")
    seen = ev.get("actual")
    if kind == "infra" and any(r.status == "error" for r in verdict.step_results):
        # 판정이 남긴 관찰은 '스텝 7 에서 중단' 뿐이다 — 재현 절차가 이미 그 자리를 짚는다.
        # 무엇을 하려다 왜 멈췄는지를 쓴다. 두 리포트 모두 (2026-11-19).
        seen = stop_reason(verdict)[1]
    actual = f"<p>{_esc(seen)}</p>"
    missing, found = missing_names(verdict)
    if missing:
        # 이름 대조(2026-11-19, 기획자용 보고서에서 옮김) — 관찰 문장은 못 찾은 이름과 까닭을 한 줄로
        # 이어 길다. 몇 개 중 몇 개인지를 먼저 크게 쓰고, 이름을 못 찾은 것·찾은 것으로 나눈다.
        # 이름마다의 까닭(없음·후보 여럿)은 원래 문장에 있으니 그대로 남긴다.
        actual = (
            f"<p>{_esc(_names_sentence(missing, found))}</p>"
            "<p class='src'><b>찾지 못함</b>"
            + ", ".join(f"<span class='miss'>{_esc(n)}</span>" for n in missing) + "</p>"
            + (f"<p class='src'><b>확인됨</b>{_esc(', '.join(found))}</p>" if found else "")
            + f"<p class='src'><b>자세히</b>{_esc(ev.get('actual'))}</p>")
    return (
        f"<div class='cmp {verdict.verdict} {kind}'>"
        f"<div class='want'><h4>기획서</h4><p>{_esc(expected)}</p>{sources}{repro}</div>"
        f"<div class='got'><h4>실제 화면</h4>{actual}{shot}{url}</div>"
        "</div>"
    )


def _repro_html(verdict: Verdict, broke: str | None = None) -> str:
    """재현 절차 — 손으로 그대로 따라 할 수 있는 문장으로.

    엑셀의 '재현 절차' 칸과 같은 문장이다(wording.step_sentence). 기획자가 개발사에
    "이렇게 하면 나온다" 고 넘길 때 표를 풀어 쓸 필요가 없게 한다.
    `broke` 는 규칙을 어긴 항목의 이름이다 — 그 항목을 건드린 단계만 진하게 둔다. 나머지 단계는
    케이스마다 같아서, 다 같은 무게면 무엇을 다르게 넣었는지 찾아 읽어야 한다.

    멈춘 단계도 같은 무게로 진하게 둔다 — 전체 가운데 어디서 멈췄는지가 한눈에 보여야 한다.
    그 뒤의 실행하지 못한 단계(verdict.pending_steps)는 흐리게 이어 적는다. 멈춘 데서 목록이
    끊기면 '이게 전부인가' 를 알 수 없다 (2026-11-19).
    """
    if not (verdict.step_results or verdict.pending_steps):
        return ""
    items = []
    for r in verdict.step_results:
        prefix = "<span class='pre'>준비</span> " if r.phase == "setup" else ""
        stuck = r.status == "error"
        stopped = " <em class='stop'>여기서 멈춤</em>" if stuck else ""
        hit = bool(broke) and r.phase != "setup" and r.target == broke and r.action != "click"
        mark = " <em class='broke'>기획서를 어긴 단계</em>" if hit else ""
        cls = " class=broke" if hit else " class='broke stuck'" if stuck else ""
        items.append(f"<li{cls}>{prefix}"
                     f"{_esc(step_sentence(r.action, r.target, r.value))}{mark}{stopped}</li>")
    for s in verdict.pending_steps:
        prefix = "<span class='pre'>준비</span> " if s.get("phase") == "setup" else ""
        items.append(f"<li class='todo'>{prefix}"
                     f"{_esc(step_sentence(s.get('action', ''), s.get('target', ''), s.get('value')))}</li>")
    note = ("<p class='repro-note'>흐린 단계는 앞에서 멈춰 실행하지 못했습니다.</p>"
            if verdict.pending_steps else "")
    return f"<h4>재현 절차</h4><ol class='repro'>{''.join(items)}</ol>{note}"


def _conclusion(verdicts: list[Verdict], total: int) -> str:
    """리포트 파일 맨 위의 결론 한 줄 — 웹 UI 결과 제목과 같은 말."""
    kinds = [fail_kind(v) for v in verdicts if v.verdict == "FAIL"]
    for kind, tail in (("defect", "건이 기획서와 다릅니다."), ("infra", "건을 실행 문제로 확인하지 못했습니다."),
                       ("unv", "건은 판정할 근거가 없습니다.")):
        n = kinds.count(kind)
        if n:
            return f"{total}건 중 <mark class='{'fail' if kind == 'defect' else kind}'>{n}{tail}</mark>"
    return f"<mark class='pass'>{total}건 모두 통과했습니다.</mark>"


def _fail_list_html(fails: list[Verdict], names: dict, numbers: dict | None = None) -> str:
    """틀린 곳을 한 줄씩 — 화면을 열자마자 '무엇이' 틀렸는지 보인다. 누르면 그 카드로 간다.

    번호는 카드의 번호와 같다 — 기획자와 개발사가 '3번' 으로 같은 건을 가리킨다.
    """
    if not fails:
        return ""
    out = []
    for label, kind in (("기획서와 다른 곳", "defect"), ("실행 문제로 확인하지 못한 곳", "infra"),
                        ("확인 불가 (결함도 통과도 아님)", "unv")):
        items = [v for v in fails if fail_kind(v) == kind]
        if not items:
            continue
        def row(v: Verdict, what: str, kind: str = kind) -> str:
            who = v.target_label or names.get(v.screen_id or "", v.screen_id or "")
            # 왼쪽 칸에 항목 이름이 있으니 문장 앞의 같은 이름('비밀번호 확인에 …')은 뗀다.
            for particle in ("에 ", "을 ", "를 "):
                if who and what.startswith(who + particle):
                    what = what[len(who + particle):]
                    break
            rule = RULE_LABELS.get(v.violates, v.violates) if v.violates else ""
            return (f"<a class='frow' href='#c-{_esc(v.case_id)}'>"
                    f"<span class='no {kind}'>{(numbers or {}).get(v.case_id, '')}</span>"
                    f"<span class='who'>{_esc(who)}</span>"
                    f"<span class='what'>{_esc(what)}</span><span class='rule'>{_esc(rule)}</span></a>")

        if kind == "infra":
            rows = _stuck_rows_html(items, fails, names, numbers or {}, row)
        else:
            rows = ""
            for v in items:
                missing, found = missing_names(v)
                if kind == "unv":
                    # 확인 불가는 이유가 대개 한 가지라(쓰기 요청 막기 등) 줄마다 같은 문장이 된다 —
                    # 무엇을 확인하지 못했는지(케이스 문장)를 쓰고, 이유는 카드에 둔다.
                    what = v.plain or v.title
                elif missing:
                    # 이름 대조는 사유가 못 찾은 이름을 전부 이은 긴 문장이다 — 수만 적고 이름은 카드에 둔다.
                    what = _names_sentence(missing, found)
                else:
                    what = _headline(v)[0]
                rows += row(v, what)
        out.append(f"<div class='flist {kind}'><div class='cap'>{label} {len(items)}</div>{rows}</div>")
    return "".join(out)


def _names_sentence(missing: list[str], found: list[str]) -> str:
    return (f"기획서의 이름 {len(missing) + len(found)}개 가운데 {len(missing)}개를 "
            "화면에서 찾지 못했습니다.")


def _stuck_rows_html(items: list[Verdict], fails: list[Verdict], names: dict, numbers: dict,
                     row) -> str:
    """판정하지 못한 건을 멈춘 이유가 같은 것끼리 묶는다 (2026-11-19, 기획자용 보고서에서 옮김).

    실물 기획서 실행에서 19건 중 10건이 한 화면의 같은 자리에서 멈췄다. 한 줄씩 늘어놓으면 같은
    문장을 열 번 읽고서야 '원인은 하나' 임을 안다. 이유는 묶음 머리에 한 번 적고, 줄에는 무엇을
    확인하려던 것인지를 적는다. 화면이 다르면 같은 문장이라도 고칠 곳이 달라 따로 묶는다.
    """
    groups: dict[tuple[str, str], list[Verdict]] = {}
    for v in items:
        groups.setdefault((v.screen_id or "", stop_reason(v)[1]), []).append(v)
    # 기획서와 다른 곳에서 '화면에 없던 이름' → 그 건의 번호. 멈춘 대상이 그 이름이면 같은 차이다.
    missing_at: dict[tuple[str, str], object] = {}
    for d in fails:
        if fail_kind(d) == "defect":
            for name in missing_names(d)[0]:
                missing_at.setdefault((d.screen_id or "", name), numbers.get(d.case_id, ""))
    out = []
    for (sid, sentence), group in groups.items():
        target = stop_reason(group[0])[0]
        same = ""
        if target and (sid, target) in missing_at:
            same = (f"멈춘 대상 {_esc(repr(target))} — 기획서와 다른 곳 {missing_at[(sid, target)]}번에서 "
                    "화면에 없던 이름입니다. 같은 차이 때문에 멈춘 것으로 보입니다.")
        if len(group) < 2:
            out.append(row(group[0], sentence) + (f"<div class='fwhy'>{same}</div>" if same else ""))
            continue
        screen = names.get(sid, sid)
        out.append(
            f"<div class='fgroup'><div class='fwhy'><b>같은 이유로 {len(group)}건</b>"
            f"{_esc(screen) + ' — ' if screen else ''}{_esc(sentence)}"
            f"{'<br>' + same if same else ''}</div>"
            + "".join(row(v, v.plain or v.title) for v in group) + "</div>")
    return "".join(out)


# 흐름 케이스의 확인 스텝 이름 — s2_case_generator.generator._flow_case 가 짓는다.
# '<screen_id> 성공' 은 중간 화면의 성공 조건, '<screen_id> 도착' 은 눌러 옮긴 뒤 경로 확인.
_FLOW_MARK = re.compile(r"^(\S+) (성공|도착)$")


def flow_route(v: Verdict) -> dict | None:
    """흐름 케이스의 스텝에서 화면 순서·이동 방법·끊긴 곳을 읽는다.

    리포트에는 기획서의 흐름 표가 없다 — 대신 케이스 스텝에 화면 경계가 이름으로 남아
    있다('signup 성공', 'login 도착'). 실행한 스텝(step_results)과 멈춘 뒤 남은 스텝
    (pending_steps)을 이으면 흐름 전체가 나온다. 모양이 맞지 않으면 None — 지도를
    그리지 않고 예전처럼 글로만 둔다(틀린 지도보다 없는 지도가 낫다).

    돌려주는 것: screens(screen_id 순서), via(전이마다 누른 요소 이름, 주소 이동은 ""),
    broken(("node"|"edge", 번호) 또는 None).
    """
    if not v.flow_id:
        return None
    steps = [(r.action, r.target or "", r.status) for r in v.step_results if r.phase == "test"]
    steps += [(d.get("action") or "", d.get("target") or "", "pending")
              for d in v.pending_steps if d.get("phase", "test") == "test"]
    screens: list[str] = []
    via: list[str] = []
    broken = None
    for i, (action, target, status) in enumerate(steps):
        mark = _FLOW_MARK.match(target) if action == "assert" else None
        if mark and mark.group(2) == "성공":
            if status == "error" and broken is None:
                broken = ("node", len(screens))
            screens.append(mark.group(1))
            via.append("")
            continue
        if mark and mark.group(2) == "도착":
            if not via:
                return None
            prev = steps[i - 1]
            via[-1] = prev[1] if prev[0] == "click" else ""
            if status == "error" and broken is None:
                broken = ("edge", len(via) - 1)
            continue
        if status == "error" and broken is None:
            nxt = steps[i + 1] if i + 1 < len(steps) else ("", "", "")
            arrive = nxt[0] == "assert" and nxt[1].endswith(" 도착")
            # 이동 요소를 못 찾아 누르지 못했다 — 화면 안이 아니라 화면 사이에서 끊겼다.
            broken = ("edge", len(via) - 1) if action == "click" and arrive and via else ("node", len(screens))
    screens.append(v.screen_id)
    if len(screens) < 2 or len(via) != len(screens) - 1:
        return None
    if v.verdict == "FAIL" and broken is None and not any(
            r.status == "error" and r.phase == "setup" for r in v.step_results):
        # 스텝은 다 지났는데 마지막 화면의 확인(케이스 기대)이 틀렸다.
        broken = ("node", len(screens) - 1)
    if v.verdict == "PASS":
        broken = None
    return {"screens": screens, "via": via, "broken": broken}


def _flow_map_html(v: Verdict, names: dict) -> str:
    """흐름 실패 카드 맨 위의 화면 흐름 지도 — 어느 화면, 어느 이동에서 끊겼는지.

    21st.dev 'Interactive Workflow Blueprint' 의 노드·연결선 그림만 가져왔다(웹 화면의
    app.js flowMap 과 같은 모양). 판정 색은 카드의 실패 분류(fail_kind)를 따르고 늘
    글자('여기서 끊김')와 함께 쓴다.
    """
    route = flow_route(v)
    if not route:
        return ""
    kind, at = route["broken"] or ("", -1)

    def state(part: str, i: int) -> str:
        if not route["broken"]:
            return "ok" if v.verdict == "PASS" else ""
        if part == kind and i == at:
            return "broken"
        # 끊긴 곳보다 앞은 지나왔고, 뒤는 가지 못했다. 끊긴 이동의 앞 화면(i == at)도 지나왔다.
        before = i < at or (part == "node" and kind == "edge" and i == at)
        return "ok" if before else "unreached"

    say = {"ok": "통과", "broken": "여기서 끊김", "unreached": "가지 못함"}
    parts = []
    for i, sid in enumerate(route["screens"]):
        if i:
            st = state("edge", i - 1)
            m = route["via"][i - 1]
            label = f"'{_esc(m)}' 누름" if m else "주소로 이동"
            note = f"<i>{say[st]}</i>" if st == "broken" else ""
            parts.append(f"<li class='fm-edge' data-via='{'click' if m else 'url'}' data-state='{st}'>"
                         f"<span>{label}</span>{note}</li>")
        st = state("node", i)
        parts.append(f"<li class='fm-node' data-state='{st}'><b>{_esc(names.get(sid) or sid)}</b>"
                     f"{f'<i>{say[st]}</i>' if st else ''}</li>")
    return (f"<ol class='flowmap {fail_kind(v) if v.verdict == 'FAIL' else ''}' aria-label='화면 흐름'>"
            f"{''.join(parts)}</ol>")


def _case_html(verdict: Verdict, open_by_default: bool,
               revised: dict | None = None, target_url: str = "", no: int | None = None,
               names: dict | None = None) -> str:
    ev = verdict.evidence or {}
    # 이전 판 기획서와 비교해 바뀐 것을 건드리는 케이스 (prova.spec_revision). 판정이 아니라
    # '이 케이스가 새 판의 바뀐 곳을 본다' 는 표시다.
    why = (revised or {}).get(verdict.case_id) or []
    rev_tag = (f"<span class='tag revised' title='{_esc(' / '.join(why))}'>개정</span>"
               if why else "")
    # 요소와 규칙을 함께 보여준다. 화면에 같은 규칙을 가진 요소가 여럿이면
    # (회원가입의 required 6개) 규칙 이름만으로는 어디를 고쳐야 할지 모른다.
    rule_name = RULE_LABELS.get(verdict.violates, verdict.violates) if verdict.violates else ""
    # 요소는 기획서의 이름으로 적는다(식별자는 마우스를 올리면 보인다).
    subject = rule_subject(verdict.target_label, verdict.target_element)
    rule_label = f"{subject} · {rule_name}" if subject else rule_name
    rule_tag = (f"<span class='tag rule' title='{_esc(verdict.target_element or '')}'>"
                f"{_esc(rule_label)}</span>" if verdict.violates else "")
    # 분류를 요약 줄에 올린다. 펼친 카드 안쪽 표에만 있으면 목록만 훑는 사람에게
    # 구현 결함과 도구·환경 실패가 똑같이 'FAIL' 로 보인다.
    cat_tag = ""
    # 결함(기획서와 다름)과 도구·환경 쪽 실패는 카드 안에서도 색이 달라야 한다. 전부 빨강이면
    # 기획자가 개발사에 잘못 따진다.
    kind = ""
    if verdict.verdict == "FAIL" and verdict.failure_category:
        kind = fail_kind(verdict)
        name = CATEGORY_LABELS.get(verdict.failure_category,
                                   CATEGORY_LABELS["unknown"])[0]
        cat_tag = f"<span class='tag cat {kind}'>{_esc(name)}</span>"
    elif is_weak_pass(verdict):
        cat_tag = "<span class='tag cat weak'>약한 확인</span>"

    # 실패 카드의 대제목 — 무엇이 틀렸는지를 사유의 첫 문장으로 크게 쓴다. 목록을 훑는
    # 사람은 케이스 제목('…규칙 강제 여부 확인')이 아니라 이 문장을 읽고 지나간다.
    headline, rest = _headline(verdict)
    # 이름 대조는 사유가 못 찾은 이름을 전부 이은 긴 문장이다 — 대제목에는 수만 쓰고 이름은 비교 칸에
    # 나눠 적는다(_compare_html). 복사하는 글에는 원래 문장을 둔다 — 개발사에는 이름이 필요하다.
    missing, found = missing_names(verdict)
    shown = _names_sentence(missing, found) if missing and verdict.verdict == "FAIL" else headline
    if kind == "infra" and any(r.status == "error" for r in verdict.step_results):
        # 사유의 첫 문장은 내부 말('스텝 3(fill …) 실패')이다 — 무엇을 하려다 멈췄는지로 바꿔 적는다.
        # 고치는 사람용은 원래 문장을 오른쪽 '실제 화면' 칸에 그대로 둔다. 복사 글도 원래 문장이다.
        shown, rest = stop_reason(verdict)[1], ""

    rows = [("이번 판에서 바뀐 것", _esc(" / ".join(why)))] if why else []
    # 기대·실제·기획서 근거는 아래 비교 칸(_compare_html)이 좌우로 나란히 보인다.
    actual = ev.get("actual")
    # 대제목에 못 담은 사유의 나머지 — 실제 결과와 같은 말이면 두 번 쓰지 않는다.
    if rest and rest not in str(actual or "") and str(actual or "") not in rest:
        rows.append(("자세히", _esc(rest)))
    # 실패 분류는 요약 줄 꼬리표에 있다. 최종 URL 은 재현 자료와 함께 접어 둔다.
    if ev.get("error_texts"):
        rows.append(("화면 에러", _esc(" / ".join(ev["error_texts"]))))
    if ev.get("dry_run_blocked"):
        rows.append(("쓰기 요청 막기로 막은 요청", _esc(" / ".join(ev["dry_run_blocked"]))
                     + f" (막지 않았다면 판정: {_esc(ev.get('dry_run_original'))}, 참고용)"))

    kv = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)
    # 재현 자료(단계 표·캡처 전부·최종 URL)는 개발자에게 넘길 때 보는 것이라 접어 둔다.
    # 알림이 아니라 근거 자료다 — 요구서 4절 1번(알림은 접지 않는다)과 부딪히지 않는다.
    n_steps = len(verdict.step_results)
    n_shots = sum(1 for r in verdict.step_results if r.screenshot)
    more = (f"<details class='raw'><summary>단계별 기록 {n_steps}개 · 캡처 {n_shots}장</summary>"
            f"<div class='url'>마지막 주소 <code>{_esc(ev.get('url'))}</code></div>"
            f"{_steps_html(verdict)}{_shots_html(verdict)}</details>" if n_steps else "")
    failed = verdict.verdict == "FAIL"
    copy = ""
    if failed:
        label = {"defect": "기획서와 다름", "infra": "실행 문제", "unv": "확인 불가"}[fail_kind(verdict)]
        text = copy_text(verdict, f"[{label}] {headline}", target_url)
        copy = (f"<button class='copy' type='button' data-copy='{_esc(text)}'>"
                "재현 절차 복사</button>")

    shot = _trace_html(verdict, kind, names) if failed else ""
    no_tag = f"<span class='no {kind}'>{no}</span>" if failed and no else ""
    repro = _repro_html(verdict, verdict.target_label if kind == "defect" and verdict.violates else None)

    return (
        f"<details class='case{' failed' if failed else ''}' id='c-{_esc(verdict.case_id)}'"
        f"{' open' if open_by_default else ''}>"
        f"<summary>{no_tag}"
        f"{f'<span class=head>{_esc(shown)}</span>' if shown else ''}{copy}"
        f"<span class='tag {verdict.verdict}'>{verdict.verdict}</span>"
        f"{cat_tag}{rev_tag}{rule_tag}"
        # 대제목이 케이스 문장을 뒤집어 쓴 것이면('…입력해도 막히지 않습니다') 같은 문장을 또 쓰지 않는다.
        f"{'' if failed and verdict.plain and not_blocked_sentence(verdict.plain) else f'<span class=title>{_esc(verdict.plain or verdict.title)}</span>'}"
        f"<span class='ms'>{verdict.elapsed_ms}ms</span></summary>"
        f"<div class='body'>{_flow_map_html(verdict, names or {}) if verdict.flow_id else ''}"
        f"{_compare_html(verdict, kind, shot, repro)}{f'<table class=kv>{kv}</table>' if kv else ''}"
        f"{more}"
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
        # 전제 미충족(precondition_failed) 은 결함 수(fail)에 넣지 않고 별도
        # 열로 보여준다 — 이 화면의 결함이 아니라 전제로 삼은 화면(로그인)의
        # 결함이 여기서 또 잡힌 것뿐이다. 합치면 같은 결함이 여러 화면의
        # 결함처럼 불어나 보인다 (명세서 §3-6·§3-7).
        precondition = n.get("precondition", 0)
        precond_cls = " class='n f'" if precondition else " class='n'"
        return (
            f"<tr><td>{_esc(label)} <code>{_esc(code)}</code></td>"
            f"<td class='k'>{_esc(kind)}</td>"
            f"<td class='n'>{n['total']}</td><td class='n'>{n['pass']}</td>"
            f"<td{fail_cls}>{n['fail']}</td>"
            f"<td{precond_cls}>{precondition}</td></tr>"
        )

    rows = [row(names.get(sid, sid), sid, n, "화면") for sid, n in by_screen.items()]
    rows += [row("화면 사이", fid, n, "흐름") for fid, n in by_flow.items()]
    return (
        "<table class='screens'><thead><tr><th>대상</th><th>종류</th><th>전체</th>"
        "<th>통과</th><th>실패</th><th>전제 미충족</th></tr></thead><tbody>"
        + "".join(rows) + "</tbody></table>"
    )


def _groups(verdicts: list[Verdict], names: dict) -> dict[str, list[Verdict]]:
    """판정을 화면별로 묶는다. 흐름은 화면과 섞지 않고 제 묶음을 갖는다."""
    groups: dict[str, list[Verdict]] = {}
    for v in verdicts:
        key = f"흐름 {v.flow_id}" if v.flow_id else names.get(v.screen_id or "?",
                                                             v.screen_id or "?")
        groups.setdefault(key, []).append(v)
    return groups


def _grouped_html(verdicts: list[Verdict], names: dict, open_by_default: bool,
                  revised: dict | None = None, target_url: str = "",
                  numbers: dict | None = None) -> str:
    """판정을 화면별로 묶어 렌더한다. 묶을 것이 하나면 소제목을 붙이지 않는다.

    흐름은 별도 구획으로 떼어 맨 뒤에 둔다. 마지막 화면 구획에 섞으면 **그 화면에
    결함이 하나 더 있는 것처럼 읽힌다** — 흐름의 실패는 화면 안이 아니라 화면
    사이의 문제이고 고칠 곳도 다르다.
    """
    if not verdicts:
        return ""
    groups = _groups(verdicts, names)

    def card(v: Verdict) -> str:
        return _case_html(v, open_by_default, revised, target_url, (numbers or {}).get(v.case_id),
                          names)

    if len(groups) < 2:
        return "".join(card(v) for v in verdicts)

    out = []
    for label, items in groups.items():
        out.append(f"<h3 class='grp'>{_esc(label)} · {len(items)}건</h3>")
        out.extend(card(v) for v in items)
    return "".join(out)


def _screens_phrase(names: dict, checked: list) -> str:
    """결론 아래 한 줄의 화면 부분. 화면이 많으면 이름을 잇지 않고 수만 적는다.

    실물 기획서(화면 21개)에서 이름 21개를 가운뎃점으로 이은 줄이 결론 밑에 세 줄을 차지했고,
    보지 않은 화면까지 '확인한 화면' 처럼 읽혔다(2026-11-19). 이름은 화면별 확인 범위에 있다.
    """
    if not names:
        return ""
    seen = [sid for sid in names if sid in checked] if checked else list(names)
    if len(names) <= 3 and len(seen) == len(names):
        return f"{' · '.join(str(n) for n in names.values())} 화면"
    if len(seen) == len(names):
        return f"화면 {len(names)}개"
    return f"기획서 화면 {len(names)}개 중 {len(seen)}개 확인"


_NO_URL = "화면 경로가 기획서에 없어 실행하지 않습니다"


def _scope_html(report: TestReport, names: dict, checked: list, numbers: dict, gaps: list,
                warnings: list, spec_figures: dict) -> str:
    """화면별 확인 범위 — 화면마다 한 줄에 그 화면의 결과·못 본 것·읽을 때의 주의를 모은다 (2026-11-19).

    전에는 '요소를 찾지 못한 케이스', '확인하지 않은 것', '보지 않은 화면', '설계 문서 추출 경고' 가
    저마다 상자였고, 줄마다 [화면 ID] 를 앞에 단 긴 목록이었다. 실물 기획서(화면 21개)에서 경고만
    150줄이 결론과 틀린 곳 목록 사이에 놓였다. 읽는 사람은 '이 화면은 어떻게 됐나' 를 묻는데 답이
    네 상자에 흩어져 있었다.

    - 화면마다 그 화면의 그림 한 장(실제 화면, 보지 않았으면 기획서 시안)을 붙인다.
    - 실패 건은 제목을 다시 늘어놓지 않고 번호로 가리킨다 — 틀린 곳 목록·카드와 같은 번호다.
    - 여러 화면에 똑같이 붙은 주의(예: 요소 표 없음)는 한 번만 적고 몇 곳인지 센다.
    - 추출 경고와 모델 메모는 접는다. 건수는 접힌 줄에 보인다. 판정의 범위를 바꾸는 것(보지 않은
      화면, 확인하지 않은 것)은 접지 않는다.
    """
    by_name = {str(v): k for k, v in names.items()}

    def split(line: str) -> tuple[str, str]:
        m = re.match(r"\[([^\]]+)\]\s*(.*)", str(line), re.S)
        if not m:
            return "", str(line)
        sid = m.group(1) if m.group(1) in names else by_name.get(m.group(1), "")
        return (sid, m.group(2)) if sid else ("", str(line))

    notes: dict[str, list[str]] = {}
    for w in warnings:
        sid, text = split(w)
        notes.setdefault(sid, []).append(text)
    # 여러 화면에 같은 문장으로 붙은 주의 — 화면마다 되풀이하지 않는다.
    spread: dict[str, int] = {}
    for sid, items in notes.items():
        if sid:
            for text in dict.fromkeys(items):
                spread[text] = spread.get(text, 0) + 1
    common = {text: n for text, n in spread.items()
              if n >= 3 and not text.startswith(MEMO_PREFIX) and _NO_URL not in text}
    gap_by: dict[str, list[str]] = {}
    for g in gaps:
        sid, text = split(g)
        gap_by.setdefault(sid, []).append(text)

    def thumb(sid: str) -> str:
        shot = next((r.screenshot for v in report.cases if v.screen_id == sid and not v.flow_id
                     for r in v.step_results if r.action == "navigate" and r.screenshot), None)
        label = "실제 화면"
        if not shot and sid in spec_figures:
            shot, label = spec_figures[sid][0], "기획서 시안"
        if not shot:
            return "<div class='scr-t none'></div>"
        name = names.get(sid) or sid
        return (f"<div class='shots scr-t'><a href='{_esc(shot)}' target='_blank'>"
                f"<img src='{_esc(shot)}' loading='lazy' alt='{_esc(name)} {label}'>"
                f"<div class='cap'>{_esc(name)} · {label}</div></a></div>")

    def refs(items: list[Verdict]) -> str:
        return ", ".join(f"<a href='#c-{_esc(v.case_id)}'>{numbers.get(v.case_id, '')}번</a>"
                         for v in items)

    def memo_html(memo: list[str]) -> str:
        if not memo:
            return ""
        return ("<div class='why'><b>모델 메모</b> — 모델이 '판단할 수 없다' 고 남긴 말입니다. 도구가 확인한 "
                "사실이 아닙니다.</div>" + "".join(f"<div>· {_esc(x)}</div>" for x in memo))

    def folded(items: list[str]) -> str:
        tool = [x for x in items if not x.startswith(MEMO_PREFIX)]
        memo = [x[len(MEMO_PREFIX):].strip() for x in items if x.startswith(MEMO_PREFIX)]
        if not (tool or memo):
            return ""
        head = " · ".join(x for x in (f"기획서를 읽을 때의 주의 {len(tool)}건" if tool else "",
                                      f"모델 메모 {len(memo)}건" if memo else "") if x)
        body = "".join(f"<div>· {_esc(x)}</div>" for x in tool) + memo_html(memo)
        return f"<details class='scr-more'><summary>{head}</summary>{body}</details>"

    rows = []
    for sid in dict.fromkeys(list(names) + checked):
        mine = [v for v in report.cases if v.screen_id == sid and not v.flow_id]
        own = [x for x in notes.get(sid, []) if x not in common]
        no_url = any(_NO_URL in x for x in own)
        own = [x for x in own if _NO_URL not in x]
        lines = []
        if mine:
            kinds = {k: [v for v in mine if v.verdict == "FAIL" and fail_kind(v) == k]
                     for k in ("defect", "infra", "unv")}
            passed = sum(1 for v in mine if v.verdict == "PASS")
            tally = " · ".join(x for x in (
                f"<span class='n defect'>기획서와 다름 {len(kinds['defect'])}</span>" if kinds["defect"] else "",
                f"<span class='n infra'>확인하지 못함 {len(kinds['infra'])}</span>" if kinds["infra"] else "",
                f"<span class='n unv'>확인 불가 {len(kinds['unv'])}</span>" if kinds["unv"] else "",
                f"통과 {passed}") if x)
            head = f"<span class='scr-n'>확인 {len(mine)}건 — {tally}</span>"
            for label, k in (("기획서와 다른 곳", "defect"), ("확인하지 못한 곳", "infra"),
                             ("확인 불가", "unv")):
                if kinds[k]:
                    lines.append(f"<div class='scr-l'>{label}: {refs(kinds[k])}</div>")
        else:
            why = ("화면 주소가 기획서에 없어 열지 못했습니다. 실행할 때 이 화면의 주소를 알려 주면 확인합니다."
                   if no_url else "이번 실행에서 확인한 케이스가 없습니다.")
            head = f"<span class='scr-n'><b class='unseen'>보지 않음</b> — {why}</span>"
        for g in gap_by.get(sid, []):
            lines.append(f"<div class='scr-l'><b>확인하지 않은 것</b> {_esc(g)}</div>")
        rows.append(
            f"<div class='scr{'' if mine else ' unseen'}'>{thumb(sid)}"
            f"<div class='scr-b'><div class='scr-h'><b>{_esc(names.get(sid) or sid)}</b>{head}</div>"
            f"{''.join(lines)}{folded(own)}</div></div>")

    # 화면 사이(흐름) — 화면 안이 아니라 화면 사이의 문제라 제 줄을 갖는다.
    flows: dict[str, list[Verdict]] = {}
    for v in report.cases:
        if v.flow_id:
            flows.setdefault(v.flow_id, []).append(v)
    for fid, items in flows.items():
        bad = [v for v in items if v.verdict == "FAIL"]
        pre = sum(1 for v in bad if v.failure_category == "precondition_failed")
        rows.append(
            "<div class='scr'><div class='scr-t none'></div><div class='scr-b'>"
            f"<div class='scr-h'><b>화면 사이 <code>{_esc(fid)}</code></b><span class='scr-n'>"
            f"확인 {len(items)}건 — 실패 {len(bad)} · 통과 {len(items) - len(bad)}"
            f"{f' · 전제 미충족 {pre}' if pre else ''}</span></div>"
            + (f"<div class='scr-l'>실패: {refs(bad)}</div>" if bad else "") + "</div></div>")

    shared = [f"<div>· {_esc(text)} <span class='ms'>화면 {n}곳</span></div>" for text, n in common.items()]
    whole = notes.get("", [])
    extra = ""
    if shared or whole:
        head = " · ".join(x for x in (f"여러 화면에 공통인 주의 {len(shared)}가지" if shared else "",
                                      f"문서 전체 {len(whole)}건" if whole else "") if x)
        tool = [x for x in whole if not x.startswith(MEMO_PREFIX)]
        memo = [x[len(MEMO_PREFIX):].strip() for x in whole if x.startswith(MEMO_PREFIX)]
        body = "".join(shared) + "".join(f"<div>· {_esc(x)}</div>" for x in tool) + memo_html(memo)
        extra = (f"<details class='scr-more all'><summary>설계 문서 추출 경고 — {head}</summary>"
                 f"{body}</details>")
    loose = "".join(f"<div class='scr-l'><b>확인하지 않은 것</b> {_esc(g)}</div>" for g in gap_by.get("", []))

    if len(rows) < 2 and not (gaps or warnings):
        return ""
    unseen = [sid for sid in names if sid not in checked]
    intro = ""
    if unseen and checked:
        intro = (f"기획서 화면 {len(names)}개 가운데 {len(names) - len(unseen)}개만 이번 실행에서 "
                 "확인했습니다. ")
    if (unseen and checked) or gaps:
        intro += "'보지 않음' 과 '확인하지 않은 것' 은 <b>통과한 것이 아니라 확인하지 않은 것</b>입니다."
    title = f"화면별 확인 범위 ({len(rows)})" if len(rows) > 1 else "확인 범위와 주의"
    return (f"<h2>{title}</h2>"
            + (f"<p class='scope-note'>{intro}</p>" if intro else "")
            + f"<div class='scope'>{''.join(rows)}</div>{loose}{extra}")


def _design_pairs_html(report: TestReport, names: dict, checked: list, spec_figures: dict) -> str:
    """기획서 시안과 실제 화면을 나란히 둔다 (2026-11-19, 기획자용 보고서에서 옮김).

    색·배치는 판정하지 않는다(spec_figures 의 설명). 시안이 없으면 절을 세우지 않는다.
    실제 화면은 그 화면을 연 직후의 캡처다 — 조작하기 전 모습이 시안과 견줄 만하다.
    """
    sids = [sid for sid in checked if sid in spec_figures]
    if not sids:
        return ""
    out = [f"<h2>기획서 시안과 실제 화면 ({len(sids)})</h2>"
           "<p class='scope-note'>왼쪽은 기획서 그 화면 쪽의 첫 화면 부분이고, 오른쪽은 그 화면을 연 직후 찍은 "
           "것입니다. 색·배치는 자동으로 대조하지 않았습니다 — 나란히 놓고 직접 비교하세요. "
           "누르면 크게 봅니다(시안은 전체).</p>"]
    for sid in sids:
        name = names.get(sid) or sid
        crop, full = spec_figures[sid]
        shot = next((r.screenshot for v in report.cases if v.screen_id == sid
                     for r in v.step_results if r.action == "navigate" and r.screenshot), None)
        real = (f"<a href='{_esc(shot)}' target='_blank'><img src='{_esc(shot)}' loading='lazy' "
                f"alt='{_esc(name)} 실제 화면'><div class='cap'>{_esc(name)} · 실제 화면</div></a>"
                if shot else "<div class='cap'>실제 화면 캡처가 없습니다.</div>")
        out.append(
            f"<div class='shots pair'><a href='{_esc(full)}' target='_blank'>"
            f"<img src='{_esc(crop)}' loading='lazy' alt='{_esc(name)} 기획서 시안'>"
            f"<div class='cap'>{_esc(name)} · 기획서 시안</div></a>{real}</div>")
    return "".join(out)


def _split_screen(line: str, names: dict) -> tuple[str, str]:
    """'[화면 ID] 문장' 을 (화면 ID, 문장)으로. 화면을 모르면 ('', 원문)."""
    m = re.match(r"\[([^\]]+)\]\s*(.*)", str(line), re.S)
    if not m:
        return "", str(line)
    by_name = {str(v): k for k, v in names.items()}
    sid = m.group(1) if m.group(1) in names else by_name.get(m.group(1), "")
    return (sid, m.group(2)) if sid else ("", str(line))


def _brief_html(report: TestReport, names: dict, checked: list, fails: list[Verdict],
                numbers: dict, gaps: list, backend: str, pairs_html: str) -> str:
    """실패·통과 케이스 아래의 '참고' — 판정을 읽는 데 필요한 것만 한 줄씩 (2026-11-19).

    실물 기획서 실행(화면 21개·43건)에서 케이스 아래에 틀린 곳 목록·화면별 확인 범위(21줄)·
    직전 비교·두 단계 실행·시안 15쌍이 이어져, 다 읽을 것 같지 않은 길이가 됐다. 사용자 결정:
    실패·통과 케이스 밖의 내용은 최소한만 남긴 압축판으로.

    남기는 것은 결과를 잘못 읽지 않는 데 필요한 것뿐이다 — 보지 않은 화면(통과가 아니다),
    확인하지 않은 것, 실행 문제가 몰린 이유, 실행 조건 한 줄, 받을 파일. 추출 경고·모델 메모는
    report.json 과 엑셀에 있다. 시안 대조는 접어 둔다.
    """
    s = report.summary
    items = []
    no_url = {sid for sid, text in (_split_screen(w, names) for w in s.get("spec_warnings") or [])
              if sid and _NO_URL in text}
    unseen = [sid for sid in names if sid not in checked]
    if unseen:
        why = ("화면 주소가 기획서에 없어 열지 못했습니다" if all(u in no_url for u in unseen)
               else "이번 실행에서 확인한 케이스가 없습니다")
        items.append(
            f"<li><b>보지 않은 화면 {len(unseen)}개</b>"
            f"{_esc(' · '.join(str(names[u]) for u in unseen))} — {why}. 통과한 것이 아닙니다.</li>")
    if gaps:
        shown = [_split_screen(g, names) for g in gaps[:3]]
        more = f" 외 {len(gaps) - 3}건" if len(gaps) > 3 else ""
        items.append(
            f"<li><b>확인하지 않은 것 {len(gaps)}건</b>"
            + " / ".join(f"{_esc(names.get(sid, sid)) + ': ' if sid else ''}{_esc(text)}" for sid, text in shown)
            + f"{more}</li>")
    stuck = [v for v in fails if fail_kind(v) == "infra"]
    if stuck:
        reasons: dict[str, list[Verdict]] = {}
        for v in stuck:
            reasons.setdefault(stop_reason(v)[1], []).append(v)
        top = sorted(reasons.items(), key=lambda kv: -len(kv[1]))[:2]
        lines = []
        for sentence, group in top:
            nos = ", ".join(f"<a href='#c-{_esc(v.case_id)}'>{numbers.get(v.case_id, '')}</a>" for v in group)
            lines.append(f"{len(group)}건 — {_esc(sentence)} <span class='nos'>({nos})</span>")
        rest = len(stuck) - sum(len(g) for _, g in top)
        items.append(f"<li><b>실행 문제 {len(stuck)}건이 멈춘 이유</b>" + "<br>".join(lines)
                     + (f"<br>그 밖의 이유 {rest}건" if rest else "") + "</li>")
    history = s.get("history") or {}
    regressed, fixed = history.get("regressed") or [], history.get("fixed") or []
    added, removed = history.get("added", 0), history.get("removed", 0)
    if history.get("previous_run") and (regressed or fixed or added or removed or history.get("partial")):
        when = _esc((history.get("previous_at") or "")[:16].replace("T", " "))
        parts = [f"새로 실패 {len(regressed)}건 · 해결 {len(fixed)}건"
                 + (f" · 새 케이스 {added}건" if added else "")
                 + (f" · 사라진 케이스 {removed}건" if removed else "")]
        parts += [f"새로 실패: {_esc(t)}" for t in regressed[:3]]
        parts += [f"해결: {_esc(t)}" for t in fixed[:3]]
        if len(regressed) > 3 or len(fixed) > 3:
            parts.append("나머지는 엑셀에 있습니다")
        if history.get("partial"):
            parts.append("둘 중 한쪽은 일부만 실행한 결과라 양쪽에 다 있는 케이스만 비교했습니다")
        items.append(f"<li><b>{history.get('round', '?')}차 — 직전 실행({when})과 비교</b>"
                     + "<br>".join(parts) + "</li>")
    if s.get("healed"):
        items.append(f"<li><b>화면 이미지로 찾아 진행 {s['healed']}건</b>기획서의 라벨이 구현과 이어져 있지 않습니다.</li>")
    if s.get("settled"):
        items.append(f"<li><b>결과를 기다린 뒤 통과 {s['settled']}건</b>이 화면은 결과를 늦게 보여 줍니다.</li>")
    plan = s.get("plan") or {}
    run = [f"실행 번호 {_esc(report.run_id)}"]
    if backend:
        run.append(f"모델 {_esc(backend)}")
    if plan:
        run.append(f"두 단계 실행(추출 {_esc(str(plan.get('created_at', '?'))[:16].replace('T', ' '))}"
                   f" · {_esc(plan.get('backend', '?'))})")
    if "vlm" in s:
        run.append("화면 이미지로 찾기 " + (f"켬 · {_esc(s['vlm'])}" if s["vlm"] else "꺼짐"))
    if s.get("viewport"):
        run.append(f"화면 크기 {_esc(s['viewport'])}")
    if s.get("sut_build"):
        run.append("대상 빌드 " + ("일치" if s["sut_build"] == "match" else "확인 불가"))
    if s.get("workers"):
        run.append(f"병렬 {_esc(s['workers'])}")
    cache = s.get("llm_cache") or {}
    if cache.get("hits"):
        run.append(f"저장된 모델 응답 {_esc(cache['hits'])}건 재사용 · 새 호출 {_esc(cache.get('misses', 0))}건")
    items.append(f"<li><b>실행 조건</b>{' · '.join(run)}</li>")
    # 계획을 세운 뒤 기획서가 바뀌었다는 경고는 판정의 전제를 흔든다 — 짧게라도 남긴다.
    if plan.get("warnings"):
        items.append("<li><b>저장된 계획의 주의</b>"
                     + "<br>".join(_esc(w) for w in plan["warnings"]) + "</li>")
    items.append("<li><b>받기</b><a href='report.xlsx' download>엑셀</a> · "
                 "<a href='report.csv' download>결과표 CSV</a> · "
                 "<a href='run.log' target='_blank'>실행 로그</a> — 스크린샷은 이 파일 옆 폴더에 있어, "
                 "공유할 때는 결과 폴더째 보내세요.</li>")
    fold = (f"<details class='pairfold'><summary>기획서 시안과 실제 화면 보기</summary>{pairs_html}</details>"
            if pairs_html else "")
    def cell(item: str) -> str:
        head, _, rest = item.removeprefix("<li><b>").removesuffix("</li>").partition("</b>")
        return f"<li><b>{head}</b><span>{rest}</span></li>"
    items = [cell(i) for i in items]
    return f"<h2 class='brief-h'>참고</h2><ul class='brief'>{''.join(items)}</ul>{fold}"


def render_html(report: TestReport, spec_figures: dict | None = None) -> str:
    s = report.summary
    total = s.get("total", 0) or 0
    passed, failed = s.get("pass", 0), s.get("fail", 0)
    rate = s.get("pass_rate", 0)

    fails = [v for v in report.cases if v.verdict == "FAIL"]
    passes = [v for v in report.cases if v.verdict == "PASS"]

    warn_html = ""  # 추출 경고·모델 메모는 화면별 확인 범위(_scope_html)가 화면마다 접어서 보인다.

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

    # 자연어 요청으로 고른 실행. --only 와 같은 부분 실행이지만 위험이 더 크다 —
    # 필터는 사람이 쓴 문자열이라 무엇이 빠졌는지 스스로 알지만, 요청 해석은
    # 모델이 골랐으므로 무엇이 빠졌는지 사람이 모른다. 그래서 제외 목록을
    # 통째로 싣는다.
    # 요청이 비어 있어도 제외가 있으면 싣는다 — 웹 UI 는 요청 없이 체크박스만
    # 꺼서 실행할 수 있고, 그때 이 절을 건너뛰면 제외 목록이 통째로 사라진
    # 100% 짜리 리포트가 나온다 (2026-08-22).
    sel = report.selection
    sel_html = ""
    if sel and (sel.request or sel.excluded):
        if sel.request:
            rows = [f"<div>요청: <code>{_esc(sel.request)}</code></div>"]
        else:
            rows = ["<div>요청 없이 계획 화면에서 <b>승인한 케이스만</b> 실행했습니다.</div>"]
        if sel.reason:
            rows.append(f"<div>선택 근거: {_esc(sel.reason)}</div>")
        for w in sel.warnings:
            rows.append(f"<div>· {_esc(w)}</div>")
        if sel.widened:
            # 모델이 고른 것과 코드가 더한 것을 구분해 남긴다 — 그래야 "해석이
            # 맞았는가" 를 리포트만 보고 되짚을 수 있다 (selector.widen_selection).
            rows.append(
                f"<div>도구가 넓힌 케이스 {len(sel.widened)}건 — 모델이 가리킨 묶음을 "
                f"코드가 채웠습니다: {_esc(', '.join(sel.widened))}</div>"
            )
        if sel.fallback:
            rows.append(
                "<div>요청을 해석하지 못해 <b>전체 케이스를 실행</b>했습니다 — "
                "해석 실패는 적게 검사하는 쪽이 아니라 많이 검사하는 쪽으로 넘어집니다.</div>"
            )
        # 요청이 화면을 이름으로 지목했는데 일부만 골라진 경우. '몇 건 제외' 만
        # 보면 그 화면을 확인했다고 읽힌다 — 실모델 측정에서 "회원가입이 잘
        # 되는지" 에 17건 중 6건만 골라진 것이 프롬프트로는 안 고쳐졌고, 이
        # 표시가 그 남은 구멍의 방어선이다.
        risky = [c for c in sel.coverage if c.named and c.partial]
        for c in risky:
            rows.append(
                f"<div class='why'><b>'{_esc(c.name)}' 화면은 {c.total}건 중 "
                f"{c.selected}건만 실행됩니다</b> — 요청이 이 화면을 가리켰지만 "
                "일부만 골라졌습니다. 이 화면의 통과율은 화면 전체의 상태를 뜻하지 않습니다.</div>"
            )
        partial = [c for c in sel.coverage if c.partial or c.selected == 0]
        if partial:
            rows.append("<div class='why'><b>화면별 확인 범위</b></div>")
            for c in sel.coverage:
                kind = "흐름 " if c.kind == "flow" else ""
                rows.append(
                    f"<div>· {kind}{_esc(c.name)} — {c.selected}/{c.total}건</div>"
                )
        if sel.excluded:
            rows.append(
                f"<div class='why'><b>이번 실행에서 제외한 케이스 ({len(sel.excluded)}건)</b> — "
                "아래는 <b>통과한 것이 아니라 실행하지 않은 것</b>입니다.</div>"
            )
            rows += [
                f"<div>· {_esc(sel.excluded_titles.get(cid, cid))}"
                + (f" <span class='ms'>{_esc(cid)}</span>"
                   if cid in sel.excluded_titles else "")
                + "</div>"
                for cid in sel.excluded
            ]
        who = "요청을 확인한 뒤 사람이 승인한 실행" if sel.approved else "자연어 요청으로 고른 실행"
        sel_html = (
            f"<div class='gap'><b>{who} "
            f"({len(sel.selected)}건 실행"
            + (f" · {len(sel.excluded)}건 제외" if sel.excluded else "")
            + ")</b>"
            + "".join(rows)
            + "</div>"
        )

    gaps = s.get("coverage_gaps") or []
    gap_html = ""  # 확인하지 않은 것은 화면별 확인 범위(_scope_html)가 그 화면 줄에 적는다.

    healed = s.get("healed", 0) or 0
    heal_html = ""
    if healed:
        healed_titles = "".join(
            f"<div>· {_esc(v.plain or v.title)}</div>"
            for v in report.cases if v.healed
        )
        heal_html = (
            f"<div class='heal'><b>화면 이미지로 찾아 진행한 케이스 ({healed}건)</b>"
            "<div class='why'>기획서의 라벨로 요소를 찾지 못해 화면 이미지로 찾아 진행했습니다. "
            "판정은 유효하지만 <b>라벨이 구현과 이어져 있지 않습니다</b> — "
            "'기획서의 항목 이름으로 화면에서 칸을 찾을 수 있다' 항목을 함께 보세요.</div>"
            f"{healed_titles}</div>"
        )

    # 2차 경로를 끈 채로 요소를 못 찾았다 — 켜서 다시 돌려 볼 만하다고 알린다.
    #
    # 켜면 해결된다고 말하지 않는다. 못 찾은 까닭은 '라벨만 없다' 와 '구현이 그 항목을
    # 빠뜨렸다' 가 섞여 있고, 뒤쪽이면 켜도 못 찾는 것이 맞는 결과다. 그래서 화면에 그
    # 요소가 보이는지를 먼저 보라고 적는다.
    #
    # 상자가 아니라 실패 케이스 바로 아래 작은 글씨다 (2026-11-19) — 결론과 실패 케이스 사이를
    # 막던 상자 중 하나였다. 판정을 바꾸는 알림이 아니라 다시 돌릴 때의 요령이다.
    missed = s.get("not_found_without_vlm", 0) or 0
    missed_note = ""
    if missed:
        missed_note = (
            f"<p class='smallnote'><b>요소를 찾지 못한 케이스 {missed}건</b> — 화면 이미지로 찾기를 켜지 "
            "않은 실행입니다. 기획서의 라벨로만 찾았습니다. 스크린샷에 그 요소가 보이는데 못 찾았다면"
            "(아이콘만 있는 버튼, 라벨을 잇지 않은 입력란 등) '화면 이미지로 찾기' 를 켜서 다시 돌려 "
            "보세요. 스크린샷에도 없다면 구현이 그 항목을 빠뜨린 것일 수 있고, 켜도 달라지지 않습니다. "
            "어느 건인지는 아래 '참고' 의 '멈춘 이유' 에 번호가 있습니다.</p>"
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
            f"<div>· {_esc(v.plain or v.title)} <b>{v.evidence['settled_ms']}ms</b></div>"
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

    # 대상 빌드 확인. 경고 상자가 아니라 머리말 한 줄이다 — 실물 대상에는 도장이
    # 없는 것이 정상이라 상자로 만들면 매번 뜨고, 매번 뜨는 경고는 읽히지 않는다.
    build_state = s.get("sut_build", "")
    build_meta = ""
    if build_state:
        label = "일치" if build_state == "match" else "확인 불가"
        build_meta = f"\n대상 빌드 <code>{_esc(label)}</code>"
    # 2차 경로도 머리말 한 줄이다 — 꺼진 것이 기본이라 상자로 만들면 매번 뜬다.
    if "vlm" in s:
        state = f"켬 · {s['vlm']}" if s["vlm"] else "꺼짐"
        build_meta += f"\n화면 이미지로 찾기 <code>{_esc(state)}</code>"
    # 기본(데스크톱)이 아닌 화면 크기 — 판정의 전제라 머리말에 둔다 (nodes.note_viewport).
    if s.get("viewport"):
        build_meta += f"\n화면 크기 <code>{_esc(s['viewport'])}</code>"

    backend = s.get("llm_backend", "")
    mock_warn = ""
    if backend.startswith("mock"):
        mock_warn = (
            "<div class='warn dup'><b>연습용으로 실행한 리포트입니다</b>"
            "<div>설계 문서 추출에 실제 모델이 쓰이지 않았습니다. "
            "이 결과를 실제 검증 결과로 사용하지 마세요.</div></div>"
        )
    if s.get("input_kind") == "figma":
        # 초록불의 범위를 리포트가 말한다 — figma 입력은 규칙·성공 조건이 없다.
        mock_warn += (
            "<div class='warn'><b>입력: Figma 디자인</b>"
            "<div>검증 규칙·성공 조건이 없어 정적 대조(라벨·안내 문구·선택 항목)만 "
            "수행했습니다. 규칙 검증은 기획서 입력이 필요합니다.</div></div>"
        )
    if s.get("session_file"):
        mock_warn += (
            f"<div class='warn'><b>세션 파일로 실행됨 — "
            f"{_esc(s['session_file'])}</b>"
            "<div>저장된 로그인 상태가 미리 실렸습니다. 비로그인 가드 검증은 "
            "세션 없는 별도 컨텍스트에서 수행했습니다.</div></div>"
        )
    plan_info = s.get("plan") or {}
    plan_html = ""
    if plan_info:
        # 두 단계 실행 — 추출(계획)과 실행(재개)이 다른 시점·다른 서버에서
        # 일어났다. 판정의 전제이므로 JSON 만이 아니라 HTML 도 말해야 한다.
        plan_warns = "".join(
            f"<li>{_esc(w)}</li>" for w in plan_info.get("warnings", []))
        plan_html = (
            "<div class='warn'><b>두 단계 실행 — 저장된 계획을 재개했습니다</b>"
            f"<div>추출(S1~S2): {_esc(plan_info.get('backend', '?'))} · "
            f"{_esc(plan_info.get('created_at', '?'))} — 실행(S3~S6)은 이후 "
            "별도로 수행됐습니다."
            + (f"<ul>{plan_warns}</ul>" if plan_warns else "")
            + "</div></div>"
        )
    mismatches = s.get("design_mismatches") or []
    if mismatches:
        items = "".join(f"<li>{_esc(m)}</li>" for m in mismatches)
        mock_warn += (
            f"<div class='warn'><b>기획↔디자인 불일치 {len(mismatches)}건</b>"
            f"<div>구현을 고치기 전에 두 입력 중 어느 쪽이 맞는지부터 정해야 "
            f"합니다.<ul>{items}</ul></div></div>"
        )
    edits = s.get("spec_edits") or []
    if edits:
        # 판정 근거의 일부가 기획서가 아니라 사람이 계획 화면에서 적은 값이다 (prova.spec_edits).
        items = "".join(f"<li>{_esc(m)}</li>" for m in edits)
        mock_warn += (
            f"<div class='warn'><b>사람이 고친 추출 결과로 실행 — {len(edits)}건</b>"
            "<div>아래 값은 기획서에서 읽은 것이 아니라 실행 전에 사람이 고친 것입니다. "
            f"이 값에 기댄 판정은 그 수정이 맞을 때만 유효합니다.<ul>{items}</ul></div></div>"
        )

    dry = s.get("dry_run")
    if dry:
        # 판정의 전제 — 쓰기 요청을 막은 케이스는 제출 뒤를 보지 못했다 (prova.dry_run).
        mock_warn += (
            "<div class='warn dup'><b>쓰기 요청을 막고 실행했습니다</b>"
            f"<div>막은 요청 {_esc(dry.get('requests_blocked'))}건 · 그 때문에 확인 불가가 된 케이스 "
            f"{_esc(dry.get('cases_blocked'))}개 · 통과시킨 전제(로그인) 요청 "
            f"{_esc(dry.get('setup_allowed'))}건. 막은 요청이 있는 케이스는 서버 응답을 보지 못해 "
            f"'확인 불가' 로 두었습니다. {_esc(dry.get('limits'))}</div></div>"
        )

    rev = s.get("revision") or {}
    if rev:
        # 기획서끼리의 차이 — 판정 수에 넣지 않는다 (prova.spec_revision).
        changes = rev.get("changes") or []
        items = "".join(f"<li>{_esc(m)}</li>" for m in changes) or "<li>바뀐 것이 없습니다.</li>"
        scope = (f"바뀐 것을 건드리는 케이스 {len(rev.get('touched') or {})}개만 실행했습니다"
                 f"(전체 {_esc(rev.get('cases_available'))}개). 나머지는 이번 실행에서 확인하지 않았습니다."
                 if rev.get("changed_only") else
                 f"바뀐 것을 건드리는 케이스 {len(rev.get('touched') or {})}개에 '개정' 표시를 달았습니다.")
        mock_warn += (
            f"<div class='warn'><b>이전 판 기획서와 비교 — 바뀐 것 {len(changes)}건</b>"
            f"<div>이전 판 <code>{_esc(rev.get('since'))}</code> 과 이번 판의 추출 결과를 비교했습니다. "
            "기획서끼리의 차이이며 결함이 아닙니다. 모델이 같은 문장을 다르게 읽은 것도 차이로 "
            f"보일 수 있으니 원문과 대조하세요. {scope}<ul>{items}</ul></div></div>"
        )

    history = s.get("history") or {}
    if s.get("project"):
        build_meta += f"\n프로젝트 <code>{_esc(s['project'])}</code>"
    if history.get("round"):
        build_meta += f"\n차수 <code>{history['round']}차</code>"
    if s.get("workers"):
        build_meta += f"\n병렬 <code>{_esc(s['workers'])}</code>"
    cache = s.get("llm_cache") or {}
    if cache.get("hits"):
        build_meta += (f"\n저장된 모델 응답 <code>{_esc(cache['hits'])}건 재사용"
                       f" · 새 호출 {_esc(cache.get('misses', 0))}건</code>")
    chart_html = _chart_html(report.cases, len(gaps), len(sel.excluded) if sel else 0, rate)

    # 실행 조건. 한 줄로 이어 쓰면 아홉 가지가 가운뎃점으로 붙어 읽히지 않았다 — 이름과 값을
    # 한 칸씩 나눠 격자로 놓는다. 기획서는 파일 이름만 보이고 전체 경로는 마우스를 올리면 나온다
    # (경로가 길어 다른 칸을 밀어냈다). 시각은 분까지만 적는다.
    spec_name = str(report.spec_source or "").replace("\\", "/").rsplit("/", 1)[-1]
    when = str(report.created_at or "")[:16].replace("T", " ")
    meta_items = [
        f"대상 <code>{_esc(report.target_url)}</code>",
        f"기획서 <code title='{_esc(report.spec_source)}'>{_esc(spec_name)}</code>",
        f"실행한 때 <code title='{_esc(report.created_at)}'>{_esc(when)}</code>",
        f"실행 번호 <code>{_esc(report.run_id)}</code>",
    ]
    if backend:
        meta_items.append(f"모델 <code>{_esc(backend)}</code>")
    # 항목은 줄바꿈으로 나눠 모았다 — 값 안에 가운뎃점이 들어갈 수 있다('켬 · 모델 이름').
    meta_items += [item for item in build_meta.split("\n") if item.strip()]
    meta_html = "".join(f"<div class='mi'>{item}</div>" for item in meta_items)

    names = s.get("screen_names") or {}
    checked = list(dict.fromkeys(v.screen_id for v in report.cases if v.screen_id))
    pairs_html = _design_pairs_html(report, names, checked, spec_figures or {})

    revision = s.get("revision") or {}
    revised = revision.get("touched") or {}
    # 실패 건의 번호 — 카드가 놓이는 순서대로. 틀린 곳 목록과 카드가 같은 번호를 쓴다.
    numbers = {v.case_id: i for i, v in enumerate(
        (v for items in _groups(fails, names).values() for v in items), 1)}
    # 결론 아래 한 줄 — 웹 UI 결과 화면과 같은 말(app.js 의 cond).
    changed = len(history.get("regressed") or []) + len(history.get("fixed") or [])
    cond = " · ".join(x for x in (
        _screens_phrase(names, checked),
        f"{history['round']}번째 실행" if history.get("round") else "",
        "" if not history.get("previous_run") else
        (f"직전보다 새로 실패 {len(history.get('regressed') or [])} · 해결 {len(history.get('fixed') or [])}"
         if changed else "직전과 같은 결과"),
    ) if x)
    fail_section = _grouped_html(fails, names, open_by_default=True, revised=revised,
                                 target_url=report.target_url, numbers=numbers) or         "<div class='empty'>실패한 케이스가 없습니다.</div>"
    pass_section = _grouped_html(passes, names, open_by_default=False, revised=revised) or         "<div class='empty'>통과한 케이스가 없습니다.</div>"

    # 기획서와 다름·실행 문제의 수는 비율 막대 아래 집계 줄에 이미 있다. 실행 문제가 있을 때만
    # '도구·환경을 먼저 확인' 을 덧붙인다.
    n_infra = sum(1 for v in fails if fail_kind(v) == "infra")
    # 실패 케이스·통과 케이스 바로 아래 작은 글씨로 둔다 — 그 목록에 대한 말이다.
    breakdown = (f"<p class='smallnote'><b>실행 문제 {n_infra}건</b>은 "
                 "기획서와의 차이가 아니라 도구·환경 문제일 수 있습니다 — 먼저 확인하세요.</p>"
                 if n_infra else "")
    weak_note = ""
    weak = sum(1 for v in passes if is_weak_pass(v))
    if weak:
        weak_note = (f"<p class='smallnote'>성공 조건이 없어 '에러 없음'만 확인한 정상 케이스 "
                     f"<b>{weak}건</b> — 기획서의 성공 조건에 이동 경로나 문구가 있으면 더 강하게 확인합니다.</p>")

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="color-scheme" content="light dark">
<script>{_THEME_JS}</script>
<title>Prova 검증 리포트 · {_esc(report.run_id)}</title>
<style>{_CSS}</style>
<script>if(self!==top)document.documentElement.className='embedded'</script></head>
<body>
<header class="topbar">
<div class="crumbs">{f"<b title='{_esc(report.spec_source)}'>{_esc(spec_name)}</b><span aria-hidden='true'>→</span>" if spec_name else ""}<span>{_esc(report.target_url)}</span></div>
<div class="name">{_WORDMARK}</div>
<div class="when"><span>검증 리포트 · {_esc(when)}</span>{THEME_BUTTON}</div>
</header>
<div class="wrap">
<div class="result-head">
<div><h1>{_conclusion(report.cases, total)}</h1>{f"<div class='cond'>{_esc(cond)}</div>" if cond else ""}</div>
<div class="actions"><a class="btn" href="report.xlsx" download>{_ICON_DOWNLOAD}엑셀 받기</a><a class="btn" id="pdfBtn" hidden download>{_ICON_DOWNLOAD}PDF 받기</a></div>
</div>
{chart_html}
{f"<div class='warn'><b>{_esc(s['url_note'])}</b></div>" if s.get("url_note") else ""}
{mock_warn}{filter_warn}

<h2>실패 케이스 ({len(fails)})</h2>
{fail_section}
{breakdown}{missed_note}

<details class='passfold'><summary><h2>통과 케이스 ({len(passes)})</h2>
<span class='ms'>확인할 것 없음 · 펼치기</span></summary>
{pass_section}
</details>
{weak_note}
{sel_html}
{_brief_html(report, names, checked, fails, numbers, gaps, backend, pairs_html)}
</div><script>{_LIGHTBOX_JS}</script><script>{_COPY_JS}</script><script>{_TRACE_JS}</script><script>{_PRINT_JS}</script><script>{_THEME_BTN_JS}</script><script>{_PDF_BTN_JS}</script></body></html>
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


#: 리포트와 함께 두는 글꼴 — Pretendard 가변 글꼴과 그 라이선스(SIL OFL 1.1, 함께 보내야 한다).
FONT_DIR = Path(__file__).parent / "fonts"
FONT_FILES = ("PretendardVariable.woff2", "Pretendard-OFL.txt")


def copy_fonts(out_dir: Path) -> None:
    """리포트 폴더의 fonts/ 에 글꼴을 둔다. 이미 같은 크기의 파일이 있으면 두고 간다."""
    dest = out_dir / "fonts"
    dest.mkdir(parents=True, exist_ok=True)
    for name in FONT_FILES:
        src, dst = FONT_DIR / name, dest / name
        if src.exists() and not (dst.exists() and dst.stat().st_size == src.stat().st_size):
            shutil.copyfile(src, dst)


def save_html(report: TestReport, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    fill_pending_from_plan(report, out_dir)
    copy_fonts(out_dir)
    path = out_dir / "report.html"
    path.write_text(render_html(report, build_spec_figures(report, out_dir)), encoding="utf-8")
    return path


#: CSV 결과표의 칸. 엑셀(xlsx_export) 의 '케이스' 시트와 같은 내용을 한 장으로 — 차수끼리
#: 비교하거나 다른 도구(스프레드시트·diff)에 넣을 때 쓴다. 앞 다섯 칸의 순서는 바꾸지 않는다.
CSV_COLUMNS = ["화면", "흐름", "케이스", "제목", "판정", "실패 원인",
               "기획서 기대", "실제 화면", "상세"]


def save_csv(report: TestReport, out_dir: Path) -> Path:
    """케이스 한 줄씩 report.csv 로 남긴다.

    utf-8-sig(BOM)로 쓴다 — BOM 이 없으면 엑셀이 CSV 를 열 때 한글을 시스템 코드 페이지로
    읽어 깨뜨린다.
    """
    import csv

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "report.csv"
    names = report.summary.get("screen_names") or {}
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_COLUMNS)
        for v in report.cases:
            ev = v.evidence or {}
            category = (CATEGORY_LABELS.get(v.failure_category, CATEGORY_LABELS["unknown"])[0]
                        if v.verdict == "FAIL" else "")
            writer.writerow([
                names.get(v.screen_id, v.screen_id), v.flow_id or "", v.case_id,
                v.plain or v.title, v.verdict, category,
                str(ev.get("expected") or ""), str(ev.get("actual") or ""),
                v.failure_detail or "",
            ])
    return path
