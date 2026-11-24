/* Prova 작업 콘솔.
 *
 * 프레임워크를 쓰지 않는다. 상태가 셋뿐이고(설정·계획·결과) 화면 전환이 없으므로
 * 프레임워크의 값보다 빌드 단계와 CDN 의존이 더 비싸다 — 리포트가 폐쇄망에서
 * 열려야 한다는 원칙과 같은 이유다.
 *
 * 틀은 macOS 앱이다(2026-11-24, Apple macOS 27 UI Kit). 한 번에 한 단계만 보여 준다:
 *   1 기획서   — 사이드바: 실행 기록      · 내용: 설정식 묶음 상자
 *   2 항목 검토 — 사이드바: 규칙 종류·화면  · 내용: 항목 표 + 오른쪽 원문·절차
 *   3 실행     — 사이드바: 진행 단계      · 내용: 진행 막대 + 항목별 상태
 *   4 결과     — 사이드바: 판정별 묶음    · 내용: 숫자 칸 + 실패 목록·상세(report.json)
 * body[data-view] 가 어느 사이드바·내용을 보일지 정한다(form · plan · busy · result).
 */
"use strict";

// ── 유틸 ───────────────────────────────────────────────────────────────────

const $ = (id) => document.getElementById(id);

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const ICON = {
  info: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="8" cy="8" r="6.6" stroke="currentColor" stroke-width="1.4"/><path d="M8 7.2v4M8 4.9v.1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`,
  warn: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M8 2.2l6 10.6H2L8 2.2z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M8 6.4v3M8 11.2v.1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`,
  fail: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="8" cy="8" r="6.6" stroke="currentColor" stroke-width="1.4"/><path d="M5.8 5.8l4.4 4.4M10.2 5.8l-4.4 4.4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`,
  search: `<svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><circle cx="6" cy="6" r="4.2" stroke="currentColor" stroke-width="1.5"/><path d="M9.2 9.2l3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`,
  caution: `<svg width="28" height="28" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.2 2.6 19.6h18.8L12 3.2z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M12 9.4v4.8M12 16.6v.2" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>`,
  download: `<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2.5v8M5 7.5l3 3 3-3M3 13h10"/></svg>`,
  open: `<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M9.5 2.5h4v4M13.5 2.5 8 8M11.5 9.5v4h-9v-9h4"/></svg>`,
  again: `<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M13 8a5 5 0 1 1-1.6-3.7M13 2.8v2.6h-2.6"/></svg>`,
  copy: `<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="5.5" y="5.5" width="8" height="8" rx="1.6"/><path d="M10.5 3.6V3.5a1 1 0 0 0-1-1h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h.1"/></svg>`,
  check: `<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.4l3 3 6-6.6"/></svg>`,
};

// 알림 상자의 종류를 읽어 주는 프로그램에도 알린다 — 21st.dev Notifications 의 role 에서.
// 오류는 바로 끼어들어 읽고(alert), 주의·참고는 하던 말을 마친 뒤 읽는다(status).
// 종류는 아이콘 모양과 색으로만 보이므로 앞에 낱말을 숨겨 붙인다(HIG: 색·모양만으로 전하지 않는다).
// 닫기(×)는 넣지 않는다 — 디자인 기준 1번 '알림 상자는 숨기거나 접지 않는다'.
const ALERT_SAY = { fail: ["alert", "오류"], warn: ["status", "주의"], info: ["status", "참고"] };

function alertBox(kind, title, why) {
  const [role, say] = ALERT_SAY[kind] || ALERT_SAY.info;
  why = oneSentencePerLine(why);
  return `<div class="alert ${kind}" role="${role}">${ICON[kind] || ICON.info}<div>` +
    `<b><span class="sr">${say}: </span>${title}</b>${why ? `<div class="why">${why}</div>` : ""}</div></div>`;
}

/** 짧은 두 문장(각 25자 안팎)은 한 줄에 한 문장 — 문장 끝에서 줄을 바꿔 낱말 중간에서 꺾이지 않게. 태그가 든 글은 그대로. */
function oneSentencePerLine(html) {
  if (!html || /[<>]/.test(html)) return html;
  const parts = String(html).split(/(?<=[.!?])\s+(?=\S)/);
  if (parts.length !== 2 || parts.some((p) => p.length > 27)) return html;
  return parts.map((p) => `<span class="ln">${p}</span>`).join(" ");
}

/**
 * 판정 표시 — 채운 원 안의 모양이 뜻을 진다(21st.dev Status Badge 의 '상태마다 다른 모양' 에서).
 * 통과 ✓ · 기획서와 다름 ✕ · 실행 문제 ! · 확인 불가 ? — 색을 못 가려도 읽힌다(HIG).
 * 진행 표시는 판정이 아니다: 할 차례는 빈 원, 도는 중은 파란 호, 끝난 단계는 파란 체크. 초록은 판정에만.
 */
const VM_PATH = {
  ok: `<path d="M5.1 8.3l1.9 1.9 3.9-4.2"/>`,
  done: `<path d="M5.1 8.3l1.9 1.9 3.9-4.2"/>`,
  fail: `<path d="M5.6 5.6l4.8 4.8M10.4 5.6l-4.8 4.8"/>`,
  infra: `<path d="M8 4.5v4.3M8 11.3v.1"/>`,
  unv: `<path d="M6.2 6.3a1.8 1.8 0 1 1 2.6 1.6c-.5.3-.8.6-.8 1.1v.2M8 11.4v.1"/>`,
};
const VM_SAY = { ok: "통과", fail: "기획서와 다름", infra: "실행 문제", unv: "확인 불가",
                 wait: "할 차례", run: "확인 중", done: "끝남" };
function vmark(kind, { dot = false, say = true } = {}) {
  const ring = kind === "wait" || kind === "run";
  return `<svg class="vm ${kind}${dot ? " dot" : ""}" viewBox="0 0 16 16" aria-hidden="true">` +
    `<circle class="f" cx="8" cy="8" r="${ring ? 6.6 : 7.6}"/>` +
    (kind === "run" ? `<circle class="arc" cx="8" cy="8" r="6.6"/>` : "") + (VM_PATH[kind] || "") +
    `</svg>` + (say ? `<span class="sr">${VM_SAY[kind] || ""} </span>` : "");
}

/**
 * 되돌릴 수 없는 일 앞에서 한 번 묻는 창 — 브라우저 <dialog> 로, 키트의 경고창 규격대로
 * (폭 260, 가운데 정렬, 버튼은 세로로 쌓은 28px 알약). 초점 가두기·Esc·뒤 화면 막기는 브라우저가 한다.
 * 처음 초점은 안전한 쪽(keep, 파란 기본 버튼). Esc·바깥 누르기도 keep.
 * '멈추기' 를 빨갛게 칠하지 않는다 — 빨강은 '기획서와 다름' 에만 쓴다(디자인 기준 2번). 말이 뜻을 진다.
 */
function confirmDialog({ title, body, keep, go }) {
  return new Promise((resolve) => {
    const d = document.createElement("dialog");
    d.className = "confirm";
    d.setAttribute("aria-labelledby", "cfTitle");
    d.setAttribute("aria-describedby", "cfBody");
    // 본문은 문장마다 한 줄 — 배열로 받으면 줄을 나눈다(짧은 두 문장이 낱말 중간에서 꺾이지 않게, hh 11-25)
    const lines = Array.isArray(body) ? body : [body];
    d.innerHTML = `<div class="ai">${ICON.caution}</div><h2 id="cfTitle">${esc(title)}</h2>` +
      `<p id="cfBody">${lines.map((l) => `<span class="ln">${esc(l)}</span>`).join(" ")}</p>` +
      `<div class="col"><button class="btn primary" type="button" value="keep" autofocus>${esc(keep)}</button>` +
      `<button class="btn" type="button" value="go">${esc(go)}</button></div>`;
    document.body.appendChild(d);
    const done = (ok) => { if (d.open) d.close(); d.remove(); resolve(ok); };
    d.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (b) { done(b.value === "go"); return; }
      const r = d.getBoundingClientRect();  // 창 바깥(뒤 화면)을 누르면 keep
      if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) done(false);
    });
    d.addEventListener("cancel", (e) => { e.preventDefault(); done(false); });  // Esc
    d.showModal();
  });
}

// ── 움직임 ─────────────────────────────────────────────────────────────────
// 상태가 바뀔 때만 움직인다 — 단계 이동, 항목 완료, 숫자 바뀜. 들어올 때 장식으로 흔들지 않는다.
// 화면 설정이 '동작 줄이기' 면 바뀐 모습만 바로 보인다.
/**
 * 잠깐 뜨는 확인 한 줄 — '복사했어요' 처럼 방금 한 일이 됐다는 말만. 경고·오류는 여기 쓰지 않는다
 * (알림은 닫히거나 사라지지 않는다 — 디자인 기준 1번). 화면 읽기 프로그램에는 status 로 읽힌다.
 */
let toastTimer = null;
function toast(text) {
  let el = $("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast"; el.className = "toast"; el.setAttribute("role", "status");
    document.body.appendChild(el);
  }
  el.innerHTML = `${ICON.check || ""}<span>${esc(text)}</span>`;
  el.dataset.on = "1";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { delete el.dataset.on; }, 2600);
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch (e) { /* 아래 옛 방식으로 */ }
  const ta = document.createElement("textarea");
  ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.appendChild(ta); ta.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
  ta.remove();
  return ok;
}

/**
 * 다른 탭에 가 있는 사이 끝나면 탭 제목으로 알린다 — 알림 권한을 묻지 않는다.
 * 돌아오면 원래 제목으로.
 */
function notifyDone(title) {
  if (!document.hidden) return;
  document.title = `${title} · Prova`;
  const back = () => {
    if (document.hidden) return;
    document.removeEventListener("visibilitychange", back);
    if (!state.busy) document.title = pageTitle();
  };
  document.addEventListener("visibilitychange", back);
}

const reduceMotion = () =>
  !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

/**
 * 바뀐 숫자만 아래에서 위로 밀어 바꾼다 (21st.dev 'Agent Todo List' 의 개수 표시).
 * 실행 중 판정 수처럼 몇 초마다 바뀌는 숫자에 쓴다. 처음 값은 그냥 쓴다.
 */
function swapNumber(el, to) {
  if (!el) return;
  to = String(to);
  const from = el.dataset.v;
  if (from === to) return;
  el.dataset.v = to;
  if (from === undefined || reduceMotion() || !el.animate) { el.textContent = to; return; }
  el.innerHTML = `<span class="sw"><span>${esc(from)}</span><span>${esc(to)}</span></span>`;
  const [a, b] = el.firstChild.children;
  const opt = { duration: 220, easing: "cubic-bezier(0.2, 0.7, 0.2, 1)" };
  a.animate([{ transform: "translateY(0)", opacity: 1 }, { transform: "translateY(-100%)", opacity: 0 }],
            { ...opt, fill: "forwards" });
  b.animate([{ transform: "translateY(100%)", opacity: 0 }, { transform: "translateY(0)", opacity: 1 }], opt)
    .finished.then(() => { if (el.dataset.v === to) el.textContent = to; }).catch(() => {});
}

/**
 * 결과 숫자를 자리마다 0에서 굴려 세운다 (21st.dev 'Count Up Animation' 의 roll).
 * 결과가 처음 나올 때 한 번만 돈다. 화면 읽기 프로그램은 완성된 숫자를 그대로 읽는다.
 */
function rollIn(el) {
  const text = el.textContent;
  if (reduceMotion() || !el.animate || !/\d/.test(text)) return;
  const strip = "0123456789".split("").map((d) => `<span>${d}</span>`).join("");
  el.innerHTML = `<span class="sr">${esc(text)}</span>` + [...text].map((ch) => /\d/.test(ch)
    ? `<span class="dg" aria-hidden="true"><span class="strip">${strip}</span><span class="ghost">${ch}</span></span>`
    : `<span aria-hidden="true">${esc(ch)}</span>`).join("");
  el.querySelectorAll(".dg").forEach((d) => {
    const n = Number(d.querySelector(".ghost").textContent);
    d.querySelector(".strip").animate(
      [{ transform: "translateY(0)" }, { transform: `translateY(${-n * 10}%)` }],
      { duration: 700, easing: "cubic-bezier(0.3, 0.5, 0.2, 1)", fill: "forwards" });
  });
}

/**
 * 누른 뒤 바로 끝나지 않는 버튼 — 버튼 안에서 '하는 중' 으로 바뀐다.
 * Apple HIG Buttons: 바로 끝나지 않는 동작은 버튼 안에 진행 표시를 띄운다.
 * 버튼은 줄어들지 않는다(옆 버튼이 밀려 움직이지 않게). 눌린 동안은 다시 누를 수 없다.
 */
function busyButton(btn, label) {
  if (!btn || btn.getAttribute("aria-busy") === "true") return;
  btn.dataset.idle = btn.innerHTML;
  btn.style.minWidth = `${btn.offsetWidth}px`;
  btn.disabled = true;
  btn.setAttribute("aria-busy", "true");
  btn.innerHTML = `<span class="btn-spin" aria-hidden="true"></span><span>${esc(label)}</span>`;
}

function idleButton(btn) {
  if (!btn || btn.getAttribute("aria-busy") !== "true") return;
  btn.innerHTML = btn.dataset.idle || btn.innerHTML;
  delete btn.dataset.idle;
  btn.style.minWidth = "";
  btn.disabled = false;
  btn.removeAttribute("aria-busy");
}

/**
 * 미끄러지는 선택 판 — 단계 표시와 예시 사이트 고르기의 흰 판 하나가 새 자리로 옮겨 간다.
 * 두 끝이 서로 다른 빠르기의 용수철(임계 감쇠 — 넘치지 않는다)로 따라가서, 움직이는 동안만 판이 살짝
 * 늘어났다가 0.25초 안에 제 폭으로 멎는다. 새로 누르면 지금 자리와 속도에서 이어 간다.
 * 임계 감쇠의 해를 그대로 써서 프레임 간격이 들쭉날쭉해도 같은 모양으로 움직인다.
 * host 에 --thumb-l(왼쪽 끝) · --thumb-w(폭) 를 적는다. 그리는 쪽(CSS 의 ::before)이 읽는다.
 */
function stretchThumb(host) {
  const s = { a: { x: 0, v: 0 }, b: { x: 0, v: 0 }, x: 0, hw: 0, hwNow: 0, raf: 0, last: 0, ready: false };
  const paint = () => {
    const sep = Math.abs(s.a.x - s.b.x);
    host.style.setProperty("--thumb-l", `${Math.min(s.a.x, s.b.x) - s.hwNow}px`);
    host.style.setProperty("--thumb-w", `${sep + 2 * s.hwNow}px`);
  };
  const step = (dt) => {
    let still = true;
    s.hwNow += (s.hw - s.hwNow) * Math.min(1, dt * 12);
    if (Math.abs(s.hw - s.hwNow) > 0.3) still = false;
    [s.a, s.b].forEach((edge) => {
      const w = edge === s.a ? 30 : 23;          // 앞 끝이 조금 빨라서 그 차이만큼 늘어난다
      const off = edge.x - s.x;
      const slope = edge.v + w * off;
      const decay = Math.exp(-w * dt);
      edge.x = s.x + (off + slope * dt) * decay;
      edge.v = (edge.v - w * slope * dt) * decay;
      if (Math.abs(s.x - edge.x) > 0.3 || Math.abs(edge.v) > 3) still = false;
    });
    return still;
  };
  const snap = () => {
    s.a.x = s.b.x = s.x; s.a.v = s.b.v = 0; s.hwNow = s.hw;
    cancelAnimationFrame(s.raf); s.raf = 0;
    paint();
  };
  const loop = () => {
    if (s.raf) return;
    s.last = performance.now();
    const tick = (now) => {
      const dt = Math.min((now - s.last) / 1000, 1 / 30);
      s.last = now;
      if (step(dt)) { s.raf = 0; snap(); return; }
      paint();
      s.raf = requestAnimationFrame(tick);
    };
    s.raf = requestAnimationFrame(tick);
  };
  return {
    /** el 아래로 판을 옮긴다. 처음 자리·창 크기 바뀜·동작 줄이기 설정에서는 바로 옮긴다. */
    to(el, { instant = false } = {}) {
      if (!el || !el.offsetWidth) { s.ready = false; return; }   // 숨어 있으면 다음에 처음처럼
      const x = el.offsetLeft + el.offsetWidth / 2;
      s.hw = el.offsetWidth / 2;
      const moved = Math.abs(x - s.x) > 0.5;
      s.x = x;
      if (!s.ready || instant || reduceMotion()) { s.ready = true; snap(); return; }
      if (!moved) { s.hwNow = s.hw; paint(); return; }
      loop();
    },
  };
}


// ── 서버 통신 ──────────────────────────────────────────────────────────────

class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function api(path, opts) {
  let res;
  try {
    res = await fetch(path, opts);
  } catch (e) {
    // 서버가 죽었거나 네트워크가 끊긴 경우. 원인을 사람 말로 바꿔 준다.
    throw new ApiError("서버에 연결하지 못했어요. prova serve 가 켜져 있는지 확인해 주세요.", 0);
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(detailText(body.detail) || `${res.status} ${res.statusText}`, res.status);
  return body;
}

// FastAPI 의 422 는 detail 이 배열이다. 그대로 쓰면 화면에 [object Object] 가 뜬다.
function detailText(detail) {
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || JSON.stringify(d)).join(" / ")
      || "요청 형식이 올바르지 않아요";
  }
  return detail;
}

/**
 * 작업이 끝날 때까지 진행 메시지를 이어 받는다.
 *
 * since 로 읽는 이유는 runner.py 와 같다 — 늦게 붙어도 처음부터 따라올 수 있다.
 *
 * 연속 실패에 상한을 둔다. 상한이 없으면 서버가 죽었을 때 화면이 영원히
 * '실행 중' 으로 남아, 사람은 오래 걸리는 것과 끊긴 것을 구분할 수 없다.
 */
async function follow(jobId, onMessages) {
  let since = 0, misses = 0;
  const MAX_MISS = 5;
  for (;;) {
    let job;
    try {
      job = await api(`/api/job/${jobId}?since=${since}`);
      misses = 0;
    } catch (e) {
      if (++misses >= MAX_MISS) {
        throw new ApiError("서버와 연결이 끊겼어요. 작업은 계속 돌고 있을 수 있어요.", 0);
      }
      await sleep(600);
      continue;
    }
    since = job.next;
    if (job.messages.length) onMessages(job.messages);
    if (job.status === "error") throw new ApiError(job.error, 500);
    if (job.status === "done") return job.result;
    await sleep(400);
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── 상태 ───────────────────────────────────────────────────────────────────

const state = {
  plan: null,        // 계획 확인 중인 목록
  result: null,      // 마지막으로 본 실행 결과 ({run_id, summary, report_url})
  report: null,      // 그 결과의 report.json
  filter: "",        // 항목 검색어
  onlyOff: false,    // 꺼 둔 것만 보기
  rule: "",          // 사이드바에서 고른 규칙 종류 ("" = 전체)
  group: "",         // 사이드바에서 고른 화면·흐름 ("" = 전체)
  sel: "",           // 항목 표에서 고른 줄 (case_id)
  mode: "items",     // 항목 검토 화면: items(항목 표) · spec(기획서에서 읽은 내용)
  resKind: "",       // 결과 화면: 사이드바에서 고른 판정 묶음
  resSel: "",        // 결과 화면: 목록에서 고른 항목 (case_id)
  serverBackend: "mock",
  busy: false,
  specGroups: [],    // 기획서 묶음 — 프로젝트 폴더들, 프로젝트 없이 올린 것, 예시
  projects: [],      // 고를 수 있는 프로젝트 이름
  runs: [],          // 실행 기록
  runsOpen: {},      // 실행 기록 묶음마다 '이전 기록 더 보기' 를 눌렀는지
};

const LS = "prova.settings.v1";

function saveSettings() {
  try {
    localStorage.setItem(LS, JSON.stringify({
      pdf: $("pdf").value, url: $("url").value, backend: $("backend").value,
      figma: $("figma").value, project: $("project").value.trim(),
      screenUrls: $("screenUrls").value,
    }));
  } catch (e) { /* 저장 못 해도 기능은 그대로 돈다 */ }
}

function loadSettings() {
  try { return JSON.parse(localStorage.getItem(LS)) || {}; } catch (e) { return {}; }
}

function form() {
  return {
    pdf: $("pdf").value,
    url: $("url").value.trim(),
    request: $("request").value.trim() || null,
    backend: $("backend").value,
    figma: $("figma").value || null,
    project: $("project").value.trim(),
    screen_urls: screenUrls().urls,
  };
}

// '화면 이름=/경로' 줄들을 읽는다. 빈 줄은 건너뛰고, '=' 가 없거나 한쪽이 빈 줄은 틀린 줄로
// 모은다 — 조용히 버리면 그 화면이 0건으로 끝나도 사람이 이유를 모른다.
function screenUrls() {
  const urls = {};
  const bad = [];
  for (const raw of $("screenUrls").value.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const i = line.indexOf("=");
    const name = i < 0 ? "" : line.slice(0, i).trim();
    const path = i < 0 ? "" : line.slice(i + 1).trim();
    if (!name || !path) bad.push(line);
    else urls[name] = path;
  }
  return { urls, bad };
}

function renderScreenUrlsErr() {
  const { bad } = screenUrls();
  const box = $("screenUrlsErr");
  box.hidden = bad.length === 0;
  box.textContent = bad.length ? `'화면 이름=/경로' 모양이 아닌 줄: ${bad.join(", ")}` : "";
}

const specName = () => (form().pdf || "").split(/[\\/]/).pop() || "기획서 없음";

// ── 창 틀 — 도구 막대 · 단계 · 사이드바 ─────────────────────────────────────

// 화면에 보이는 이름. 값(mock·vllm·replay)은 서버와 주고받는 이름이라 그대로 둔다.
const BACKEND_NAME = { mock: "연습용", vllm: "실제 모델", replay: "저장된 응답" };

// 탭에는 앱 이름만 — 할 말이 있을 때만(실행 중, 숨은 탭에서 끝남) 앞에 상태를 붙인다(hh 11-25).
const pageTitle = () => "Prova";

function renderChrome() {
  syncStepper();
  if (!state.busy) document.title = pageTitle();
  const f = form();
  // 올리는 중이거나 고른 기획서가 없으면 다음 단계로 못 간다 — 반쯤 올라간 파일로 돌지 않게.
  const uploading = $("uploadBtn").getAttribute("aria-busy") === "true";
  $("planBtn").disabled = state.busy || uploading || !f.pdf;
  if ($("tryBtn")) $("tryBtn").disabled = state.busy || uploading;
  // 실행 옵션은 접혀 있다 — 지금 값은 접힌 채로도 보여야 모르고 켠 채 돌리지 않는다.
  const nUrls = Object.keys(f.screen_urls).length;
  $("optsNow").textContent = [BACKEND_NAME[f.backend] || f.backend, f.figma && "Figma 함께",
    nUrls && `화면 주소 ${nUrls}개`,
    $("vlm").checked && "이미지로 찾기 켬", $("dryRun").checked && "쓰기 막기 켬",
  ].filter(Boolean).join(" · ");
  if (document.body.dataset.view === "form") renderRunsFoot();
}

function setBar(title, sub) {
  $("barTitle").textContent = title;
  $("barSub").textContent = sub || "";
}

/**
 * 어느 화면을 보일지 — view 는 사이드바·내용의 종류, step 은 위쪽 경로에서 몇 단계인지.
 * 도구 막대의 오른쪽 할 일과 사이드바 아래 줄은 화면마다 새로 채운다.
 */
function setView(view, step) {
  const prev = Number(document.body.dataset.step) || 0;
  const prevView = document.body.dataset.view;
  document.body.dataset.view = view;
  document.body.dataset.step = step;
  for (const el of $("stepper").querySelectorAll("[data-step]")) {
    const s = Number(el.dataset.step);
    if (s === step) el.setAttribute("aria-current", "step");
    else el.removeAttribute("aria-current");
    // 지난 단계는 파란 체크, 지금 단계는 흰 판 위의 파란 번호, 남은 단계는 회색 번호.
    const li = el.parentElement, was = li.dataset.state, no = el.querySelector(".no");
    li.dataset.state = s < step ? "done" : s === step ? "now" : "next";
    no.textContent = s < step ? "✓" : String(s);
    // 방금 지난 단계가 됐으면 체크가 튀어 들어온다 — 처음 그릴 때(was 없음)와 동작 줄이기에서는 없다
    if (was && was !== "done" && li.dataset.state === "done" && !reduceMotion()) {
      no.classList.remove("pop"); void no.offsetWidth; no.classList.add("pop");
      no.addEventListener("animationend", () => no.classList.remove("pop"), { once: true });
    }
  }
  $("barActions").innerHTML = "";
  $("sideFoot").textContent = "";
  $("sideFoot").removeAttribute("title");
  syncStepper();
  placeThumb();
  if (view === "form") placeSegThumb(true);
  if (!state.busy) document.title = pageTitle();
  if (prev && (prev !== step || prevView !== view)) stepChanged(prev, step);
}

/**
 * 갈 수 있는 단계만 누를 수 있다 (21st.dev 'Wizard Steps' 의 '가 본 곳까지만').
 * 3 실행은 실행 중에만 보이는 단계라 단추가 아니다.
 */
function syncStepper() {
  for (const b of $("stepper").querySelectorAll("button[data-step]")) {
    const n = b.dataset.step;
    b.disabled = state.busy || (n === "2" && !state.plan) || (n === "4" && !state.result);
  }
}

/**
 * 단계가 바뀔 때 — 'Wizard Steps' 에서 세 가지만 가져왔다.
 * 1) 앞 단계로 가면 새 화면이 오른쪽에서, 뒤로 가면 왼쪽에서 12px 들어온다. 어느 쪽으로
 *    움직였는지가 보인다. 나가는 화면은 기다리지 않는다(화면을 늦게 바꾸지 않는다).
 * 2) 화면 읽기 프로그램에 '4단계 중 2단계, 항목 검토' 를 알린다.
 * 3) 누른 단추가 새 화면에 없으면 초점을 새 화면으로 옮긴다 — 문서 맨 앞으로 튀지 않게.
 */
function stepChanged(prev, n) {
  const main = document.querySelector(".main");
  const content = document.querySelector(".content");
  const lb = $("stepper").querySelector(`[data-step="${n}"] > .lb`);
  $("stepSay").textContent = `4단계 중 ${n}단계, ${lb ? lb.textContent : ""}`;
  if (!reduceMotion() && content.animate && n !== prev) {
    const d = n > prev ? 1 : -1;
    // 길이·곡선은 토큰(--dur-3 · --ease-out)을 읽는다
    const css = getComputedStyle(document.documentElement);
    content.animate([{ opacity: 0, transform: `translateX(${d * 12}px)` }, { opacity: 1, transform: "none" }],
                    { duration: parseFloat(css.getPropertyValue("--dur-3")) || 250,
                      easing: css.getPropertyValue("--ease-out").trim() || "ease-out" });
  }
  requestAnimationFrame(() => {
    const a = document.activeElement;
    if (a && a !== document.body && a.isConnected && a.getClientRects().length) return;
    main.focus({ preventScroll: true });
  });
}

// 지금 단계의 흰 판은 하나뿐이고, 단계가 바뀌면 그 판이 옆 단계로 미끄러진다. 처음 자리·창 크기 바뀜은 움직이지 않는다.
// 움직임은 CSS 가 맡는다(.path 의 --thumb-* 전환 300ms) — 여기서는 끝 자리만 적는다. offset* 는 확대 전 값이라 zoom 과 맞는다.
function placeThumb() {
  const st = $("stepper");
  const now = st.querySelector("[data-step][aria-current]");
  if (!now || !now.offsetWidth) return;
  const first = !st.dataset.ready;
  if (first || placeThumb.resizing) st.classList.add("snap");
  st.style.setProperty("--thumb-l", `${now.offsetLeft}px`);
  st.style.setProperty("--thumb-w", `${now.offsetWidth}px`);
  if (st.classList.contains("snap")) { void st.offsetWidth; st.classList.remove("snap"); }
  st.dataset.ready = "1";
}
window.addEventListener("resize", () => {
  placeThumb.resizing = true; placeThumb(); placeSegThumb(true); placeThumb.resizing = false;
});

$("stepper").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-step]");
  if (state.busy || !btn || btn.disabled) return;
  const n = btn.dataset.step;
  if (n === "1") showBlank();
  if (n === "2" && state.plan) showPlan();
  if (n === "4" && state.result) showResult(state.result);
});

$("newBtn").addEventListener("click", () => { if (!state.busy) showBlank(); });

// ── 사이드바 — 접기, 고른 줄로 미끄러지는 판, 굴릴 때만 보이는 스크롤 막대 (21st.dev Sidebar 에서 움직임만) ──
(() => {
  const root = document.documentElement, side = document.querySelector(".side"), panes = $("sidePanes");
  const tog = $("sideToggle");
  const say = () => {
    const rail = root.classList.contains("side-rail");
    tog.setAttribute("aria-expanded", String(!rail));
    tog.setAttribute("aria-label", rail ? "사이드바 표시" : "사이드바 숨기기");
    tog.removeAttribute("title");
    panes.inert = rail;
  };
  tog.addEventListener("click", () => {
    const rail = root.classList.toggle("side-rail");
    try { localStorage.setItem("prova-side", rail ? "rail" : "open"); } catch (e) { /* 저장은 덤 */ }
    say();
    tip.hidden = true;
    // 키보드로 접고 폈으면 이름표를 새 이름으로 다시 띄운다(초점은 같은 단추에 남는다)
    if (document.activeElement === tog && tog.matches(":focus-visible")) showTip(tog, ...TIPS[0][1]());
  });
  $("railNew").addEventListener("click", () => { if (!state.busy) showBlank(); });
  say();

  // ⌘\ (맥) · Ctrl+\ (그 밖) 로 접고 편다 — 브라우저 단축키와 겹치지 않는 자리
  const mac = /mac|iphone|ipad/i.test(navigator.userAgentData?.platform || navigator.platform || "");
  tog.setAttribute("aria-keyshortcuts", mac ? "Meta+Backslash" : "Control+Backslash");
  document.addEventListener("keydown", (e) => {
    if (e.key === "\\" && (mac ? e.metaKey : e.ctrlKey) && !e.altKey && !e.shiftKey) { e.preventDefault(); tog.click(); }
  });

  // 접힌 줄의 이름표 — 마우스는 0.5초 머문 뒤, 키보드 초점은 바로. 이름 + 단축키(있으면)
  const tip = $("railTip");
  // 이름은 그때그때 — 접기 단추는 펼침·접힘에서 말이 다르다. 접기 단추 이름표는 펼친 상태에서도 뜬다.
  const KEY = mac ? "⌘\\" : "Ctrl \\";
  const TIPS = [[tog, () => [root.classList.contains("side-rail") ? "사이드바 표시" : "사이드바 숨기기", KEY]],
                [$("railNew"), () => ["새 확인", ""]],
                [$("themeBtn"), () => [$("themeBtn").getAttribute("aria-checked") === "true" ? "어둡게 끄기" : "어둡게 켜기", ""]]];
  let tipT = 0;
  const showTip = (el, label, key) => {
    if (!root.classList.contains("side-rail") && el !== tog) return;
    tip.innerHTML = `${esc(label)}${key ? `<kbd class="kbd">${esc(key)}</kbd>` : ""}`;
    tip.style.top = `${el.offsetTop + el.offsetHeight / 2}px`;   // .side 기준 — 화면 배율(zoom)과 상관없다
    tip.hidden = false;
    el.setAttribute("aria-describedby", "railTip");
  };
  const hideTip = (el) => { clearTimeout(tipT); tip.hidden = true; el.removeAttribute("aria-describedby"); };
  TIPS.forEach(([el, what]) => {
    el.addEventListener("pointerenter", () => { clearTimeout(tipT); tipT = setTimeout(() => showTip(el, ...what()), 500); });
    el.addEventListener("pointerleave", () => hideTip(el));
    el.addEventListener("focus", () => { if (el.matches(":focus-visible")) showTip(el, ...what()); });
    el.addEventListener("blur", () => hideTip(el));
    el.addEventListener("keydown", (e) => { if (e.key === "Escape") hideTip(el); });
  });

  // 판 하나 — 보이는 목록에서 고른 줄이 딱 하나일 때만 쓴다. 여럿이면 줄마다 제 배경을 둔다.
  const pill = document.createElement("span");
  pill.className = "side-pill";
  pill.setAttribute("aria-hidden", "true");
  panes.prepend(pill);
  let lastPane = null, shown = false, hideT = 0;
  const place = (instant = false) => {
    // 접힌 줄에서는 목록이 숨어 있다 — 그 좁은 모양으로 재 두면 펼친 뒤에도 판이 작게 남았다(hh 11-25 '+ 새 확인')
    if (root.classList.contains("side-rail")) { shown = false; return; }
    const pane = [...panes.querySelectorAll(".side-pane")].find((p) => p.offsetParent);
    const sel = pane ? [...pane.querySelectorAll('.sitem[aria-current="true"], .sitem[aria-pressed="true"]')] : [];
    panes.querySelectorAll(".sitem.pilled").forEach((x) => { if (x !== sel[0]) x.classList.remove("pilled"); });
    if (sel.length !== 1) {
      // 목록을 새로 그리는 사이 한 프레임 비는 것은 무시한다 — 바로 숨기면 다음 줄로 미끄러지지 못한다
      clearTimeout(hideT);
      hideT = setTimeout(() => { side.classList.remove("has-pill"); pill.style.opacity = "0"; shown = false; }, 80);
      return;
    }
    clearTimeout(hideT);
    const it = sel[0], a = it.getBoundingClientRect(), b = panes.getBoundingClientRect();
    // 다른 단계의 목록으로 넘어갔거나 처음이면 미끄러지지 않고 그 자리에 놓는다
    const snap = instant || pane !== lastPane || !shown;
    pill.classList.toggle("snap", snap);
    // 화면 비율(body zoom --z, 1760px 이상 1.1 · 2080px 이상 1.2)이 걸리면 getBoundingClientRect 는 확대된 값이고
    // style 의 px 는 확대 전 값이다 — 그대로 넣으면 판이 z 배로 커지고 아래 줄일수록 더 밀렸다(hh 11-25 05:21). z 로 나눈다.
    const z = panes.currentCSSZoom || parseFloat(getComputedStyle(document.body).zoom) || 1;
    pill.style.width = `${a.width / z}px`;
    pill.style.height = `${a.height / z}px`;
    pill.style.transform = `translate(${(a.left - b.left) / z}px, ${(a.top - b.top) / z}px)`;
    pill.style.opacity = a.bottom < b.top || a.top > b.bottom ? "0" : "1";
    it.classList.add("pilled");
    side.classList.add("has-pill");
    lastPane = pane; shown = true;
  };
  // 관찰 콜백은 이미 한 번에 모아 오므로 바로 놓는다(그리기 전이라 깜빡이지 않는다)
  const later = () => place();
  new MutationObserver(later).observe(panes, { subtree: true, childList: true, attributes: true,
    attributeFilter: ["aria-current", "aria-pressed", "hidden"] });
  new MutationObserver(later).observe(document.body, { attributes: true, attributeFilter: ["data-view"] });
  addEventListener("resize", later);
  // 사이드바 폭이 바뀌면(접기·펴기, 창 크기) 판도 줄 크기에 맞춰 바로 다시 놓는다 — 미끄러지지 않고
  if (window.ResizeObserver) new ResizeObserver(() => place(true)).observe(panes);
  // 글꼴이 늦게 오면 줄 높이가 바뀐다(윈도의 Pretendard) — 다 온 뒤 한 번 더 놓는다
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => place(true));

  // 굴리는 동안만 스크롤 막대. 굴리면 판도 줄을 따라간다(이때는 미끄러지지 않는다).
  const timers = new WeakMap();
  panes.addEventListener("scroll", (e) => {
    const p = e.target;
    if (!p.classList || !p.classList.contains("side-pane")) return;
    p.classList.add("is-scrolling");
    clearTimeout(timers.get(p));
    timers.set(p, setTimeout(() => p.classList.remove("is-scrolling"), 700));
    pill.classList.add("snap");
    place();
  }, true);
  later();
})();
// 사이드바 Prova 로고 = 홈(새 확인). 새 탭으로 여는 클릭(⌘·가운데)은 그대로 둔다
$("homeLink").addEventListener("click", (e) => {
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
  e.preventDefault();
  if (!state.busy) showBlank();
});

function showBlank() {
  setView("form", 1);
  setBar("새 확인");
  $("stage").innerHTML = "";
  renderRunsFoot();
}

function showError(title, message) {
  showBlank();
  $("formNote").innerHTML = alertBox("fail", esc(title), esc(message));
}

// ── 진행 (기획서 읽는 중 · 실행 중) ──────────────────────────────────────────

// 실행 중 항목별 상태 — 직전 집계와 비교해 방금 끝난 항목의 판정을 안다(서버를 바꾸지 않는다).
let prog = null;

const ruleOf = (c) => c.rule_label || c.violates || (c.flow_id ? "화면 흐름" : "정상 동작");

function showProgress(title, lines) {
  const run = title === "실행 중";
  setView("busy", run ? 3 : 2);
  const f = form();
  setBar(run ? "실행 중" : title, run ? `${specName()} → ${f.url}` : specName());
  $("sideFoot").textContent = `${BACKEND_NAME[f.backend] || f.backend} · ${f.url}`;
  $("pSteps").innerHTML = planSteps(title);

  // 실행할 항목을 처음부터 깔아 둔다 — 몇 개 중 어디쯤이고 무엇이 남았는지가 처음부터 보인다.
  const cases = run && state.plan ? state.plan.cases.filter((c) => c.selected) : [];
  // last 는 직전 집계 — 처음부터 0 으로 둔다. null 이면 첫 집계 줄에서 첫 항목을 판정하지 못해
  // '진행 중' 으로 남았다(실행 시작 때 0 집계 줄이 오지 않으면).
  prog = { k: 0, n: cases.length, t0: 0, last: [0, 0, 0, 0], row: null, seen: [0, 0, 0, 0] };
  if (run) $("barActions").innerHTML = `<button class="btn" id="pStop" type="button" hidden>중지</button>`;

  $("stage").innerHTML = `
    <div class="scroll" id="pScroll">
      <div class="run-head">
        <h2 class="lt nums" id="pHead">${run ? "" : esc(title)}</h2>
        <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
        <span class="hint nums" id="pElapsed"><span class="el"></span> 지남<span class="eta"></span><span class="per"></span></span>
      </div>
      <div class="pnow" id="pNow" aria-live="polite"></div>
      <div class="pnotes" id="pNotes"></div>
      <progress id="pBar" class="sr" max="${cases.length || 1}" value="0" ${run ? "" : "hidden"}></progress>
      <div class="pbar seg" id="pTrack" ${run ? "" : "hidden"} aria-hidden="true" style="--n:${cases.length || 1}"></div>
      <div class="ptally" id="pTally" hidden></div>
      ${run ? `<table class="tbl run-table">
        <colgroup><col style="width:34px"><col><col style="width:140px"><col style="width:72px"></colgroup>
        <tbody id="pCases">${cases.map((c, i) => runRow(c, i)).join("")}</tbody></table>` : ""}
      <details class="disc" id="pRaw"><summary><span class="chev" aria-hidden="true"></span>진행 로그 전체<span class="n" id="pLogN"></span></summary>
        <div class="logbox"><pre class="log" id="pLog" role="log" aria-live="polite"></pre>
          <button class="btn sm log-jump" id="pLogJump" type="button" hidden></button></div></details>
    </div>`;
  if (run) rollText($("pHead"), `0 / ${cases.length || "—"}`, `${cases.length}건 중 0건 끝남`);
  followLog();
  pushProgress(lines || []);
  startClock();
  watchRunHead();
}

/**
 * 실행 머리의 시계 — 지난 시간(m:ss), 남은 시간 어림, 건당 시간. hh 11-25 '실행 중 화면을 공연 계기판처럼'.
 * 1초에 한 번, 실행 화면이 떠 있고 탭이 보일 때만 돈다(숨으면 멈추고, 돌아오면 실제 시작 시각에서 다시 맞춘다).
 * 틱 안에서는 글자만 바꾼다 — 크기·위치를 읽지 않는다. 바뀐 자리 숫자만 굴린다(rollText).
 * 남은 시간 = 끝난 항목의 평균(첫 항목을 시작한 때부터) × 남은 항목. 한 건도 안 끝났으면 어림하지 않는다.
 */
const runClock = { start: 0, first: 0, timer: 0 };
function startClock() {
  clearTimeout(runClock.timer);
  runClock.start = Date.now();
  runClock.first = 0;
  clockTick();
}
function clockTick() {
  clearTimeout(runClock.timer);
  const el = $("pElapsed");
  if (!el || document.visibilityState !== "visible") return;   // 결과로 넘어갔거나 탭이 숨었다
  const now = Date.now(), ms = now - runClock.start, sec = Math.floor(ms / 1000);
  const mm = Math.floor(sec / 60), ss = sec % 60;
  rollText(el.querySelector(".el"), `${mm}:${String(ss).padStart(2, "0")}`, mm ? `${mm}분 ${ss}초` : `${ss}초`);
  const bar = $("pBar");
  const done = bar ? Number(bar.value) || 0 : 0, n = prog ? prog.n : 0, left = n - done;
  let eta = "", per = "";
  if (n && done >= 1 && runClock.first) {
    const avg = (now - runClock.first) / 1000 / done;
    per = ` · 건당 ${avg.toFixed(1)}초`;
    if (left > 0) {
      const est = avg * left;
      eta = est < 5 ? " · 곧 끝나요" : est < 60 ? ` · 약 ${Math.round(est)}초 남음`
        : ` · 약 ${Math.floor(est / 60)}분 ${Math.round(est % 60)}초 남음`;
    }
  }
  rollText(el.querySelector(".eta"), eta);
  rollText(el.querySelector(".per"), per);
  runClock.timer = setTimeout(clockTick, 1000 - (ms % 1000) + 5);
}
document.addEventListener("visibilitychange", () => {
  const head = document.querySelector(".run-head");
  if (head) head.classList.toggle("hidden-tab", document.visibilityState !== "visible");
  if (document.visibilityState === "visible") clockTick(); else clearTimeout(runClock.timer);
});
// 실행 머리가 화면 밖으로 굴러 나가면 도는 점을 멈춘다
let headIO = null;
function watchRunHead() {
  const head = document.querySelector(".run-head");
  if (!head || !window.IntersectionObserver) return;
  if (headIO) headIO.disconnect();
  headIO = new IntersectionObserver(([e]) => head.classList.toggle("asleep", !e.isIntersecting));
  headIO.observe(head);
}

/**
 * 자리마다 바뀐 글자만 굴린다 — 21st.dev 'Animate Digits'. 새 글자는 아래에서(60% · 흐림 4px · 0.85배) 들어오고,
 * 옛 글자는 같은 칸 안의 겹친 쌍둥이로 위로 빠지며 흐려진다. 칸은 넘친 것을 자른다. 자리는 오른쪽 끝에 맞춰
 * 9 → 10 처럼 길어져도 일의 자리가 제자리에 있다. 화면 읽기에는 조각이 아니라 label 한 줄만.
 */
let rollTiming = null;
function rollText(el, text, label) {
  if (!el) return;
  text = String(text);
  if (el.dataset.v === text) return;
  const first = el.dataset.v === undefined;
  el.dataset.v = text;
  let sr = el.querySelector(":scope > .sr"), box = el.querySelector(":scope > .rl");
  if (!box) {
    el.innerHTML = `<span class="sr"></span><span class="rl" aria-hidden="true"></span>`;
    sr = el.firstChild; box = el.lastChild;
  }
  sr.textContent = label ?? text;
  const go = !first && !reduceMotion() && !!el.animate;
  if (go && !rollTiming) {
    const css = getComputedStyle(document.documentElement);
    rollTiming = { dur: parseFloat(css.getPropertyValue("--dur-3")) || 250,
                   spring: css.getPropertyValue("--ease-spring").trim() || "ease-out",
                   out: css.getPropertyValue("--ease-out").trim() || "ease-out" };
  }
  const chars = [...text], cells = [...box.children];
  while (cells.length < chars.length) { const c = document.createElement("span"); c.className = "dc"; box.prepend(c); cells.unshift(c); }
  while (cells.length > chars.length) cells.shift().remove();
  chars.forEach((ch, i) => {
    const c = cells[i];
    if (c.dataset.c === ch) return;
    c.dataset.c = ch;
    const old = c.querySelector(".d:not(.out)");
    const neu = document.createElement("span");
    neu.className = "d"; neu.textContent = ch;
    c.append(neu);
    if (!go) { if (old) old.remove(); return; }
    neu.animate([{ transform: "translateY(60%) scale(0.85)", filter: "blur(4px)", opacity: 0 },
                 { transform: "none", filter: "none", opacity: 1 }],
                { duration: rollTiming.dur, easing: rollTiming.spring });
    if (old) {
      old.classList.add("out");
      old.animate([{ transform: "none", opacity: 1 }, { transform: "translateY(-60%)", opacity: 0 }],
                  { duration: rollTiming.dur * 0.8, easing: rollTiming.out, fill: "forwards" })
        .finished.then(() => old.remove(), () => old.remove());
    }
  });
}

function runRow(c, i, k) {
  return `<tr class="case wait${i % 2 ? " alt" : ""}" data-k="${k || i + 1}" data-title="${esc(c.title)}">` +
    `<td>${vmark("wait")}</td><td>${esc(c.title)}</td>` +
    `<td class="muted">${c.case_id ? esc(ruleOf(c)) : ""}</td><td class="muted nums t"></td></tr>`;
}

/* ── 진행 로그 — 흘러 들어오는 글 ─────────────────────────────────────────
 * 21st.dev 'Response Stream' 에서 '도착하는 대로 덧붙인다' 와 '멈춤·이어 보기' 만.
 * 맨 아래를 보고 있으면 따라 내려가고, 위로 올려 읽는 중이면 끌어내리지 않는다. 그동안 온 줄 수를
 * '새 줄 n개 — 맨 아래로' 로 알려 준다. 접혀 있어도 머리줄의 줄 수가 늘어 일이 도는 것이 보인다. */
const atLogEnd = (log) => log.scrollHeight - log.scrollTop - log.clientHeight < 24;
// 가려진 줄이 있는 쪽 가장자리만 흐린다 — macOS 의 스크롤 가장자리 효과와 같은 뜻(21st.dev AI Thinking 에서).
// 다 보이면 걸지 않는다. 바탕은 .logbox 가 가져서 흐림이 글에만 걸린다.
function logEdges(log) {
  log.classList.toggle("cut-top", log.scrollTop > 2);
  log.classList.toggle("cut-bottom", log.scrollHeight - log.scrollTop - log.clientHeight > 2);
}

function followLog() {
  const log = $("pLog"), jump = $("pLogJump"), raw = $("pRaw");
  if (!log || !jump) return;
  const toEnd = () => { log.scrollTop = log.scrollHeight; jump.hidden = true; log.dataset.unseen = 0; logEdges(log); };
  jump.addEventListener("click", toEnd);
  log.addEventListener("scroll", () => {
    logEdges(log);
    if (atLogEnd(log)) { jump.hidden = true; log.dataset.unseen = 0; }
  }, { passive: true });
  raw.addEventListener("toggle", () => { if (raw.open) toEnd(); });
}

function appendLog(log, lines) {
  if (!lines.length) return;
  const follow = atLogEnd(log) || !$("pRaw").open;
  const chunk = document.createElement("span");
  chunk.className = "chunk";
  chunk.textContent = lines.join("\n") + "\n";
  log.appendChild(chunk);
  const n = (Number(log.dataset.n) || 0) + lines.length;
  log.dataset.n = n;
  $("pLogN").textContent = ` · ${n}줄`;
  if (follow) { log.scrollTop = log.scrollHeight; logEdges(log); return; }
  logEdges(log);
  const unseen = (Number(log.dataset.unseen) || 0) + lines.length;
  log.dataset.unseen = unseen;
  const jump = $("pLogJump");
  jump.textContent = `새 줄 ${unseen}개 — 맨 아래로`;
  jump.hidden = false;
}

const TALLY_KEYS = ["ok", "fail", "infra", "unv"];

/** 방금 끝난 항목 줄에 판정을 적는다 — 직전 집계에서 어느 수가 늘었는지로 안다. */
/**
 * 진행 막대를 판정별 조각으로 — 끝난 항목마다 한 칸이 그 판정 색으로 왼쪽에서 자란다(scaleX, 목업의 growx).
 * 칸 순서는 끝난 순서. 색만으로 말하지 않는다 — 옆 집계 글자(pTally)가 같은 수를 말한다.
 */
const BAR_KIND = ["pass", "defect", "infra", "unv"];
function growBar(nums) {
  const track = $("pTrack");
  if (!track || !prog) return;
  nums.forEach((v, j) => {
    for (let x = prog.seen[j]; x < v; x++) track.insertAdjacentHTML("beforeend", `<i class="${BAR_KIND[j]}"></i>`);
    prog.seen[j] = Math.max(prog.seen[j], v);
  });
}

function settleRow(t) {
  const row = prog.row;
  if (!row || !prog.last) return;
  const i = t.findIndex((v, j) => v > prog.last[j]);
  const kind = TALLY_KEYS[i] || "unv";
  row.classList.remove("now", "wait");
  row.classList.add("done");
  row.cells[0].innerHTML = vmark(kind);
  const sec = (Date.now() - prog.t0) / 1000;
  row.querySelector(".t").textContent = `${sec.toFixed(sec < 10 ? 1 : 0)}초`;
  prog.row = null;
}

/** 'k번째 항목' 줄을 찾는다 — 제목이 같은 남은 줄, 없으면 k번째 줄, 그것도 없으면 새로 만든다. */
function runRowFor(k, title) {
  const body = $("pCases");
  if (!body) return null;
  const rows = [...body.querySelectorAll("tr.wait")];
  let row = rows.find((r) => r.dataset.title === title) || body.querySelector(`tr.wait[data-k="${k}"]`);
  if (!row) {
    body.insertAdjacentHTML("beforeend", runRow({ title }, body.rows.length, k));
    row = body.lastElementChild;
  }
  return row;
}

/** 지금 도는 줄이 화면 아래로 벗어났으면 따라간다 — 사람이 위로 올려 읽는 중이면 두고 본다. */
function keepInView(row, prevRow) {
  const box = $("pScroll");
  if (!box || !row) return;
  const b = box.getBoundingClientRect();
  const seen = (el) => { const r = el.getBoundingClientRect(); return r.top >= b.top && r.bottom <= b.bottom; };
  if (prevRow && !seen(prevRow)) return;
  if (!seen(row)) row.scrollIntoView({ block: "nearest" });
}

/**
 * 진행 메시지를 단계로 접어서 보여준다.
 *
 * 파이프라인은 "S1 설계 문서 추출" 같은 머리줄과 그 아래 들여쓴 상세를 보낸다.
 * 머리줄은 사이드바의 단계로, 들여쓴 줄은 그 단계의 상세로 읽는다. 원문은 접힌 로그에 그대로 남긴다.
 * 실행 중에는 '케이스 k/N' 줄과 '집계' 줄로 항목 표의 줄마다 상태를 채운다.
 */
function pushProgress(messages) {
  const log = $("pLog"), steps = $("pSteps");
  if (!log || !steps) return;
  appendLog(log, messages);

  for (const raw0 of messages) {
    // 지금까지의 판정 수 (nodes.run_cases 의 '집계' 줄). 항목이 하나 끝날 때마다 온다.
    const t = /집계 통과 (\d+) · 기획서와 다름 (\d+) · 실행 문제 (\d+)(?: · 확인 불가 (\d+))?/.exec(raw0);
    if (t) {
      const nums = [t[1], t[2], t[3], t[4] || "0"].map(Number);
      if (prog) {
        settleRow(nums);
        prog.last = nums;
        if (prog.k) {
          const done = nums.reduce((a, b) => a + b, 0);
          const bar = $("pBar");
          bar.value = done;
          rollText($("pHead"), `${done} / ${bar.max}`, `${bar.max}건 중 ${done}건 끝남`);
          growBar(nums);
          clockTick();
          bar.setAttribute("aria-valuetext", `${bar.max}건 중 ${done}건 끝남`);
          document.title = `${done}/${bar.max} 실행 중 · Prova`;
          const active = steps.querySelector(".pstep.active .t");
          if (active) active.textContent = `${done}/${bar.max}`;
        }
      }
      const el = $("pTally");
      el.hidden = false;
      // 칸은 한 번 만들고 숫자만 바꾼다 — 바뀐 숫자만 밀어 올린다.
      if (!el.firstChild) {
        el.innerHTML = `<span>${vmark("ok", { dot: true, say: false })}통과 <b data-k="ok"></b></span>` +
          `<span>${vmark("fail", { dot: true, say: false })}기획서와 다름 <b data-k="fail"></b></span>` +
          `<span>${vmark("infra", { dot: true, say: false })}실행 문제 <b data-k="infra"></b></span>` +
          `<span hidden>${vmark("unv", { dot: true, say: false })}확인 불가 <b data-k="unv"></b></span>`;
      }
      const k = (key) => el.querySelector(`[data-k="${key}"]`);
      swapNumber(k("ok"), nums[0]);
      swapNumber(k("fail"), nums[1]);
      swapNumber(k("infra"), nums[2]);
      k("unv").parentElement.hidden = !nums[3];
      swapNumber(k("unv"), nums[3]);
      continue;
    }
    const raw = plainProgress(raw0);
    // 케이스 줄은 단계 목록에 쌓지 않고 표의 그 줄을 '확인 중' 으로 바꾼다. 원문은 로그에 남는다.
    const m = /케이스 (\d+)\/(\d+) · (.+)/.exec(raw);
    if (m) {
      const k = Number(m[1]), n = Number(m[2]);
      setNow(`${n}건 중 ${k}번째 — ${m[3]}`);
      const bar = $("pBar");
      bar.hidden = false; bar.max = n; bar.value = k - 1;
      const track = $("pTrack");
      track.hidden = false;
      track.style.setProperty("--n", n);
      rollText($("pHead"), `${k - 1} / ${n}`, `${n}건 중 ${k - 1}건 끝남`);
      if (k === 1 && !runClock.first) runClock.first = Date.now();
      if (prog) {
        const prevRow = prog.row;
        prog.k = k; prog.n = n; prog.t0 = Date.now();
        const row = runRowFor(k, m[3].trim());
        if (row) {
          row.classList.remove("wait");
          row.classList.add("now");
          row.cells[0].innerHTML = vmark("run");
          row.querySelector(".t").textContent = "진행 중";
          prog.row = row;
          keepInView(row, prevRow || row.previousElementSibling);
        }
      }
      continue;
    }
    const isDetail = /^\s{2,}/.test(raw) || raw.trimStart().startsWith("!");
    const text = raw.trim();
    if (!text) continue;
    if (isDetail) {
      const last = currentStep(steps);
      if (last) {
        const d = document.createElement("div");
        d.className = "detail";
        // '!' 로 시작하는 줄은 주의 — 읽어 주는 프로그램에는 '주의' 라고 알린다.
        if (/^!/.test(text)) {
          d.classList.add("warn");
          d.innerHTML = `<span class="sr">주의: </span>`;
          d.append(text.replace(/^!\s*/, ""));
        } else {
          d.textContent = text;
        }
        last.querySelector(".body").appendChild(d);
        // 항목을 돌기 전에는 가장 최근 상세가 지금 하는 일이다.
        if (!prog || !prog.k) setNow(text.replace(/^!\s*/, ""));
        continue;
      }
    }
    const label = text.replace(/^S\d(~S\d)?\s+/, "");
    const key = (PLAN_STEPS.find(([, name]) => label.startsWith(name)) || [])[0];
    // 단계 이름이 아닌 맨 앞 줄(예: '연습용으로 실행합니다 — …')은 단계가 아니라 알림이다.
    // 체크 표시를 달아 단계 목록에 넣으면 '한 일' 처럼 읽힌다 — 내용 위에 알림으로 둔다.
    if (!key && !/^S\d/.test(text)) {
      const [head, ...rest] = text.split(" — ");
      $("pNotes").insertAdjacentHTML("beforeend", alertBox("info", esc(head), esc(rest.join(" — "))));
      continue;
    }
    const prev = currentStep(steps);
    if (prev) doneStep(prev);
    let el = key && steps.querySelector(`.pstep.todo[data-key="${key}"]`);
    if (el) {
      // 건너뛴 앞 단계(이미 만든 계획으로 바로 실행 등)는 지운다 — 남겨 두면 안 한 일이 '할 일'로 보인다.
      while (el.previousElementSibling && el.previousElementSibling.classList.contains("todo")) {
        el.previousElementSibling.remove();
      }
    } else {
      el = document.createElement("div");
      steps.insertBefore(el, steps.querySelector(".pstep.todo"));
    }
    el.className = "pstep active";
    el.dataset.t0 = Date.now();
    // 지금 단계는 모양(도는 호)만이 아니라 글자로도 말한다 — HIG '색·모양만으로 전하지 않는다'.
    el.innerHTML = `<span class="mark">${vmark("run")}</span>` +
      `<div class="body">${esc(label)}</div><span class="t">진행 중</span>`;
    if (!prog || !prog.k) setNow(label);
  }
}

/**
 * '지금 하는 일' 줄 — 21st.dev streaming-text 의 움직임만 옮겼다: 낱말이 흐림에서 하나씩 또렷해지고,
 * 다 나올 때까지 끝에 커서가 깜빡인다. 타이머 없이 CSS 지연(--i)으로만 돈다. 줄이 길면 한 낱말 간격을
 * 줄여 0.8초 안에 다 나온다. 읽어 주는 프로그램에는 낱말 조각이 아니라 문장 하나로 알린다.
 */
function setNow(text) {
  const el = $("pNow");
  if (!el || el.dataset.text === text) return;
  el.dataset.text = text;
  const words = text.split(/\s+/).filter(Boolean);
  const step = Math.min(80, Math.round(800 / Math.max(words.length, 1)));
  el.style.setProperty("--step", `${step}ms`);
  el.style.setProperty("--n", words.length);
  el.innerHTML = `<span class="sr">${esc(text)}</span><span aria-hidden="true">` +
    words.map((w, i) => `<span class="w" style="--i:${i}">${esc(w)}</span>`).join(" ") +
    `<span class="caret"></span></span>`;
}

/**
 * 앞으로 할 단계를 처음부터 깐다 — 21st.dev 'AI Planning' 에서 '계획 전체를 먼저 보이고
 * 하나씩 채운다' 만 가져왔다. 남은 단계는 빈 원과 흐린 글자, 시작되면 도는 호, 끝나면 파란 체크와 걸린 시간.
 * 이름은 PROGRESS_WORDS 가 바꾼 말과 같아야 켜진다.
 */
const PLAN_STEPS = [
  ["read", "기획서 읽기"],
  ["cases", "확인할 항목 만들기"],
  ["browse", "브라우저로 하나씩 확인"],
  ["report", "리포트 만들기"],
];
function planSteps(title) {
  const keys = title === "실행 중" ? ["read", "cases", "browse", "report"] : ["read", "cases"];
  return PLAN_STEPS.filter(([k]) => keys.includes(k)).map(([k, name]) =>
    `<div class="pstep todo" data-key="${k}"><span class="mark">${vmark("wait", { say: false })}</span>` +
    `<div class="body"><span class="sr">할 차례: </span>${esc(name)}</div><span class="t"></span></div>`).join("");
}
// 지금 단계 = 남은 단계(todo)를 뺀 마지막 줄.
function currentStep(steps) {
  const all = steps.querySelectorAll(".pstep:not(.todo)");
  return all[all.length - 1] || null;
}

/**
 * 파이프라인의 진행 문구를 기획자의 말로 바꾼다. 원문은 CLI 와 접힌 로그가 그대로 쓴다 —
 * 개발자가 그 말로 코드를 찾는다.
 */
const PROGRESS_WORDS = [
  [/mock 백엔드로 실행합니다 — 설계 문서 추출에 실제 모델을 쓰지 않습니다\./, "연습용으로 실행해요 — 기획서를 실제 모델로 읽지 않아요."],
  [/^(\s*)S1 사람이 고친 추출 결과를 씁니다.*$/, "$1기획서 읽기 — 고친 내용을 써요"],
  [/^(\s*)S1 설계 문서 추출/, "$1기획서 읽기"],
  [/^(\s*)S2 테스트 케이스 생성/, "$1확인할 항목 만들기"],
  [/^(\s*)S3~S5 브라우저 실행 및 판정/, "$1브라우저로 하나씩 확인"],
  [/^(\s*)S6 리포트 생성/, "$1리포트 만들기"],
  [/화면 '(.+?)' · 요소 (\d+)개/, "'$1' 화면 · 입력칸·버튼 $2개"],
  [/케이스 (\d+)개 \(정상 (\d+) · 위반 (\d+)/, "항목 $1개 (정상 동작 $2 · 막혀야 하는 입력 $3"],
  [/승인 목록 → (\d+)개 실행/, "승인한 $1개를 실행해요"],
];
function plainProgress(line) {
  for (const [re, to] of PROGRESS_WORDS) line = line.replace(re, to);
  return line;
}

// 끝난 단계는 파란 체크와 걸린 시간 — 1초 넘게 걸린 단계만. 초록(통과)으로 칠하지 않는다.
function doneStep(el) {
  if (!el.classList.contains("active")) return;
  el.classList.remove("active");
  el.classList.add("done");
  el.querySelector(".mark").innerHTML = vmark("done");
  const sec = Math.round((Date.now() - Number(el.dataset.t0 || Date.now())) / 1000);
  const t = el.querySelector(".t");
  if (t) t.textContent = sec >= 1 ? `${sec}초` : "";
}

function finishProgress() {
  const last = $("pSteps") && currentStep($("pSteps"));
  if (last) doneStep(last);
}

// ── 2 항목 검토 ────────────────────────────────────────────────────────────

function screenName(id) {
  return (state.plan.screens && state.plan.screens[id]) || id || "기타";
}

const groupOf = (c) => (c.flow_id ? `flow:${c.flow_id}` : c.screen_id);
const groupName = (key) => key.startsWith("flow:") ? `흐름 ${key.slice(5)}` : screenName(key);

function visibleCases() {
  const q = state.filter.trim().toLowerCase();
  return state.plan.cases.filter((c) => {
    if (state.onlyOff && c.selected) return false;
    if (state.rule && ruleOf(c) !== state.rule) return false;
    if (state.group && groupOf(c) !== state.group) return false;
    if (!q) return true;
    return (c.case_id + " " + c.title + " " + (c.violates || "") + " " + (c.target_label || "") + " " +
            ruleOf(c) + " " + screenName(c.screen_id)).toLowerCase().includes(q);
  });
}

/**
 * 화면별 확인 범위를 지금 체크 상태로 다시 센다.
 *
 * 서버가 준 coverage 는 모델이 고른 시점의 수치라, 사람이 체크를 바꾸면 낡는다.
 * named(요청이 그 화면을 이름으로 지목했는가)만 서버 판단을 쓰고 수는 여기서 센다.
 */
function liveCoverage() {
  const namedBy = {};
  for (const c of state.plan.coverage || []) namedBy[c.key] = c.named;
  const slots = new Map();
  for (const c of state.plan.cases) {
    const key = c.flow_id || c.screen_id;
    if (!slots.has(key)) {
      slots.set(key, { key, name: c.flow_id ? `흐름 ${key}` : screenName(key),
                       named: !!namedBy[key], selected: 0, total: 0 });
    }
    const s = slots.get(key);
    s.total += 1;
    if (c.selected) s.selected += 1;
  }
  return [...slots.values()];
}

function planNotes() {
  const p = state.plan;
  const out = [];

  // 대상 URL 을 도구가 고쳤다면 먼저 보인다 — 판정의 전제가 바뀐 것이다.
  if (p.url_note) out.push(alertBox("info", "대상 주소를 고쳤어요", esc(p.url_note)));

  // 기획↔디자인 불일치 — 케이스를 승인하기 전에 봐야 한다. 구현을 검증하기
  // 전에 입력끼리 모순이면 그것부터 정리하는 것이 순서다 (s1_merge).
  if ((p.design_mismatches || []).length) {
    out.push(alertBox("warn",
      `기획↔디자인 불일치 ${p.design_mismatches.length}건`,
      "구현을 고치기 전에 두 입력 중 어느 쪽이 맞는지부터 정해야 해요. " +
      "어긋난 항목은 판정에서 빠져요." +
      p.design_mismatches.map((m) => `<div style="margin-top:6px">${esc(m)}</div>`).join("")));
  }

  if (p.fallback) {
    out.push(alertBox("warn", "요청을 해석하지 못해 전체 항목을 골랐어요",
      "해석 실패는 적게 검사하는 쪽이 아니라 많이 검사하는 쪽으로 넘어가요 — " +
      "적게 고르면 결함이 숨지만 많이 고르면 숨지 않아요." +
      (p.warnings || []).map((w) => `<div style="margin-top:6px">${esc(w)}</div>`).join("")));
  } else {
    if (p.request && p.reason) {
      out.push(alertBox("info", "이렇게 이해했습니다", esc(p.reason)));
    }
    for (const w of p.warnings || []) out.push(alertBox("warn", esc(w), ""));
    if ((p.widened || []).length) {
      // 모델이 고른 것과 코드가 더한 것을 구분해 보인다 (selector.widen_selection).
      out.push(alertBox("info", `도구가 넓힌 케이스 ${p.widened.length}건`,
        "모델이 가리킨 묶음(건수·정렬·흐름 등)을 코드가 채웠어요: " + esc(p.widened.join(", "))));
    }
  }

  if ((p.spec_edits || []).length) {
    out.push(alertBox("info", `사람이 고친 값 ${p.spec_edits.length}건으로 만든 항목이에요`,
      "고친 칸은 위의 '기획서에서 읽은 내용' 에서 볼 수 있고, 리포트에도 '사람이 고친 것' 으로 남아요."));
  }

  // 요청이 화면을 이름으로 지목했는데 일부만 골라진 경우. "몇 건 제외" 만
  // 보면 그 화면을 확인했다고 읽힌다 — 실측에서 "회원가입이 잘 되는지" 에
  // 17건 중 6건만 골라지는 것이 프롬프트로는 안 고쳐졌고, 이 경고가 그 남은
  // 구멍의 방어선이다. 사람이 체크를 바꾸면 함께 갱신된다.
  for (const c of liveCoverage()) {
    if (c.named && c.selected > 0 && c.selected < c.total) {
      out.push(alertBox("warn",
        `'${esc(c.name)}' 화면은 ${c.total}건 중 ${c.selected}건만 실행돼요`,
        `요청이 이 화면을 가리켰지만 일부만 골라졌어요. 이대로 실행하면 ` +
        `이 화면의 통과율은 <b>화면 전체의 상태를 뜻하지 않아요.</b> ` +
        `표의 화면 줄 체크 상자로 전부 켤 수 있어요.`));
    }
  }

  const off = p.cases.filter((c) => !c.selected).length;
  if (off) {
    out.push(alertBox("info", `이번 실행에서 ${off}건을 제외해요`,
      "<b>통과한 것이 아니라 확인하지 않는 것</b>이에요. 빠지면 안 되는 것이 있으면 " +
      "표에서 도로 켜 주세요."));
  }

  if ((p.coverage_gaps || []).length) {
    out.push(alertBox("warn",
      `기획서에 있으나 케이스가 없는 항목 ${p.coverage_gaps.length}건`,
      p.coverage_gaps.map((g) => esc(g)).join("<br>")));
  }
  return out.join("");
}

function showPlan() {
  setView("plan", 2);
  const p = state.plan;
  setBar("항목 검토", `${specName()} · ${p.total_generated}개 뽑음`);
  // 검색은 도구 막대 오른쪽 — macOS 앱의 자리(키트 Search Field)
  $("barActions").innerHTML = `<label class="search">${ICON.search}<span class="sr">항목 검색</span>` +
    `<input type="search" id="q" placeholder="검색" spellcheck="false" value="${esc(state.filter)}"></label>`;

  $("stage").innerHTML = `
    <div class="planview${state.mode === "spec" ? " spec-mode" : ""}" id="planView">
      <div class="plan-main">
        <div class="scroll" id="planScroll">
          <div class="plan-head">
            <div class="seg" id="planSeg" role="group" aria-label="보기">
              <button type="button" data-mode="items" aria-pressed="${state.mode === "items"}">항목 ${p.cases.length}</button>
              <button type="button" data-mode="spec" aria-pressed="${state.mode === "spec"}">기획서에서 읽은 내용</button>
            </div>
            <span class="sub">${p.request ? `요청 — ${esc(p.request)}` : "요청이 없어 전체 항목을 골랐어요"}</span>
          </div>
          <div class="notes" id="planNotes"></div>
          <div id="itemsPane" ${state.mode === "spec" ? "hidden" : ""}>
            <table class="tbl" id="caseTable">
              <colgroup><col style="width:34px"><col><col style="width:120px"><col style="width:136px"></colgroup>
              <thead><tr><th><input type="checkbox" id="allVis" aria-label="보이는 항목 모두 실행"></th>
                <th>항목</th><th>칸</th><th>규칙</th></tr></thead>
              <tbody id="caseBody"></tbody>
            </table>
          </div>
          <section class="spec" id="specPanel" ${state.mode === "spec" ? "" : "hidden"}></section>
        </div>
        <div class="footbar">
          <span class="nums" id="count"></span>
          <button class="btn quiet sm" id="allBtn" type="button" hidden>모두 켜기</button>
          <span class="hint" id="runHint"></span>
          <span class="sp"></span>
          <button class="btn" id="backBtn" type="button">요청 고치기</button>
          <button class="btn primary" id="runBtn" type="button">이대로 실행</button>
        </div>
      </div>
      <aside class="insp" id="insp" aria-label="고른 항목"></aside>
    </div>`;

  $("q").addEventListener("input", (e) => { state.filter = e.target.value; renderTable(); });
  $("allBtn").addEventListener("click", () => {
    p.cases.forEach((c) => { c.selected = true; });
    syncChecks();
  });
  $("backBtn").addEventListener("click", () => {
    state.plan = null;
    showBlank();
    renderChrome();
    $("request").focus();
  });
  $("runBtn").addEventListener("click", startRun);
  $("planSeg").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-mode]");
    if (b) setPlanMode(b.dataset.mode);
  });
  wireTable();
  $("insp").addEventListener("click", onCite);

  state.draft = JSON.parse(JSON.stringify(p.doc || { screens: [] }));
  state.dirty = false;
  renderSpec();
  renderPlanBody();
}

function setPlanMode(mode) {
  state.mode = mode;
  $("planSeg").querySelectorAll("button").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.mode === mode)));
  $("itemsPane").hidden = mode !== "items";
  $("specPanel").hidden = mode !== "spec";
  $("planView").classList.toggle("spec-mode", mode === "spec");
}

function renderPlanBody() {
  $("planNotes").innerHTML = planNotes();
  renderSidePlan();
  renderTable();
  renderCount();
}

/**
 * 사이드바 — 규칙 종류로 거른다(메일 앱의 편지함처럼). 화면이 여럿이면 화면으로도.
 * 수는 그 묶음의 항목 수다. '꺼 둔 항목만' 은 이번에 실행하지 않을 것만 본다.
 */
function renderSidePlan() {
  const p = state.plan;
  const count = (fn) => p.cases.filter(fn).length;
  const rules = [...new Set(p.cases.map(ruleOf))];
  const groups = [...new Set(p.cases.map(groupOf))];
  const off = count((c) => !c.selected);
  const item = (f, label, n, on) =>
    `<li><button class="sitem" type="button" data-f="${esc(f)}" aria-pressed="${on}">${label}<span class="ct">${n}</span></button></li>`;
  const single = groups.length === 1;
  const nScreens = groups.filter((g) => !g.startsWith("flow:")).length;
  const nFlows = groups.length - nScreens;
  $("sidePlan").innerHTML =
    `<h4>${single ? esc(groupName(groups[0])) : "규칙 종류"}</h4><ul class="slist">` +
    item("rule:", "전체", p.cases.length, !state.rule) +
    rules.map((r) => item(`rule:${r}`, esc(r), count((c) => ruleOf(c) === r), state.rule === r)).join("") +
    `</ul>` +
    (single ? "" : `<h4>화면</h4><ul class="slist">` + item("group:", "모든 화면", p.cases.length, !state.group) +
      groups.map((g) => item(`group:${g}`, esc(groupName(g)), count((c) => groupOf(c) === g), state.group === g)).join("") +
      `</ul>`) +
    `<h4>보기</h4><ul class="slist">` + item("off", "꺼 둔 항목만", off, state.onlyOff) + `</ul>` +
    `<h4>기획서</h4><p class="empty">${esc(specName())}<br>화면 ${nScreens}개${nFlows ? ` · 흐름 ${nFlows}개` : ""}</p>`;
  $("sideFoot").textContent = `${BACKEND_NAME[form().backend] || ""} · ${form().url}`;
}

$("sidePlan").addEventListener("click", (e) => {
  const b = e.target.closest("[data-f]");
  if (!b || !state.plan) return;
  const f = b.dataset.f;
  if (f === "off") state.onlyOff = !state.onlyOff;
  else if (f.startsWith("rule:")) state.rule = f.slice(5);
  else if (f.startsWith("group:")) state.group = f.slice(6);
  if (state.mode !== "items") setPlanMode("items");
  renderSidePlan();
  renderTable();
  const again = [...$("sidePlan").querySelectorAll("[data-f]")].find((x) => x.dataset.f === f);
  if (again) again.focus();
});

/**
 * 항목 표 — 화면(또는 흐름)마다 머리 줄, 그 아래 항목 줄. 줄을 누르면 오른쪽에 원문과 절차가 뜬다.
 * 체크 상자는 '이번 실행에 넣기' 만 바꾼다 — 읽으려고 누른 것이 항목을 끄면 안 된다.
 */
function renderTable() {
  const shown = visibleCases();
  const body = $("caseBody");
  if (!shown.length) {
    body.innerHTML = `<tr class="empty-row"><td colspan="4">조건에 맞는 항목이 없어요.</td></tr>`;
    renderInsp(null);
    syncChecks();
    return;
  }
  if (!shown.some((c) => c.case_id === state.sel)) state.sel = shown[0].case_id;

  const order = [];
  const by = new Map();
  for (const c of shown) {
    const k = groupOf(c);
    if (!by.has(k)) { by.set(k, []); order.push(k); }
    by.get(k).push(c);
  }
  body.innerHTML = order.map((k) => {
    const list = by.get(k);
    const title = k.startsWith("flow:") ? `흐름 <code>${esc(k.slice(5))}</code>` : esc(screenName(k));
    return `<tr class="grp" data-group="${esc(k)}"><td><input type="checkbox" data-group="${esc(k)}"
        aria-label="${esc(groupName(k))} 항목 모두 실행"></td><td colspan="3">${title}<span class="n"></span></td></tr>` +
      list.map((c, i) => `<tr class="case${i % 2 ? " alt" : ""}${c.selected ? "" : " off"}" data-id="${esc(c.case_id)}"
          aria-selected="${c.case_id === state.sel}">
        <td><input type="checkbox" ${c.selected ? "checked" : ""} aria-label="${esc(c.title)} 실행"></td>
        <td><button class="pick" type="button" tabindex="${c.case_id === state.sel ? 0 : -1}">${esc(c.title)}</button></td>
        <td class="muted">${esc(c.target_label || "화면 전체")}</td>
        <td><span class="tag" title="${esc(c.violates || "")}">${esc(ruleOf(c))}</span></td></tr>`).join("");
  }).join("");
  syncChecks();
  renderInsp(state.plan.cases.find((c) => c.case_id === state.sel));
}

// 체크 상태를 표·머리 줄·사이드바·안내·개수에 맞춘다. 줄을 다시 그리지 않아 초점이 그대로다.
function syncChecks() {
  const p = state.plan;
  const byId = new Map(p.cases.map((c) => [c.case_id, c]));
  $("caseBody").querySelectorAll("tr.case").forEach((row) => {
    const c = byId.get(row.dataset.id);
    row.classList.toggle("off", !c.selected);
    row.querySelector("input").checked = c.selected;
  });
  const setBox = (box, list) => {
    const on = list.filter((c) => c.selected).length;
    box.checked = on === list.length && on > 0;
    box.indeterminate = on > 0 && on < list.length;
    return on;
  };
  $("caseBody").querySelectorAll("tr.grp").forEach((row) => {
    const list = p.cases.filter((c) => groupOf(c) === row.dataset.group);
    const on = setBox(row.querySelector("input"), list);
    row.querySelector(".n").textContent = `${on}/${list.length}`;
  });
  setBox($("allVis"), visibleCases());
  $("planNotes").innerHTML = planNotes();
  renderSidePlan();
  renderCount();
}

function selectCase(id, focus) {
  state.sel = id;
  $("caseBody").querySelectorAll("tr.case").forEach((r) => {
    const on = r.dataset.id === id;
    r.setAttribute("aria-selected", String(on));
    r.querySelector(".pick").tabIndex = on ? 0 : -1;
    if (on && focus) { r.querySelector(".pick").focus(); r.scrollIntoView({ block: "nearest" }); }
  });
  renderInsp(state.plan.cases.find((c) => c.case_id === id));
}

function wireTable() {
  const body = $("caseBody");
  body.addEventListener("change", (e) => {
    const box = e.target;
    if (box.dataset.group !== undefined) {
      const list = state.plan.cases.filter((c) => groupOf(c) === box.dataset.group);
      const turnOn = list.some((c) => !c.selected);
      list.forEach((c) => { c.selected = turnOn; });
    } else {
      const row = box.closest("tr.case");
      if (!row) return;
      state.plan.cases.find((x) => x.case_id === row.dataset.id).selected = box.checked;
    }
    // 안내와 개수가 사람의 조작을 따라와야 한다. 가장 중요한 안내가
    // 따라오지 않으면 확인 단계가 형식만 남는다.
    syncChecks();
  });
  body.addEventListener("click", (e) => {
    const row = e.target.closest("tr.case");
    if (!row || e.target.closest("input")) return;
    selectCase(row.dataset.id, false);
  });
  // ↑↓ 로 줄을 옮기고, 스페이스로 실행에 넣고 뺀다 (표의 기본 동작)
  body.addEventListener("keydown", (e) => {
    const row = e.target.closest("tr.case");
    if (!row || !e.target.classList.contains("pick")) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const rows = [...body.querySelectorAll("tr.case")];
      const next = rows[rows.indexOf(row) + (e.key === "ArrowDown" ? 1 : -1)];
      if (next) selectCase(next.dataset.id, true);
    } else if (e.key === " ") {
      e.preventDefault();
      const c = state.plan.cases.find((x) => x.case_id === row.dataset.id);
      c.selected = !c.selected;
      syncChecks();
    }
  });
  $("allVis").addEventListener("change", (e) => {
    const list = visibleCases();
    const turnOn = list.some((c) => !c.selected);
    list.forEach((c) => { c.selected = turnOn; });
    syncChecks();
  });
}

/**
 * 오른쪽 칸 — 고른 항목의 기대, 기획서 원문, 실행 단계. 제목만 보고 승인하지 않게 한다 (prova/wording.py).
 */
function renderInsp(c) {
  const box = $("insp");
  if (!box) return;
  if (!c) { box.innerHTML = `<p class="empty">표에서 항목을 고르면 기획서 원문과 실행 단계가 여기에 보여요.</p>`; return; }
  const src = (c.sources || []).map(readSource);
  const id = `src-${c.case_id}`;
  const flow = c.flow_id && ((state.plan.doc && state.plan.doc.flows) || []).find((f) => f.flow_id === c.flow_id);
  const steps = (c.steps || []);
  box.innerHTML = `
    <div><h5>고른 항목</h5><p class="big">${esc(c.title)}</p>
      <p class="hint meta">${esc([groupName(groupOf(c)), c.target_label, ruleOf(c)].filter(Boolean).join(" · "))}</p></div>
    ${flow && flow.screen_ids.length > 1 ? `<div><h5>화면 흐름</h5>${flowMap(flow)}</div>` : ""}
    ${c.expected ? `<div><h5>기대</h5><p class="expect">${citedExpect(c.expected, src, id)}</p></div>` : ""}
    ${src.length ? `<div id="${esc(id)}"><h5>기획서 근거 ${src.length}곳</h5>${src.map((s, i) =>
      `<div class="quote" data-i="${i}"><cite>${s.page ? `${s.page}쪽 ${s.kind}` : "기획서"}</cite>${markQuote(s.quote, c.expected)}</div>`).join("")}</div>` : ""}
    ${steps.length ? `<div><h5>실행 단계 ${steps.length}</h5><ol class="tl enter">${steps.map(stepLine).join("")}</ol></div>` : ""}
    <div><h5>케이스 번호</h5><p class="idline">${esc(c.case_id)}</p></div>`;
}

// '1. '이메일' 칸에 'a@b' 입력' → 넣는 값·주소·고르는 값만 코드 글꼴로.
// 세로 줄(21st.dev AgentPlanning 참고) — 번호 동그라미를 선으로 잇는다. 준비 단계는 속 빈 동그라미와 '준비'.
// 계획의 단계는 사람 말 한 줄뿐이라(서버가 선택자·값을 따로 보내지 않는다) 펼칠 것을 지어내지 않는다.
function stepLine(s, i = 0) {
  const prep = /^준비 /.test(s);
  const no = (/^(?:준비 )?(\d+)\. /.exec(s) || [])[1] || "";
  let t = esc(s.replace(/^(준비 )?\d+\. /, ""));
  t = t.replace(/칸에 &#39;(.+?)&#39; 입력/, "칸에 <code>$1</code> 입력")
       .replace(/^&#39;(.+?)&#39; 주소로 이동/, "<code>$1</code> 주소로 이동")
       .replace(/에서 &#39;(.+?)&#39; 선택/, "에서 <code>$1</code> 선택");
  return `<li class="${prep ? "prep" : ""}" style="--i:${i}"><span class="node" aria-hidden="true">${prep ? "" : esc(no)}</span>` +
    `<span class="tx">${prep ? `<span class="pre">준비</span> ` : ""}${t}</span></li>`;
}

// 기획서 원문에서 기대 문장이 따옴표로 옮긴 값만 진하게. 표 행의 칸 구분(|)은 가운뎃점으로.
function markQuote(quote, expected) {
  quote = String(quote || "");
  const vals = [...String(expected || "").matchAll(/'([^']{2,})'/g)].map((m) => m[1])
    .filter((v) => quote.includes(v));
  let html = "", i = 0;
  while (i < quote.length) {
    const hit = vals.map((v) => [quote.indexOf(v, i), v]).filter(([at]) => at >= 0)
      .sort((a, b) => a[0] - b[0] || b[1].length - a[1].length)[0];
    if (!hit) { html += esc(quote.slice(i)); break; }
    html += esc(quote.slice(i, hit[0])) + `<mark>${esc(hit[1])}</mark>`;
    i = hit[0] + hit[1].length;
  }
  return html.replace(/ \| /g, " · ");
}

/* ── 기획서 근거를 그 말이 나온 자리에 ─────────────────────────────────────
 * 21st.dev Streaming Text 에서 '문장 안의 출처 칩' 만 가져왔다.
 * 기대 문장의 따옴표 값('가입이 완료되었습니다')이 기획서 원문에 있으면 그 값이 든 마디 끝에
 * '2쪽' 칩을 붙인다. 못 찾은 근거는 문장 끝에 붙는다. 칩을 누르면 아래 원문 상자 중 그 칩의 것에 테두리가 선다. */
function readSource(text) {
  const m = /^(\d+)쪽 (표|본문): ([\s\S]*)$/.exec(text);
  return m ? { page: +m[1], kind: m[2], quote: m[3] } : { page: 0, kind: "", quote: text };
}

function citedExpect(expected, src, id) {
  if (!src.length) return esc(expected);
  const quoted = [...expected.matchAll(/'([^']{2,})'/g)];
  const at = new Map();   // 칩을 끼울 자리 → 근거 번호들
  src.forEach((s, i) => {
    const hit = quoted.filter((m) => s.quote.includes(m[1]))
      .sort((a, b) => b[1].length - a[1].length)[0];
    let pos = expected.length;
    if (hit) {
      const from = hit.index + hit[0].length;
      const stop = expected.slice(from).search(/ 또는 | 그리고 |, |\)/);
      if (stop >= 0) pos = from + stop;
    }
    at.set(pos, [...(at.get(pos) || []), i]);
  });
  let html = "", last = 0;
  for (const pos of [...at.keys()].sort((a, b) => a - b)) {
    const idx = at.get(pos);
    const pages = [...new Set(idx.map((i) => src[i].page).filter(Boolean))];
    const label = pages.length ? `${pages.join("·")}쪽` : "기획서";
    html += esc(expected.slice(last, pos)) +
      `<button type="button" class="cite" data-src="${idx.join(" ")}" aria-controls="${esc(id)}"
         aria-pressed="false" title="기획서 원문 짚기">${label}<span class="sr"> 기획서 원문 짚기</span></button>`;
    last = pos;
  }
  return html + esc(expected.slice(last));
}

// 칩은 제 원문 상자에 테두리를 세운다. 같은 칩을 다시 누르면 내린다.
function onCite(e) {
  const btn = e.target.closest(".cite");
  if (!btn) return;
  const box = btn.closest(".insp, .detail");
  const on = !btn.classList.contains("on");
  box.querySelectorAll(".cite").forEach((c) => { c.classList.remove("on"); c.setAttribute("aria-pressed", "false"); });
  const pick = new Set(on ? btn.dataset.src.split(" ") : []);
  box.querySelectorAll(".quote").forEach((q) => q.classList.toggle("on", pick.has(q.dataset.i)));
  btn.classList.toggle("on", on);
  btn.setAttribute("aria-pressed", String(on));
  const first = box.querySelector(".quote.on");
  if (first) first.scrollIntoView({ block: "nearest" });
}

function picked() {
  return state.plan.cases.filter((c) => c.selected).map((c) => c.case_id);
}

function renderCount() {
  const n = picked().length, all = state.plan.cases.length;
  $("count").innerHTML = `${all}개 중 <b>${n}</b>개 실행${all - n ? ` <span class="hint">· ${all - n}건 제외</span>` : ""}`;
  $("allBtn").hidden = n === all;
  // 0건 실행은 "전체 0건, 통과율 100%" 리포트가 된다. 누를 수 없게 막는다.
  const run = $("runBtn");
  run.disabled = n === 0 || state.dirty;
  run.textContent = n ? `${n}개 실행` : "이대로 실행";
  $("runHint").textContent = n === 0
    ? "0건은 실행할 수 없어요 — 통과율 100% 리포트가 돼요"
    : state.dirty ? "기획서 내용을 고쳤어요 — 먼저 [고친 내용으로 항목 다시 만들기]" : "";
}

// ── 기획서에서 읽은 내용 — 사람이 보고 고친다 (prova/spec_edits.py) ─────────
//
// 실물 기획서에서 S1 은 82% 를 맞게 읽었다. 남은 틀린 칸은 실행 전에 사람이 고치는 것이
// 모델을 더 짜내는 것보다 싸고 확실하다. 고친 값은 리포트에 '사람이 고친 것' 으로 남는다.

const EL_FIELDS = [
  ["label", "항목 이름"], ["required", "필수"], ["placeholder", "안내 문구"],
  ["error_message", "오류 문구"], ["required_message", "비웠을 때 문구"], ["options", "선택 항목"],
];
const SCREEN_FIELDS = [
  ["url_path", "경로"], ["success_condition", "성공 조건"], ["required_message", "비웠을 때 공통 문구"],
];
// 빈 칸으로 두면 '없음'(null) 이 되는 칸. 라벨·경로·성공 조건은 빈 글자 그대로 둔다.
const NULLABLE = new Set(["placeholder", "error_message", "required_message"]);
const CHOICE_TYPES = new Set(["select", "radio", "checkbox"]);
// 요소 종류를 기획자의 말로. 식별자(element_id)는 마우스를 올리면 보인다.
const TYPE_NAME = { input: "입력칸", textarea: "긴 입력칸", select: "선택 목록", checkbox: "체크박스",
                    radio: "라디오", button: "버튼", link: "링크", text: "글자", table: "표" };

function specInput(path, key, value) {
  const id = `${path}.${key}`;
  if (key === "required") {
    return `<input type="checkbox" data-spec="${esc(id)}" ${value ? "checked" : ""}
                   aria-label="필수">`;
  }
  if (key === "options") {
    return `<textarea data-spec="${esc(id)}" rows="${Math.max(1, (value || []).length)}"
                      placeholder="한 줄에 하나" spellcheck="false">${esc((value || []).join("\n"))}</textarea>`;
  }
  return `<input type="text" data-spec="${esc(id)}" value="${esc(value ?? "")}" spellcheck="false">`;
}

function renderSpec() {
  const p = state.plan;
  const d = state.draft;
  const edits = p.spec_edits || [];
  const head = `<div class="spec-head"><b>기획서에서 읽은 내용</b>
    <span class="hint">${edits.length
      ? `사람이 고친 값 ${edits.length}건으로 만든 항목이에요`
      : "잘못 읽은 칸이 있으면 기획서 문구 그대로 고친 뒤, 아래 '고친 내용으로 항목 다시 만들기' 를 누르세요"}</span></div>`;
  const screens = d.screens.map((sc, si) => {
    const meta = SCREEN_FIELDS.map(([k, name]) =>
      `<label class="spec-meta"><span>${name}</span>${specInput(`s${si}`, k, sc[k])}</label>`).join("");
    const rows = sc.elements.map((e, ei) => {
      // 선택 항목은 고를 수 있는 요소에만 있다 — 입력칸·버튼에 빈 상자를 두면 표가 어수선하다.
      const cells = EL_FIELDS.map(([k]) => k === "options" && !CHOICE_TYPES.has(e.type)
        ? `<td class="id">—</td>`
        : `<td>${specInput(`s${si}.e${ei}`, k, e[k])}</td>`).join("");
      return `<tr class="${e._removed ? "off" : ""}"><td class="id" title="${esc(e.element_id)}">${esc(TYPE_NAME[e.type] || e.type)}</td>${cells}
        <td><label class="check"><input type="checkbox" data-remove="s${si}.e${ei}"
            ${e._removed ? "checked" : ""}> 검사 안 함</label></td></tr>`;
    }).join("");
    return `<section class="spec-screen">
      <h3>${esc(sc.screen_name)}</h3>
      <div class="spec-metas">${meta}</div>
      <div class="spec-scroll"><table class="spec-table">
        <thead><tr><th>종류</th>${EL_FIELDS.map(([, n]) => `<th>${n}</th>`).join("")}<th></th></tr></thead>
        <tbody>${rows}</tbody></table></div>
    </section>`;
  }).join("");
  const list = edits.length
    ? `<ul class="spec-edits">${edits.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>` : "";
  $("specPanel").innerHTML = head + list + screens + `
    <div class="runbar"><button class="btn" id="replanBtn" type="button" disabled>
      고친 내용으로 항목 다시 만들기</button>
      <span class="hint" id="specHint">칸을 고치면 누를 수 있어요</span></div>`;

  $("specPanel").querySelectorAll("[data-spec]").forEach((el) => {
    el.addEventListener(el.type === "checkbox" ? "change" : "input", () => {
      const [path, key] = splitPath(el.dataset.spec);
      const target = specTarget(path);
      if (el.type === "checkbox") target[key] = el.checked;
      else if (key === "options") target[key] = el.value.split("\n").map((x) => x.trim()).filter(Boolean);
      else target[key] = el.value === "" && NULLABLE.has(key) ? null : el.value;
      markDirty();
    });
  });
  $("specPanel").querySelectorAll("[data-remove]").forEach((el) => {
    el.addEventListener("change", () => {
      specTarget(el.dataset.remove)._removed = el.checked;
      el.closest("tr").classList.toggle("off", el.checked);
      markDirty();
    });
  });
  $("replanBtn").addEventListener("click", replan);
}

function splitPath(id) {
  const i = id.lastIndexOf(".");
  return [id.slice(0, i), id.slice(i + 1)];
}

function specTarget(path) {
  const [s, e] = path.split(".");
  const screen = state.draft.screens[Number(s.slice(1))];
  return e ? screen.elements[Number(e.slice(1))] : screen;
}

// 고친 뒤 다시 만들지 않고 실행하면 화면의 항목과 문서가 어긋난다 — 실행을 막는다.
function markDirty() {
  state.dirty = true;
  $("replanBtn").disabled = false;
  $("specHint").textContent = "고친 내용은 이 버튼을 눌러야 항목에 반영돼요";
  renderCount();
}

function draftDoc() {
  const d = JSON.parse(JSON.stringify(state.draft));
  for (const sc of d.screens) {
    sc.elements = sc.elements.filter((e) => !e._removed);
  }
  return d;
}

function resetPlanView() {
  // 새로 만든 계획에서 예전 실행의 결과나 '통과 못 한 것만 다시 실행' 이 열리지 않게 비운다.
  state.result = null; state.report = null; state.resKind = ""; state.resSel = "";
  state.filter = ""; state.onlyOff = false; state.rule = ""; state.group = ""; state.sel = ""; state.mode = "items";
}

async function replan() {
  const doc = draftDoc();
  showProgress("고친 내용으로 항목을 다시 만드는 중", []);
  state.busy = true;
  renderChrome();
  try {
    const { job_id } = await api("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...form(), doc }),
    });
    state.plan = await follow(job_id, pushProgress);
    resetPlanView();
    state.busy = false;
    showPlan();
    notifyDone(`항목 ${state.plan.cases.length}개 뽑음`);
  } catch (err) {
    state.busy = false;
    showError("항목을 다시 만들지 못했어요", err.message);
  } finally {
    state.busy = false;
    renderChrome();
  }
}

/**
 * 화면 흐름 지도 — 기획서의 '화면 흐름' 표(Flow)를 화면 상자와 이동 선으로 그린다.
 *
 * 21st.dev 'Interactive Workflow Blueprint' 의 노드·연결선 그림만 가져왔다. 흐름은
 * 기획서가 정하는 것이라 여기서 끌어 옮기거나 잇지 않는다(편집기·내보내기는 버렸다).
 * 실선은 화면의 요소를 눌러 옮기는 전이 — 그 요소도 확인한다. 점선은 주소로 바로
 * 들어가는 전이 — 잇는 요소는 확인하지 않는다(models.Flow.via 의 설명).
 */
function flowMap(flow) {
  const screens = (state.plan.doc && state.plan.doc.screens) || [];
  const path = (sid) => (screens.find((s) => s.screen_id === sid) || {}).url_path || "";
  const parts = [];
  flow.screen_ids.forEach((sid, i) => {
    if (i > 0) {
      const via = (flow.via || [])[i - 1] || "";
      parts.push(via
        ? `<li class="fm-edge" data-via="click"><span>'${esc(via)}' 누름</span></li>`
        : `<li class="fm-edge" data-via="url" title="주소로 바로 들어가요 — 화면을 잇는 버튼·링크는 확인하지 않아요"><span>주소로 이동</span></li>`);
    }
    parts.push(`<li class="fm-node"><b>${esc(screenName(sid))}</b>` +
      (path(sid) ? `<code>${esc(path(sid))}</code>` : "") + `</li>`);
  });
  return `<ol class="flowmap" aria-label="화면 흐름">${parts.join("")}</ol>`;
}

// ── 3 실행 ─────────────────────────────────────────────────────────────────

async function startRun() {
  const ids = picked();
  showProgress("실행 중", []);
  state.busy = true;
  renderChrome();
  try {
    const { job_id } = await api("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // 2차 경로는 실행에만 쓰인다. 저장하지 않는다 — 지난번에 켠 채로 모르고
      // 계속 도는 일이 없게, 페이지를 열 때마다 꺼진 상태로 시작한다.
      body: JSON.stringify({ ...form(), case_ids: ids, reason: state.plan.reason || "",
                             vlm: $("vlm").checked,
                             // 쓰기 요청 막기 (prova.dry_run). 2차 경로처럼 저장하지 않는다.
                             dry_run: $("dryRun").checked,
                             // 고친 추출 결과로 만든 계획이면 그 문서로 실행한다 (spec_edits)
                             doc: (state.plan.spec_edits || []).length ? state.plan.doc : null }),
    });
    const stop = $("pStop");
    if (stop) {
      stop.hidden = false;
      stop.onclick = async () => {
        // 멈추면 그때까지 확인한 것도 저장하지 않는다(runner.py) — 되돌릴 수 없으니 한 번 묻는다.
        const done = Number($("pBar") && $("pBar").value) || 0;
        const ok = await confirmDialog({
          title: "실행을 멈출까요?",
          // 한 문장에 한 줄. '지금' 은 '확인 중인' 과 겹쳐 뺐다. 확인한 건수가 있으면 그것도 버려진다는 것을 말한다.
          body: [done ? `확인한 ${done}건도 저장하지 않아요.` : "이번 실행 결과는 저장하지 않아요.",
                 "확인 중인 항목이 끝나면 멈춰요."],
          keep: "계속 실행", go: "멈추기",
        });
        if (!ok || !stop.isConnected) return;  // 묻는 사이 실행이 끝났으면 할 일이 없다
        busyButton(stop, "지금 항목이 끝나면 멈춰요");
        try { await api(`/api/job/${job_id}/cancel`, { method: "POST" }); } catch (e) { /* 이미 끝났다 */ }
      };
    }
    const out = await follow(job_id, pushProgress);
    finishProgress();
    state.busy = false;
    state.resKind = ""; state.resSel = "";
    showResult(out);
    loadRuns();
    const d = (out.summary && (out.summary.defects ?? out.summary.fail)) || 0;
    notifyDone(d ? `✕ ${d}건 다름 · 결과 나옴` : "✓ 결과 나옴");
  } catch (err) {
    state.busy = false;
    if (err.status === 409) {
      // 409 는 셋이다 — 이미 실행 중, 대상 빌드가 낡음, 2차 경로 서버 없음.
      // 이유는 서버가 말한다. 한 문구로 뭉치면 낡은 대상을 '실행 중' 으로 안내한다.
      showError("실행을 시작하지 않았어요", err.message);
    } else if (err.message.startsWith("실행을 멈췄습니다")) {
      showError("실행을 멈췄어요", "같은 항목으로 다시 돌리려면 위의 '2 항목 검토' 를 눌러 주세요.");
    } else {
      showError("실행 실패", err.message);
    }
  } finally {
    state.busy = false;
    renderChrome();
  }
}

// ── 4 결과 ─────────────────────────────────────────────────────────────────
//
// 결과는 리포트 파일(report.html)을 틀에 띄우지 않고 같은 실행의 report.json 으로 직접 그린다
// (2026-11-24 hh). 리포트 파일은 그대로 남고 도구 막대의 '보고서 열기' 로 연다.

// 실패 원인 이름 — 리포트(report_builder.CATEGORY_LABELS)와 같은 말
const CATEGORY_NAME = {
  element_not_found: "화면에서 못 찾음", input_error: "입력 불가", assertion_mismatch: "기획서와 다름",
  timeout: "시간 초과", page_error: "페이지 오류", unknown: "원인 미분류", unverifiable: "확인 불가",
  precondition_failed: "전제 미충족",
};
const KIND = {
  defect: { label: "기획서와 다름", mark: "fail" },
  infra: { label: "실행 문제", mark: "infra" },
  unv: { label: "확인 불가", mark: "unv" },
  pass: { label: "통과", mark: "ok" },
};
// 실패의 세 갈래 — report_builder.fail_kind 와 같다.
const kindOf = (c) => c.verdict === "PASS" ? "pass"
  : c.failure_category === "assertion_mismatch" ? "defect"
  : c.failure_category === "unverifiable" ? "unv" : "infra";

function runWhen(iso) {
  const d = iso ? new Date(iso) : null;
  if (!d || isNaN(d)) return "";
  const p2 = (n) => String(n).padStart(2, "0");
  const hm = `${p2(d.getHours())}:${p2(d.getMinutes())}`;
  const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(new Date()) - day(d)) / 86400000);
  return diff === 0 ? `오늘 ${hm}` : diff === 1 ? `어제 ${hm}` : `${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${hm}`;
}

/**
 * 통과율 칸의 원형 차트 — 리포트 파일의 도넛과 같은 조각·같은 색(chart 토큰). hh 11-23 첫 요청
 * '검사 후 원형 차트 복구' 를 화면에도 지킨다.
 * hh 11-25 DonutChart 참고: 조각은 기획서와 다름 → 실행 문제 → 확인 불가 → 통과 순서, 끝은 각지게(둥근 끝은
 * 적은 건수를 크게 보이게 한다) 2px 틈. 결과를 처음 그릴 때만 조각이 차례로 그려진다(400ms, 60ms 차이).
 * 0건 조각은 그리지 않는다. 숫자 칸이 범례 — 칸에 올리거나 초점을 주면 그 조각만 진하고(나머지 35%),
 * 통과율 칸의 글자가 그 판정의 이름·건수·비율로 바뀐다. 화면 읽기에는 통과율이 늘 그대로 있다.
 */
const DONUT_ORDER = ["defect", "infra", "unv", "pass"];
function donut(n, total, say, { draw = true } = {}) {
  if (!total) return "";
  const keys = DONUT_ORDER.filter((k) => n[k]);
  const size = 64, c = size / 2, w = 10, r = c - w / 2 - 1, len = 2 * Math.PI * r;
  const gap = keys.length > 1 ? 2 : 0;
  let off = 0;
  const arcs = keys.map((k, i) => {
    const arc = (n[k] / total) * len, drawn = Math.max(arc - gap, 0.5);
    const el = `<circle class="seg ${k}" data-k="${k}" cx="${c}" cy="${c}" r="${r}" fill="none" stroke-width="${w}"` +
      ` stroke-dasharray="${drawn.toFixed(2)} ${(len - drawn).toFixed(2)}" stroke-dashoffset="${(-off).toFixed(2)}"` +
      ` style="--len:${len.toFixed(2)};--i:${i}"/>`;
    off += arc;
    return el;
  }).join("");
  return `<svg class="donut${draw ? " draw" : ""}" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" role="img" aria-label="${esc(say)}">` +
    `<circle class="track" cx="${c}" cy="${c}" r="${r}" fill="none" stroke-width="${w}"/>` +
    `<g transform="rotate(-90 ${c} ${c})">${arcs}</g></svg>`;
}

// 숫자 칸 = 범례, 고리도 범례 — 칸에 올리거나 초점을 주거나, 고리의 조각에 올리면 같은 상태가 된다:
// 그 조각만 굵고 진하고(나머지 35%), 그 칸이 올린 톤, 통과율 칸 글자가 그 판정으로 바뀐다(옛 글자는 위로 빠지고
// 새 글자가 4px 아래에서 들어온다 — 21st.dev DonutChart 의 가운데 글자 바뀜). 벗어나면 같은 식으로 통과율로.
// 바뀌는 글자는 눈으로만 — 화면 읽기에는 칸마다 제 글자가 있고 통과율은 숨은 글자로 늘 남는다.
function linkDonut(tiles, n, total, rate) {
  if (!tiles || !tiles.querySelector(".donut")) return;
  const rd = tiles.querySelector(".tile.rate .rd");
  const base = `<small>통과율</small><b>${esc(String(rate))}<span class="u">%</span></b>`;
  let cur = "", swapT = 0;
  const swap = (html) => {
    if (!rd) return;
    clearTimeout(swapT);
    rd.getAnimations().forEach((a) => a.cancel());
    if (reduceMotion() || !rd.animate) { rd.innerHTML = html; return; }
    const css = getComputedStyle(document.documentElement);
    const d = (parseFloat(css.getPropertyValue("--dur-2")) || 180) / 2, ease = css.getPropertyValue("--ease-out").trim() || "ease-out";
    rd.animate([{ opacity: 1, transform: "none" }, { opacity: 0, transform: "translateY(-4px)" }], { duration: d, easing: ease, fill: "forwards" });
    swapT = setTimeout(() => {
      rd.innerHTML = html;
      rd.getAnimations().forEach((a) => a.cancel());
      rd.animate([{ opacity: 0, transform: "translateY(4px)" }, { opacity: 1, transform: "none" }], { duration: d, easing: ease });
    }, d);
  };
  const on = (k) => {
    if (!(k && n[k] && tiles.querySelector(`.seg[data-k="${k}"]`))) return off();
    if (cur === k) return;
    cur = k;
    tiles.dataset.on = k;
    swap(`<small>${esc(KIND[k].label)} ${n[k]}건</small><b>${Math.round((n[k] / total) * 1000) / 10}<span class="u">%</span></b>`);
  };
  const off = () => {
    if (!cur) return;
    cur = "";
    delete tiles.dataset.on;
    swap(base);
  };
  tiles.addEventListener("pointerover", (e) => {
    const t = e.target.closest(".tile[data-k], .seg");
    if (t) on(t.dataset.k);
    else if (!e.target.closest(".tile.rate")) off();
  });
  tiles.addEventListener("pointerout", (e) => { if (e.target.closest(".seg") && !(e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest(".seg"))) off(); });
  tiles.addEventListener("pointerleave", off);
  tiles.addEventListener("focusin", (e) => { const t = e.target.closest(".tile[data-k]"); if (t) on(t.dataset.k); else off(); });
  tiles.addEventListener("focusout", (e) => { if (!tiles.contains(e.relatedTarget)) off(); });
}

/** 숫자를 0 에서 to 까지 세어 올린다(소수 자리는 to 를 따른다). 동작 줄이기면 바로. 틱에서는 글자만 바꾼다. */
function countUp(el, to, ms) {
  if (!el) return;
  const target = Number(to), dec = (String(to).split(".")[1] || "").length;
  if (reduceMotion() || !isFinite(target)) { el.textContent = String(to); return; }
  const t0 = performance.now();
  const tick = (now) => {
    const p = Math.min(1, (now - t0) / ms), e = 1 - Math.pow(1 - p, 3);   // ease-out
    el.textContent = p < 1 ? (target * e).toFixed(dec) : String(to);
    if (p < 1) requestAnimationFrame(tick);
  };
  el.textContent = (0).toFixed(dec);
  requestAnimationFrame(tick);
}

function showResult(out) {
  state.result = out;
  state.report = null;
  setView("result", 4);
  const s = out.summary;
  const planned = state.plan ? state.plan.cases.length : s.total;
  const off = planned - s.total;

  // 실패를 결함(기획서와 다름, 빨강)과 실행 문제(도구·환경, 보라)로 가른다.
  // defects 가 없는 옛 리포트는 실패를 전부 결함으로 읽던 예전 모양 그대로 둔다.
  // 확인 불가는 결함도 실행 문제도 아니다(요구서 4절 2번) — 따로 센다.
  const defects = s.defects ?? s.fail;
  const unv = s.unverifiable || 0;
  const infra = s.fail - defects - unv;

  const notes = [];
  if (off > 0) {
    notes.push(alertBox("info", "이 통과율은 전체 상태가 아니에요",
      `생성된 ${planned}건 중 ${s.total}건만 실행했어요. 나머지 ${off}건은 ` +
      `<b>통과한 것이 아니라 확인하지 않은 것</b>이에요.`));
  }
  if (s.vlm) {
    notes.push(alertBox("info", "화면 이미지로 찾기를 켜고 실행했어요",
      `라벨로 못 찾은 요소를 화면 이미지로 찾았어요 (${esc(s.vlm)}) — ` +
      `보정한 케이스 ${s.healed || 0}건. 보정한 케이스는 리포트에 따로 표시돼요.`));
  }
  if (s.not_found_without_vlm) {
    // 끈 실행은 필요한 상황이 와도 스스로 켜지지 않는다 — 다시 돌려 볼 만하다는 것을 알린다.
    notes.push(alertBox("info", `요소를 찾지 못한 케이스 ${s.not_found_without_vlm}건`,
      `화면 이미지로 찾기를 켜지 않은 실행이에요. 스크린샷에 그 요소가 보이는데 못 찾았다면 ` +
      `<b>실행 옵션의 '화면 이미지로 찾기' 를 켜서 다시 돌려 보세요</b> (모델 서버 필요). ` +
      `스크린샷에도 없다면 구현이 빠뜨린 것일 수 있고, 켜도 달라지지 않아요.`));
  }
  if (s.dry_run) {
    // 확인 불가도 실패 칸에 센다(확인하지 못한 것을 통과로 세지 않는다). 그 실패의 성질을 바로 말한다.
    const d = s.dry_run;
    notes.push(alertBox("warn", "쓰기 요청을 막고 실행했어요",
      `막은 케이스 ${d.cases_blocked || 0}건은 서버 응답을 못 봐 '확인 불가' 로 실패에 넣어요 — ` +
      `<b>구현 결함이 아니에요.</b> 막지 않은 ${s.total - (d.cases_blocked || 0)}건 중 통과 ${s.pass}. ` +
      `${esc(d.limits || "")}`));
  }
  if (s.llm_backend === "mock") {
    notes.push(alertBox("warn", "연습용으로 실행한 결과예요",
      "기획서를 실제 모델로 읽지 않았어요. 실제 검증 결과로 쓰지 마세요."));
  }

  // 조건 줄 — PM 이 읽을 것만: 어느 화면 · 몇 번째 실행 · 직전과 달라진 것.
  const h = s.history || {};
  // 화면이 많으면 이름을 잇지 않고 수만 적는다 — 리포트 파일과 같은 말(report_builder._screens_phrase).
  const allNames = Object.values(s.screen_names || {});
  const seenCount = Object.keys(s.by_screen || {}).length || allNames.length;
  const screens = !allNames.length ? ""
    : (allNames.length <= 3 && seenCount >= allNames.length) ? `${allNames.join(" · ")} 화면`
    : seenCount >= allNames.length ? `화면 ${allNames.length}개`
    : `기획서 화면 ${allNames.length}개 중 ${seenCount}개 확인`;
  const changed = (h.regressed || []).length + (h.fixed || []).length;
  const cond = [
    screens,
    h.round && `${h.round}번째 실행`,
    h.previous_run && (changed
      ? `직전보다 새로 실패 ${(h.regressed || []).length} · 해결 ${(h.fixed || []).length}`
      : "직전과 같은 결과"),
  ].filter(Boolean).join(" · ");
  const base = out.report_url.replace(/report\.html$/, "");
  // 리포트를 PDF 로도 받는다 — 받을 때 서버가 만든다(/api/report/<id>/pdf).
  const runId = base.replace(/\/$/, "").split("/").pop();
  const apiBase = `/api/report/${encodeURIComponent(runId)}`;

  // 도구 막대 제목 = 문서 이름과 때 (회차는 아래 조건 줄이 말한다 — 두 번 쓰지 않는다)
  if (!out.spec && state.plan) { out.spec = form().pdf; out.target = form().url; }
  out.doc = (out.spec || "").split(/[\\/]/).pop();
  setBar("결과", [out.doc, runWhen(out.created_at)].filter(Boolean).join(" · ") || runId);
  // 할 일은 도구 막대 오른쪽 한 곳 — 받기 둘, 열기, 다시 실행 (키트 Toolbar Button)
  $("barActions").innerHTML = `<div class="glass">
      <a href="${esc(base)}report.xlsx" download>${ICON.download}엑셀 받기</a>
      <a href="${esc(apiBase)}/pdf" download>PDF 받기</a><i aria-hidden="true"></i>
      <a href="${esc(out.report_url)}" target="_blank" rel="noopener">${ICON.open}보고서 열기</a>
      ${state.plan ? `<button id="againBtn" type="button">${ICON.again}다시 실행</button>` : ""}
    </div>`;
  const again = $("againBtn");
  // 같은 항목·같은 옵션으로 한 번 더 — 고친 뒤 확인할 때 1·2단계를 다시 밟지 않는다.
  if (again) again.addEventListener("click", startRun);

  const n = { pass: s.pass, defect: defects, infra, unv };
  const total = s.total || 1;
  // 숫자 칸이 곧 거르기 — 누르면 아래 목록이 그 판정만 보인다(사이드바 '결과 보기' 와 같은 일).
  // 21st.dev Test Results 의 '개수 버튼 = 필터'. 0건인 칸은 누를 일이 없으니 막아 둔다.
  const tile = (k, label, mark) =>
    `<button class="tile${n[k] ? "" : " zero"}" type="button" data-k="${k}" aria-pressed="false"${n[k] ? "" : " disabled"}>` +
    `<small>${vmark(mark, { dot: true, say: false })}${label}</small>` +
    `<b><span class="rn">${n[k]}</span><span class="sr">건만 보기</span></b></button>`;
  const parts = ["pass", "defect", "infra", "unv"].filter((k) => n[k]);
  $("stage").innerHTML = `
    <div class="scroll result-scroll" id="resScroll">
      <h2 class="verdict-line">${defects
        ? `${s.total}건 중 <mark class="fail">${defects}건이 기획서와 달라요.</mark>`
        : infra
        ? `${s.total}건 중 <mark class="infra">${infra}건을 실행 문제로 확인하지 못했어요.</mark>`
        : unv
        ? `${s.total}건 중 <mark class="unv">${unv}건은 판정할 근거가 없어요.</mark>`
        : `<mark class="pass">${s.total}건 모두 통과했어요.</mark>`}</h2>
      <p class="cond" id="resCond"${cond ? "" : " hidden"}>${esc(cond)}</p>
      <div class="next" id="nextActs">
        ${state.plan && s.fail ? `<button class="btn primary" id="retryBtn" type="button" disabled>${ICON.again}통과 못 한 ${s.fail}건만 다시 실행</button>` : ""}
        <button class="btn" id="copyBtn" type="button" disabled>${ICON.copy}개발팀에 보낼 요약 복사</button>
        ${state.plan && s.fail ? `<span class="hint">고친 뒤 이것만 다시 돌려 보면 돼요.</span>` : ""}
      </div>
      <div class="notes">${notes.join("")}</div>
      <div class="tiles">
        <div class="tile rate"><span class="sr">통과율 ${s.pass_rate}%</span>
          <span class="rd" aria-hidden="true"><small>통과율</small><b><span class="rn">${s.pass_rate}</span><span class="u">%</span></b></span>
          ${donut(n, total, parts.map((k) => `${KIND[k].label} ${n[k]}건`).join(", "))}</div>
        ${tile("pass", "통과", "ok")}${tile("defect", "기획서와 다름", "fail")}${tile("infra", "실행 문제", "infra")}${tile("unv", "확인 불가", "unv")}
      </div>
      <div class="split">
        <div class="flist" id="flist"><p class="empty">항목별 결과를 불러오는 중…</p></div>
        <div class="detail" id="detail" aria-live="polite"></div>
      </div>
    </div>`;
  $("stage").querySelectorAll("button.tile .rn").forEach(rollIn);
  // 통과율은 도넛이 다 그려지는 동안(400ms + 조각마다 60ms) 0 에서 세어 올라간다
  countUp($("stage").querySelector(".tile.rate .rn"), s.pass_rate, 400 + 60 * Math.max(parts.length - 1, 0));
  linkDonut($("stage").querySelector(".tiles"), n, total, s.pass_rate);
  tileDeltas(out, n);
  $("stage").querySelector(".tiles").addEventListener("click", (e) => {
    const b = e.target.closest("button.tile[data-k]");
    if (b && !b.disabled) pickResKind(b.dataset.k);
  });
  $("copyBtn").addEventListener("click", async () => {
    const ok = await copyText(summaryText(out));
    toast(ok ? "요약을 복사했어요 — 메신저나 이슈에 붙여 넣으면 돼요" : "복사하지 못했어요 — 보고서 열기에서 직접 골라 주세요");
  });
  if ($("retryBtn")) $("retryBtn").addEventListener("click", retryFailed);
  $("detail").addEventListener("click", onCite);
  $("sideFoot").textContent = out.target || runId;
  $("sideFoot").title = `실행 기록 ${runId}`;
  renderSideResult(null, n, h);
  loadReport(out, base);
}

async function loadReport(out, base) {
  let rep;
  try {
    rep = await api(`${base}report.json`);
  } catch (e) {
    // 예전 실행이라 report.json 이 없으면 리포트 파일을 그대로 띄운다.
    if (state.result !== out || document.body.dataset.view !== "result") return;
    $("copyBtn").disabled = false;
    $("copyBtn").innerHTML = ICON.copy + "실행 요약 복사";
    $("flist").innerHTML = `<p class="empty">항목별 결과 파일을 읽지 못해 리포트 파일을 아래에 띄워요.</p>`;
    $("detail").remove();
    $("resScroll").insertAdjacentHTML("beforeend",
      `<div class="reportbox"><iframe src="${esc(out.report_url)}" title="검증 리포트"></iframe></div>`);
    return;
  }
  if (state.result !== out || document.body.dataset.view !== "result") return;   // 그사이 다른 화면으로 갔다
  state.report = rep;
  $("copyBtn").disabled = false;
  if (!out.created_at && rep.created_at) {
    out.created_at = rep.created_at;
    $("barSub").textContent = [out.doc, runWhen(rep.created_at)].filter(Boolean).join(" · ");
  }
  const counts = { defect: 0, infra: 0, unv: 0, pass: 0 };
  rep.cases.forEach((c) => { counts[kindOf(c)] += 1; });
  // 걸린 시간 — 항목마다 잰 시간의 합(브라우저는 하나라 차례로 돈다). 조건 줄 끝에 붙인다.
  // 레퍼런스: 21st.dev Test Results 머리 줄 오른쪽의 전체 시간, GitHub Actions 실행 요약의 'Total duration'.
  const ms = rep.cases.reduce((t, c) => t + (c.elapsed_ms || 0), 0);
  const cond = $("resCond");
  if (cond && ms > 0) {
    const sec = Math.max(1, Math.round(ms / 1000));
    const took = sec < 60 ? `${sec}초` : `${Math.floor(sec / 60)}분${sec % 60 ? ` ${sec % 60}초` : ""}`;
    cond.textContent = [cond.textContent, `걸린 시간 ${took}`].filter(Boolean).join(" · ");
    cond.hidden = false;
  }
  const retry = $("retryBtn");
  if (retry) retry.disabled = !rep.cases.some((c) => c.verdict !== "PASS" && planCase(c.case_id));
  if (!state.resKind) state.resKind = ["defect", "infra", "unv", "pass"].find((k) => counts[k]) || "pass";
  renderSideResult(rep, counts, (out.summary && out.summary.history) || {});
  syncResPressed();
  renderFlist();
}

/** 통과 못 한 항목만 골라 같은 조건으로 다시 — 고친 뒤 확인할 때 17건을 다 기다리지 않는다. */
function retryFailed() {
  if (!state.plan || !state.report) return;
  const failed = new Set(state.report.cases.filter((c) => c.verdict !== "PASS").map((c) => c.case_id));
  state.plan.cases.forEach((c) => { c.selected = failed.has(c.case_id); });
  startRun();
}

/**
 * 개발팀에 붙여 넣을 글 — 메신저·이슈에 그대로 들어가게 꾸밈 없는 글자만.
 * 기획서와 다른 것을 먼저, 실행 문제·확인 불가는 따로 센다(결함으로 섞지 않는다).
 */
function summaryText(out) {
  const s = out.summary || {};
  const rep = state.report;
  const defects = s.defects ?? s.fail;
  const names = Object.values(s.screen_names || {});
  const when = runWhen(out.created_at || (rep && rep.created_at));
  const round = s.history && s.history.round;
  const lines = [
    `[Prova] ${[names.length ? `${names.join(" · ")} 화면` : prettySpec(out.spec), round && `${round}차`, when].filter(Boolean).join(" · ")}`,
    `대상 ${out.target || ""} · 기획서 ${out.doc || prettySpec(out.spec)}`,
    defects ? `${s.total}건 중 ${defects}건이 기획서와 달라요 (통과 ${s.pass})` : `${s.total}건 중 기획서와 다른 것은 없어요 (통과 ${s.pass})`,
  ];
  const rest = s.fail - defects;
  if (rest > 0) lines.push(`실행 문제·확인 불가 ${rest}건은 결함이 아니라 확인하지 못한 것이에요.`);
  if (s.llm_backend === "mock") lines.push("※ 연습용 실행 결과예요. 실제 검증 결과로 쓰지 마세요.");
  if (rep) {
    const bad = rep.cases.filter((c) => kindOf(c) === "defect");
    bad.forEach((c, i) => {
      const ev = c.evidence || {};
      const src = (c.spec_sources || []).map((x) => x.page && `${x.page}쪽`).filter(Boolean)[0];
      const flat = (x) => String(x).replace(/\s+/g, " ").trim();
      lines.push("", `${i + 1}. ${c.plain || c.title}`);
      if (ev.expected) lines.push(`   기대: ${flat(ev.expected)}`);
      lines.push(`   실제: ${actualLines(c).map(flat).join(" — ")}`);
      if (ev.url) lines.push(`   화면: ${ev.url}`);
      if (src) lines.push(`   근거: 기획서 ${src}`);
    });
  }
  lines.push("", `보고서 ${new URL(out.report_url, location.href).href}`);
  return lines.join("\n");
}

/** 사이드바 — 판정별 묶음. 고르면 가운데 목록이 그 묶음만 보인다. */
function renderSideResult(rep, n, h) {
  const item = (k, label, mark, count) =>
    `<li><button class="sitem" type="button" data-kind="${k}" aria-pressed="${state.resKind === k}" ${rep ? "" : "disabled"}>` +
    `${mark ? vmark(mark, { dot: true, say: false }) : ""}${label}<span class="ct">${count}</span></button></li>`;
  $("sideResult").innerHTML = `<h4>결과 보기</h4><ul class="slist">` +
    item("defect", "기획서와 다름", "fail", n.defect) + item("infra", "실행 문제", "infra", n.infra) +
    item("unv", "확인 불가", "unv", n.unv) + item("pass", "통과", "ok", n.pass) + `</ul>` +
    (h.previous_run ? `<h4>지난 회차와 비교</h4><ul class="slist">` +
      item("regressed", "새로 실패", "", (h.regressed || []).length) +
      item("fixed", "해결", "", (h.fixed || []).length) + `</ul>` : "");
}

$("sideResult").addEventListener("click", (e) => {
  const b = e.target.closest("[data-kind]");
  if (b) pickResKind(b.dataset.kind);
});

/** 판정 묶음 고르기 — 사이드바 줄과 위 숫자 칸 어느 쪽으로 골라도 같다. 둘 다 눌린 표시를 맞춘다. */
function pickResKind(k) {
  if (!state.report || !k) return;
  state.resKind = k;
  state.resSel = "";
  syncResPressed();
  renderFlist();
}
/**
 * 숫자 칸 아래 '직전보다 2건 늘었어요' — 21st.dev DashboardMetricCard 의 변화 줄만 가져왔다(오르내림 화살표·색은 뺐다:
 * 통과가 느는 것과 실패가 느는 것은 좋고 나쁨이 반대라 색으로 말하면 헷갈린다). 직전 실행의 리포트를 실제로 읽어
 * 같은 셈법(kindOf 와 같은 갈래)으로 센다. 직전이 없거나, 이번이 일부만 다시 돌린 실행이면 줄을 두지 않는다.
 */
const prevCounts = new Map();
async function tileDeltas(out, n) {
  const h = (out.summary && out.summary.history) || {};
  if (!h.previous_run || h.partial) return;
  let prev = prevCounts.get(h.previous_run);
  if (!prev) {
    try {
      const ps = (await api(`/runs/${encodeURIComponent(h.previous_run)}/report.json`)).summary || {};
      const defect = ps.defects ?? ps.fail ?? 0, unv = ps.unverifiable || 0;
      prev = { pass: ps.pass || 0, defect, unv, infra: Math.max(0, (ps.fail || 0) - defect - unv) };
      prevCounts.set(h.previous_run, prev);
    } catch (e) { return; }   // 못 읽으면 지어내지 않고 비워 둔다
  }
  if (state.result !== out) return;   // 그사이 다른 결과를 열었다
  for (const k of ["pass", "defect", "infra", "unv"]) {
    const t = document.querySelector(`#stage button.tile[data-k="${k}"]`);
    if (!t || t.querySelector(".delta")) continue;
    const d = n[k] - prev[k];
    t.insertAdjacentHTML("beforeend", `<small class="delta">${d === 0 ? "직전과 같아요"
      : `직전보다 ${Math.abs(d)}건 ${d > 0 ? "늘었어요" : "줄었어요"}`}</small>`);
  }
}

function syncResPressed() {
  $("sideResult").querySelectorAll("[data-kind]").forEach((x) =>
    x.setAttribute("aria-pressed", String(x.dataset.kind === state.resKind)));
  document.querySelectorAll("#stage .tile[data-k]").forEach((x) =>
    x.setAttribute("aria-pressed", String(x.dataset.k === state.resKind)));
}

function resCases() {
  const rep = state.report;
  const h = (state.result.summary && state.result.summary.history) || {};
  if (state.resKind === "regressed" || state.resKind === "fixed") {
    const want = new Set(h[state.resKind] || []);
    return rep.cases.filter((c) => want.has(c.title) || want.has(c.plain));
  }
  return rep.cases.filter((c) => kindOf(c) === state.resKind);
}

const planCase = (id) => state.plan && state.plan.cases.find((c) => c.case_id === id);

function resMeta(c) {
  const k = kindOf(c);
  const pc = planCase(c.case_id);
  return [c.target_label, pc && pc.rule_label,
    k === "infra" ? CATEGORY_NAME[c.failure_category] || "실행 문제" : "",
    c.elapsed_ms != null ? `${(c.elapsed_ms / 1000).toFixed(2)}초` : ""].filter(Boolean).join(" · ");
}

/** 가운데 목록 — 고른 묶음의 항목. 화면이 여럿이면 화면마다 머리 줄. */
function renderFlist() {
  const list = resCases();
  const names = (state.result.summary && state.result.summary.screen_names) || {};
  const label = { regressed: "새로 실패", fixed: "해결" }[state.resKind] || KIND[state.resKind].label;
  if (!list.length) {
    $("flist").innerHTML = `<div class="h">${esc(label)} · 0</div><p class="empty">이 묶음에 든 항목이 없어요.</p>`;
    $("detail").innerHTML = "";
    return;
  }
  if (!list.some((c) => c.case_id === state.resSel)) state.resSel = list[0].case_id;
  const groups = new Map();
  list.forEach((c) => {
    const g = c.flow_id ? `흐름 ${c.flow_id}` : names[c.screen_id] || c.screen_id || "";
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g).push(c);
  });
  const one = groups.size === 1;
  $("flist").innerHTML = [...groups].map(([g, cs]) =>
    `<div class="h">${esc(one ? label : g)} · ${cs.length}</div>` + cs.map((c) =>
      `<button class="it" type="button" data-id="${esc(c.case_id)}" aria-current="${c.case_id === state.resSel}">` +
      `${vmark(KIND[kindOf(c)].mark)}<span><p>${esc(c.plain || c.title)}</p><span class="hint">${esc(resMeta(c))}</span></span></button>`
    ).join("")).join("");
  renderDetail(list.find((c) => c.case_id === state.resSel));
}

$("stage").addEventListener("click", (e) => {
  const it = e.target.closest(".flist .it");
  if (!it || !state.report) return;
  state.resSel = it.dataset.id;
  $("flist").querySelectorAll(".it").forEach((x) => x.setAttribute("aria-current", String(x === it)));
  renderDetail(state.report.cases.find((c) => c.case_id === it.dataset.id));
});
$("stage").addEventListener("keydown", (e) => {
  const it = e.target.closest(".flist .it");
  if (!it || (e.key !== "ArrowDown" && e.key !== "ArrowUp")) return;
  e.preventDefault();
  const all = [...$("flist").querySelectorAll(".it")];
  const next = all[all.indexOf(it) + (e.key === "ArrowDown" ? 1 : -1)];
  if (next) { next.focus(); next.click(); }
});

// 실행한 단계를 사람 말로 — 리포트의 재현 절차와 같은 순서.
function stepWords(st, html = true) {
  const code = (v) => html ? `<code>${esc(v)}</code>` : `'${v}'`;
  const t = html ? esc(st.target || "") : st.target || "";
  switch (st.action) {
    case "navigate": return `열기 ${code(st.target || "")}`;
    case "fill": return `${t} ← ${code(st.value ?? "")}`;
    case "select": return `${t}에서 ${code(st.value ?? "")} 고르기`;
    case "check": return `${t} 체크`;
    case "uncheck": return `${t} 체크 해제`;
    case "click": return `'${t}' 누르기`;
    default: return `${html ? esc(st.action) : st.action} ${t}`.trim();
  }
}

// 실제로 일어난 일 — 판정 사유의 첫 문장, 관찰한 것이 다르면 그것도.
function actualLines(c) {
  const ev = c.evidence || {};
  if (c.verdict === "PASS") return [ev.actual || "기대한 대로 동작했어요."];
  const detail = (c.failure_detail || "").replace(/^기획서에 적힌 /, "");
  const head = detail.replace(/\s*\(([^()]*)\)\s*$/, "").trim();
  const lines = [];
  if (head) lines.push(head);
  if (ev.actual && !head.includes(ev.actual)) lines.push(ev.actual);
  return lines.length ? lines : ["사유가 기록되지 않았어요."];
}

/**
 * 결과의 실행한 단계 — 멈춘 단계 앞은 파란 체크, 멈춘 단계는 판정 색 표시와 글자('여기서 멈춤 · 기획서와 다름').
 * 멈춘 단계 = 처음 실패한 단계, 모두 성공했는데 통과가 아니면 마지막 단계(그 뒤 확인에서 갈렸다).
 * 통과면 모두 체크. 색만으로 말하지 않는다 — 글자가 같이 간다.
 */
function resultSteps(c, steps) {
  const k = kindOf(c);
  let stop = steps.findIndex((st) => st.status !== "ok");
  if (stop < 0 && k !== "pass") stop = steps.length - 1;
  const line = (st, i) => {
    const prep = st.phase && st.phase !== "test";
    const done = stop < 0 || i < stop;
    const node = i === stop ? vmark(KIND[k].mark, { say: false }) : done ? "✓" : esc(String(st.seq));
    return `<li class="${i === stop ? `stop ${k}` : done ? "done" : ""}${prep ? " prep" : ""}">` +
      `<span class="node" aria-hidden="true">${node}</span>` +
      `<span class="tx">${prep ? `<span class="pre">준비</span> ` : ""}${stepWords(st)}` +
      `${st.status !== "ok" && st.error_detail ? ` — ${esc(st.error_detail)}` : ""}` +
      `${i === stop ? `<span class="stop-lb">여기서 멈춤 · ${KIND[k].label}</span>` : done && stop >= 0 ? `<span class="sr"> (지나감)</span>` : ""}</span></li>`;
  };
  const rnd = (r) => `<li class="rnd" aria-hidden="true"><span></span><span>${r}회째</span></li>`;
  const plan = stepPlan(steps, stop);
  if (!plan) return steps.map(line).join("");
  const rows = (from, to, p) => steps.slice(from, to).map((st, j) =>
    (p && (from + j) % p === 0 ? rnd((from + j) / p + 1) : "") + line(st, from + j)).join("");
  const grp = `<li class="grp"><details class="disc"><summary><span class="node" aria-hidden="true">✓</span>` +
    `<span class="tx">${esc(plan.label)}<span class="chev" aria-hidden="true"></span></span></summary>` +
    `<ol class="tl">${rows(0, plan.hide, plan.period)}</ol></details></li>`;
  return grp + rows(plan.hide, steps.length, plan.period);
}

/**
 * 단계가 길면 앞쪽 통과한 단계를 한 줄로 접는다 (8개 이하는 그대로). report_builder.step_plan 과 같은 규칙.
 * - 같은 단계 묶음이 되풀이되면(동작·대상만 본다, 넣은 값은 무시) 멈춘 회차 앞의 회차를 '1–4회째 · 16단계 모두 통과' 로.
 * - 되풀이가 없으면 멈춘 단계 앞 3개만 두고 그 앞을 '앞 단계 N개 통과', 모두 통과면 마지막 하나만 두고 '단계 N개 모두 통과'.
 * 돌려주는 것: { hide: 접을 단계 수, period, rounds, label } 또는 접을 게 없으면 null.
 */
function stepPeriod(steps) {
  const sig = steps.map((st) => `${st.phase || ""}|${st.action || ""}|${st.target || ""}`);
  const n = sig.length;
  for (let p = 2; p <= n / 2; p++) {
    if (sig.every((x, i) => x === sig[i % p])) return p;
  }
  return 0;
}
function stepPlan(steps, stop) {
  const n = steps.length;
  if (n <= 8) return null;
  const p = stepPeriod(steps);
  if (p) {
    const at = Math.floor((stop >= 0 ? stop : n - 1) / p);
    if (at < 1) return null;
    return { hide: at * p, period: p, rounds: n / p,
             label: `${at > 1 ? `1–${at}` : "1"}회째 · ${at * p}단계 모두 통과` };
  }
  const hide = stop >= 0 ? stop - 3 : n - 1;
  if (hide < 2) return null;
  return { hide, period: 0, label: stop >= 0 ? `앞 단계 ${hide}개 통과` : `단계 ${hide}개 모두 통과` };
}
function stepsHead(steps) {
  const n = steps.length, p = n > 8 ? stepPeriod(steps) : 0;
  if (!p) return `실행한 단계 ${n}`;
  const full = Math.floor(n / p), rest = n % p;
  return `실행한 단계 ${n} · ${p}단계 × ${full}회${rest ? ` + ${rest}단계` : ""}`;
}

/** 오른쪽 상세 — 기대·실제, 기획서 원문, 마지막 화면과 실행한 단계. 리포트 파일을 열지 않아도 원인을 본다. */
function renderDetail(c) {
  const box = $("detail");
  if (!box || !c) return;
  const k = kindOf(c);
  const ev = c.evidence || {};
  const base = state.result.report_url.replace(/report\.html$/, "");
  const steps = c.step_results || [];
  const shotStep = steps.find((st) => st.screenshot === ev.screenshot);
  const lines = actualLines(c);
  const where = (() => { try { return ev.url ? new URL(ev.url).pathname : ""; } catch (e) { return ""; } })();
  const src = (c.spec_sources || []).map((s) => ({ page: s.page, kind: s.table ? "표" : "본문", quote: s.quote }));
  const names = (state.result.summary && state.result.summary.screen_names) || {};
  const head = { pass: "실제 — 통과", defect: "실제 — 기획서와 다름", unv: "실제 — 확인 불가",
                 infra: `실제 — 실행 문제 · ${CATEGORY_NAME[c.failure_category] || "원인 미분류"}` }[k];
  box.innerHTML = `
    <div><h3>${esc(c.plain || c.title)}</h3>
      <p class="hint meta">${esc([c.flow_id ? `흐름 ${c.flow_id}` : names[c.screen_id], resMeta(c)].filter(Boolean).join(" · "))}</p></div>
    <div class="ev">
      <div class="exp"><h6>기대</h6>${esc(ev.expected || "—")}</div>
      <div class="act ${k}"><h6>${head}</h6>${esc(lines[0])}${lines.slice(1).map((l) => `<div class="more">${esc(l)}</div>`).join("")}
        ${where ? `<div class="more">끝난 주소 <code class="code">${esc(where)}</code></div>` : ""}</div>
    </div>
    ${src.length ? `<div><h5>기획서 근거</h5>${src.map((s, i) =>
      `<div class="quote" data-i="${i}"><cite>${s.page ? `${s.page}쪽 ${s.kind}` : "기획서"}</cite>${markQuote(s.quote, ev.expected)}</div>`).join("")}</div>` : ""}
    <div class="shot">
      ${ev.screenshot ? `<figure><figcaption>${shotStep ? `${shotStep.seq}단계 ${esc(stepWords(shotStep, false))} 뒤 화면` : "마지막 화면"}</figcaption>
        <a href="${esc(base + ev.screenshot)}" target="_blank" rel="noopener" aria-label="마지막 화면 크게 보기 (새 탭)">
          <img src="${esc(base + ev.screenshot)}" alt="${esc(c.plain || c.title)} — 마지막 화면" loading="lazy"><span class="zoom-hint" aria-hidden="true">크게 보기</span></a></figure>`
        : `<figure><p class="noshot">이 항목은 화면을 찍지 않았어요.</p></figure>`}
      <div class="keysteps"><b>${esc(stepsHead(steps))}</b>
        <div><ol class="tl">${resultSteps(c, steps)}</ol>
        <p class="idline">${esc(c.case_id)}</p></div></div>
    </div>`;
}

// ── 계획 만들기 ────────────────────────────────────────────────────────────

$("planBtn").addEventListener("click", async () => {
  saveSettings();
  $("formNote").innerHTML = "";
  showProgress("기획서를 읽는 중", []);
  state.busy = true;
  renderChrome();
  $("planBtn").disabled = true;
  try {
    const { job_id } = await api("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form()),
    });
    state.plan = await follow(job_id, pushProgress);
    resetPlanView();
    state.busy = false;
    showPlan();
    notifyDone(`항목 ${state.plan.cases.length}개 뽑음`);
  } catch (err) {
    state.busy = false;
    if (err.status === 409) {
      showError("이미 실행 중이에요", "지금 도는 작업이 끝난 뒤 다시 눌러 주세요.");
    } else {
      showError("확인할 항목을 만들지 못했어요", err.message);
    }
  } finally {
    state.busy = false;
    $("planBtn").disabled = false;
    renderChrome();
  }
});

// ── 실행 기록 (1단계 사이드바) ─────────────────────────────────────────────

// 묶음마다 처음에 보이는 기록 수. 나머지는 '이전 기록 더 보기' 를 눌러야 보인다.
const RUNS_SHOWN = 5;

function runKind(r) {
  const defects = (r.summary && r.summary.defects) ?? r.fail;
  const unv = (r.summary && r.summary.unverifiable) || 0;
  const infra = r.fail - defects - unv;
  return defects ? "fail" : infra ? "infra" : unv ? "unv" : "ok";
}

async function loadRuns() {
  // 비어 있는 것과 아직 안 온 것을 구분해 준다. 빈 칸만 보이면 사람은 기록이 없는 줄 안다.
  // 처음 그릴 때만 — 줄 모양의 회색 자리(움직이지 않는다). 다시 불러올 때는 있던 목록을 그대로 둔다.
  if (!$("runs").children.length) {
    $("runs").setAttribute("aria-busy", "true");
    $("runs").innerHTML = `<p class="sr">기록을 불러오는 중</p><ul class="slist skel" aria-hidden="true">` +
      [72, 56, 64].map((w) => `<li><span class="sk"><i style="width:${w}%"></i><i style="width:${w - 24}%"></i></span></li>`).join("") + `</ul>`;
  }
  try {
    state.runs = (await api("/api/runs?limit=60")).runs;
    $("runs").removeAttribute("aria-busy");
  } catch (e) {
    $("runs").removeAttribute("aria-busy");
    $("runs").innerHTML = `<p class="empty">기록을 불러오지 못했어요. 서버가 켜져 있는지 확인해 주세요.</p>`;
    return;
  }
  // 방금 새 이름으로 돌렸으면 그 이름도 이제 고를 수 있는 프로젝트다.
  const ran = state.runs.map((r) => r.project || "").filter(Boolean);
  renderProjects([...new Set([...(state.projects || []), ...ran])].sort());
  renderRuns();
}

function renderRunsFoot() {
  if (document.body.dataset.view === "form") {
    $("sideFoot").textContent = state.runs.length ? `기록 ${state.runs.length}건` : "";
  }
}

/**
 * 실행 기록을 프로젝트별로 묶어 그린다 — 지금 고른 프로젝트가 맨 위.
 * 줄마다 기획서와 차수, 언제·몇 건 통과. 판정은 앞의 모양(✓ ✕ ! ?)과 숨은 낱말로도 말한다.
 */
function renderRuns() {
  const runs = state.runs;
  renderRunsFoot();
  renderDocMeta();
  syncTry();
  if (!runs.length) {
    $("runs").innerHTML = `<p class="empty">아직 확인한 기록이 없어요.<br>첫 확인이 끝나면 여기에 쌓여요.</p>`;
    return;
  }
  const q = (state.runFind || "").trim();
  const hits = q ? runs.map((r) => [r, findRun(r, q)]).filter(([, m]) => m) : runs.map((r) => [r, null]);
  if (q && !hits.length) {
    $("runs").innerHTML = `<p class="empty">'${esc(q)}' 에 맞는 기록이 없어요.</p>`;
    return;
  }
  const hit = new Map(hits);
  const current = $("project").value.trim();
  const groups = new Map();
  hits.map(([r]) => r).forEach((r) => {
    const key = r.project || "";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(r);
  });
  const order = [...groups.keys()].sort((a, b) => (b === current) - (a === current));
  $("runs").innerHTML = order.map((key) => {
    const list = groups.get(key);
    const open = state.runsOpen[key] || !!q;   // 찾는 중에는 다 보인다
    const shown = open ? list : list.slice(0, RUNS_SHOWN);
    const m = hit.get(list[0]) || {};
    return `<h4>${m.project ? markHits(key, m.project) : esc(key || "프로젝트 미지정")}<span class="ct">${list.length}회</span></h4><ul class="slist">` +
      shown.map((r) => `<li><button class="sitem tall" type="button" data-run="${esc(r.run_id)}" tabindex="-1"
          ${r.run_id === state.lastRun ? `aria-current="page"` : ""}
          title="${esc([`${r.target} · ${r.pass}/${r.total} 통과`, runWhere(r)].filter(Boolean).join("\n"))}">
        <span class="two"><b>${(hit.get(r) || {}).title ? markHits(runTitle(r), hit.get(r).title) : esc(runTitle(r))}</b>
        <span>${esc([r.round && `${r.round}차`, runAgo(r.created_at)].filter(Boolean).join(" · "))}</span></span>${runPill(r)}</button></li>`).join("") +
      (list.length > RUNS_SHOWN && !q ? `<li><button class="sitem more" type="button" data-more="${esc(key)}" tabindex="-1">${open
        ? "접기" : `이전 기록 ${list.length - RUNS_SHOWN}개 더 보기`}</button></li>` : "") + `</ul>`;
  }).join("");
  rovingRuns();
  fadeLongTitles();
}

/* ── 기록 찾기 — 21st.dev(chatcn) ChatSidebar 에서 '목록 위 찾기 칸' 만 ─────────────────
 * 글자가 순서대로 들어 있으면 맞는다(띄어 있어도: '회가' → 회원가입). 화면 이름·프로젝트·주소(호스트)에서 찾는다.
 * 맞은 글자는 색 없이 굵게(<mark>). 칸은 돋보기나 '/' 로 열고, Esc 는 비우고 닫는다. */
function fuzzyAt(text, q) {
  const t = String(text || "").toLowerCase(), want = q.toLowerCase().replace(/\s+/g, "");
  if (!want) return null;
  const at = [];
  let i = 0;
  for (const ch of want) {
    i = t.indexOf(ch, i);
    if (i < 0) return null;
    at.push(i++);
  }
  return at;
}
function findRun(r, q) {
  const host = String(r.target || "").replace(/^https?:\/\//, "");
  const title = fuzzyAt(runTitle(r), q), project = fuzzyAt(r.project || "", q), where = fuzzyAt(host, q);
  return title || project || where ? { title, project } : null;
}
function markHits(text, at) {
  const set = new Set(at);
  return [...String(text)].map((ch, i) => set.has(i) ? `<mark>${esc(ch)}</mark>` : esc(ch)).join("");
}
function openFind(focus = true) {
  $("findOpen").hidden = true;
  const f = $("rfind").querySelector(".rfind-field");
  f.hidden = false;
  if (focus) $("findRuns").focus();
}
function closeFind() {
  state.runFind = "";
  $("findRuns").value = "";
  $("rfind").querySelector(".rfind-field").hidden = true;
  $("findOpen").hidden = false;
  renderRuns();
  $("findOpen").focus();
}
$("findOpen").addEventListener("click", () => openFind());
$("findRuns").addEventListener("input", (e) => { state.runFind = e.target.value; renderRuns(); });
$("findRuns").addEventListener("keydown", (e) => {
  if (e.key === "Escape") { e.preventDefault(); closeFind(); }
  if (e.key === "ArrowDown") { e.preventDefault(); const b = $("runs").querySelector("[data-run]"); if (b) b.focus(); }
});
$("findRuns").addEventListener("blur", () => { if (!$("findRuns").value) setTimeout(() => {
  if (document.activeElement !== $("findRuns") && !$("findRuns").value) {
    $("rfind").querySelector(".rfind-field").hidden = true; $("findOpen").hidden = false; }
}, 0); });
// '/' — 글자를 넣는 칸에 있지 않을 때만, 첫 화면에서만
document.addEventListener("keydown", (e) => {
  if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey || document.body.dataset.view !== "form") return;
  const a = document.activeElement;
  if (a && (a.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName))) return;
  if (document.documentElement.classList.contains("side-rail") || document.querySelector("dialog[open]")) return;
  e.preventDefault();
  openFind();
});

/* 기록 줄 사이는 ↑/↓ 로 옮긴다(목록 안에서 탭 한 번만 멈춘다 — roving tabindex). Enter 는 단추라 그대로 연다.
 * Home/End 는 처음·끝. 마지막으로 연 기록은 aria-current="page". */
function rovingRuns() {
  const items = [...$("runs").querySelectorAll("button.sitem")];
  if (!items.length) return;
  const cur = items.find((b) => b.getAttribute("aria-current") === "page") || items[0];
  items.forEach((b) => { b.tabIndex = b === cur ? 0 : -1; });
}
$("runs").addEventListener("keydown", (e) => {
  const items = [...$("runs").querySelectorAll("button.sitem")];
  const i = items.indexOf(document.activeElement);
  if (i < 0) return;
  const to = e.key === "ArrowDown" ? i + 1 : e.key === "ArrowUp" ? i - 1 : e.key === "Home" ? 0 : e.key === "End" ? items.length - 1 : null;
  if (to === null) return;
  e.preventDefault();
  if (to < 0) { if (!$("rfind").querySelector(".rfind-field").hidden) $("findRuns").focus(); return; }
  const next = items[Math.min(to, items.length - 1)];
  items.forEach((b) => { b.tabIndex = b === next ? 0 : -1; });
  next.focus();
});

// 긴 이름은 '…' 대신 오른쪽 끝을 흐리게 — 넘칠 때만 (판정 알약은 그대로 읽힌다)
function fadeLongTitles() {
  $("runs").querySelectorAll(".sitem .two > b").forEach((b) => b.classList.toggle("ovf", b.scrollWidth > b.clientWidth + 1));
}

// 방금 끝난 기록은 '12분 전' 처럼 — 한 시간이 넘으면 '오늘 17:57' (GitHub Actions 실행 목록처럼).
function runAgo(iso) {
  const t = iso ? Date.parse(iso) : NaN;
  if (isNaN(t)) return "";
  const min = Math.floor((Date.now() - t) / 60000);
  return min < 1 ? "방금" : min < 60 ? `${min}분 전` : runWhen(iso);
}

// 기록 이름 — 파일 이름(signup_spec) 대신 사람이 부르는 화면 이름(회원가입). 화면이 없으면 파일 이름을 다듬어 쓴다.
const prettySpec = (p) => String(p || "").split(/[\\/]/).pop()
  .replace(/\.(pdf|json)$/i, "").replace(/[_-]spec$/i, "").replace(/[_-]+/g, " ").trim();

function runTitle(r) {
  const names = Object.values((r.summary && r.summary.screen_names) || {});
  if (names.length) return names.length <= 2 ? names.join(" · ") : `${names[0]} 외 ${names.length - 1}곳`;
  return prettySpec(r.spec) || r.run_id;
}

// 판정 알약 — 색만으로 말하지 않는다(디자인 기준 2번). 글자가 먼저, 색은 덧붙임.
function runPill(r) {
  const s = r.summary || {};
  const defects = s.defects ?? r.fail;
  const unv = s.unverifiable || 0;
  const infra = r.fail - defects - unv;
  const [k, say] = defects ? ["fail", `${defects}건 다름`] : infra ? ["infra", `실행 문제 ${infra}`]
    : unv ? ["unv", `확인 불가 ${unv}`] : ["ok", "모두 통과"];
  return `<span class="rpill ${k}">${say}</span>`;
}

/** 고른 기획서를 지난번에 언제 확인했고 결과가 어땠는지 — 기획서 이름 아래 한 줄. */
function renderDocMeta() {
  const el = $("docMeta");
  if (!el) return;
  const spec = ($("pdf").value || "").split(/[\\/]/).pop();
  if (!spec) { el.textContent = ""; return; }
  const last = (state.runs || []).find((r) => (r.spec || "").split(/[\\/]/).pop() === spec);
  el.innerHTML = last
    ? `지난 확인 · ${esc([last.round && `${last.round}차`, runAgo(last.created_at)].filter(Boolean).join(" · "))} ${runPill(last)}`
    : "아직 확인한 적 없는 기획서예요";
  renderRecap(last);
}

/**
 * 넓은 화면의 첫 화면 오른쪽 — 고른 기획서를 지난번에 확인한 결과(무엇이 달랐는지)를 미리 보여 준다.
 * 고친 뒤 다시 확인하러 온 사람이 결과 화면까지 가지 않고도 '지난번에 뭐가 틀렸지' 를 본다.
 * 확인한 적 없는 기획서면 네 단계가 각각 무엇을 하는지 적는다. 좁은 화면에서는 CSS 가 숨긴다.
 */
const recapCases = new Map();   // run_id → 항목 결과(report.json cases). 한 번 읽으면 다시 안 읽는다.
/**
 * 지난 확인의 판정 고리 — 21st.dev Activity Card 의 '고리 + 숫자 + 비율' 배치만 가져왔다.
 * 통과·기획서와 다름은 늘 두고, 실행 문제·확인 불가는 있을 때만 둔다(0건 고리가 늘어서면 시끄럽다).
 * 원본은 테두리를 잘라 낸 가짜 고리라 실제 비율과 안 맞는다 — 여기서는 SVG 호 길이가 건수 비율 그대로다.
 * 고리는 처음 그려질 때 0 에서 제 길이까지 차오르고(600ms), 색은 판정 토큰. 글자가 뜻을 말하고 색은 거든다.
 */
function recapRings(total, rows) {
  const C = 2 * Math.PI * 30;   // r=30
  rows = rows.filter(([k, , n]) => n > 0 || k === "pass" || k === "fail");
  return `<ul class="rc-rings" aria-label="판정별 건수" style="--cols:${rows.length}">${rows.map(([k, label, n]) => {
    const pct = total ? Math.round((n / total) * 100) : 0;
    const len = total ? (n / total) * C : 0;
    return `<li class="rc-ring ${k}">
      <span class="ring"><svg viewBox="0 0 72 72" aria-hidden="true"><circle class="tr" cx="36" cy="36" r="30"/>
        <circle class="arc" cx="36" cy="36" r="30" style="--len:${len.toFixed(1)};--c:${C.toFixed(1)}" stroke-dasharray="${len.toFixed(1)} ${C.toFixed(1)}"/></svg>
        <b class="nums">${n}</b><small>건</small></span>
      <span class="lb">${label}</span><span class="pc nums">${pct}%</span></li>`;
  }).join("")}</ul>`;
}

async function renderRecap(last) {
  const el = $("recap");
  if (!el) return;
  if (!last) {
    el.dataset.k = "first";
    el.innerHTML = `<p class="rc-k">이렇게 확인해요</p>
      <ol class="rc-steps">
        <li><b>확인할 항목 뽑기</b><span>기획서를 읽고 화면마다 확인할 것을 골라요. 바로 실행하지 않아요.</span></li>
        <li><b>항목 검토</b><span>뺄 항목은 끄고, 기획서에서 읽은 내용이 맞는지 봐요.</span></li>
        <li><b>실행</b><span>사이트를 직접 눌러 보며 하나씩 확인해요.</span></li>
        <li><b>결과</b><span>기획서와 다른 곳을 기획서 근거와 화면으로 보여 줘요.</span></li>
      </ol>`;
    delete el.dataset.run;
    return;
  }
  if (el.dataset.run === last.run_id) return;
  const s = last.summary || {};
  const defects = s.defects ?? last.fail;
  const unv = s.unverifiable || 0;
  const infra = last.fail - defects - unv;
  const total = s.total || last.total;
  const verdict = defects ? `${total}건 중 <mark class="fail">${defects}건이 기획서와 달라요</mark>`
    : infra ? `${total}건 중 <mark class="infra">${infra}건은 실행 문제로 확인하지 못했어요</mark>`
    : unv ? `${total}건 중 <mark class="unv">${unv}건은 판정할 근거가 없어요</mark>`
    : `<mark class="pass">${total}건 모두 통과했어요</mark>`;
  const host = String(last.target || "").replace(/^https?:\/\//, "");
  el.dataset.k = "last";
  el.dataset.run = last.run_id;
  el.innerHTML = `<p class="rc-k">이 기획서의 지난 확인</p>
    <p class="rc-when hint">${esc([last.round && `${last.round}차`, runAgo(last.created_at), host].filter(Boolean).join(" · "))}</p>
    <h3 class="rc-v">${verdict}</h3>
    ${recapRings(total, [["pass", "통과", total - last.fail], ["fail", "기획서와 다름", defects], ["infra", "실행 문제", infra], ["unv", "확인 불가", unv]])}
    <ul class="rc-list" id="recapList">${last.fail ? `<li class="hint">항목을 불러오는 중…</li>` : ""}</ul>
    <button class="btn go" type="button" id="recapOpen">결과 자세히 보기<span class="arr" aria-hidden="true">→</span></button>`;
  $("recapOpen").addEventListener("click", () => openRun(last));
  if (!last.fail) { $("recapList").remove(); return; }
  let cases = recapCases.get(last.run_id);
  if (!cases) {
    try { cases = (await api(`/runs/${encodeURIComponent(last.run_id)}/report.json`)).cases || []; }
    catch (e) { cases = null; }
    if (cases) recapCases.set(last.run_id, cases);
  }
  const list = $("recapList");
  if (!list || el.dataset.run !== last.run_id) return;   // 그사이 다른 기획서를 골랐다
  if (!cases) { list.innerHTML = `<li class="hint">항목별 결과를 불러오지 못했어요.</li>`; return; }
  const order = { defect: 0, infra: 1, unv: 2 };
  const bad = cases.filter((c) => kindOf(c) !== "pass").sort((a, b) => order[kindOf(a)] - order[kindOf(b)]);
  const SHOW = 5;
  list.innerHTML = bad.slice(0, SHOW).map((c) =>
    `<li>${vmark(KIND[kindOf(c)].mark)}<span>${esc(c.plain || c.title)}</span></li>`).join("") +
    (bad.length > SHOW ? `<li class="more hint">외 ${bad.length - SHOW}건</li>` : "");
  fitRecapList(list, bad.length);
}

// 카드가 왼쪽 카드 높이에 맞춰 잘리면(넓은 화면) 다 보이지 않는 항목을 빼고 '외 N건' 으로 센다 — 반쯤 잘린 줄을 남기지 않는다.
// 카드 크기가 바뀌면(창 크기·사이드바 접기, 좁은 창에서 숨어 있다가 나타남) 처음 목록으로 되돌려 다시 맞춘다.
const recapFitRO = window.ResizeObserver ? new ResizeObserver((es) => es.forEach((e) => {
  const list = e.target, h = Math.round(e.contentRect.height);
  if (!list.isConnected || list.dataset.fitH === String(h) || list._full === undefined) return;
  list.dataset.fitH = String(h);
  list.innerHTML = list._full;
  fitRecapList(list, list._total, true);
})) : null;
function fitRecapList(list, total, again = false) {
  if (!again) { list._full = list.innerHTML; list._total = total; if (recapFitRO) recapFitRO.observe(list); }
  if (!list.clientHeight || list.scrollHeight <= list.clientHeight + 1) return;
  const items = () => [...list.querySelectorAll("li:not(.more)")];
  let more = list.querySelector("li.more");
  if (!more) { list.insertAdjacentHTML("beforeend", `<li class="more hint"></li>`); more = list.lastElementChild; }
  while (items().length > 1 && list.scrollHeight > list.clientHeight + 1) {
    items().pop().remove();
    more.textContent = `외 ${total - items().length}건`;
  }
}

// 처음 온 사람에게만 — 예시 기획서와 결함을 심은 예시 사이트로 한 번에 끝까지 가 보게 한다.
const TRY_SPEC = "fixtures/specs/signup_spec.pdf";
function syncTry() {
  const has = [...$("pdf").options].some((o) => o.value === TRY_SPEC);
  $("tryRow").hidden = !has || (state.runs || []).length > 0;
}

$("tryBtn").addEventListener("click", () => {
  $("pdf").value = TRY_SPEC;
  $("url").value = "http://localhost:8100/bad";
  if ([...$("backend").options].some((o) => o.value === "mock")) $("backend").value = "mock";
  saveSettings(); syncVariant(); renderChrome(); renderDocMeta();
  $("planBtn").click();
});

/**
 * 통과 못 한 케이스가 어느 화면에서 났는지 — 많은 순으로, 흐름 케이스는 '흐름' 하나로.
 * 사이드바 줄 위에 올리면 뜨는 도움말에 한 줄로 붙인다(macOS 도움말 태그). 예전에는 둘째 줄이
 * 위로 빠지며 바뀌었는데, 사이드바 줄이 저절로 모양을 바꾸는 것은 macOS 답지 않아 글만 남겼다.
 */
function runWhere(r) {
  const s = r.summary || {};
  const names = s.screen_names || {};
  const parts = Object.entries(s.by_screen || {})
    .filter(([, v]) => v && v.fail).map(([k, v]) => [names[k] || k, v.fail]);
  const flows = Object.values(s.by_flow || {}).reduce((n, v) => n + ((v && v.fail) || 0), 0);
  if (flows) parts.push(["흐름", flows]);
  if (!parts.length) return "";
  parts.sort((a, b) => b[1] - a[1]);
  return `통과 못 한 곳: ${parts.map(([nm, c]) => `${nm} ${c}`).join(" · ")}`;
}

$("runs").addEventListener("click", (e) => {
  const more = e.target.closest("[data-more]");
  if (more) {
    const key = more.dataset.more;
    state.runsOpen[key] = !state.runsOpen[key];
    renderRuns();
    const again = [...$("runs").querySelectorAll("[data-more]")].find((x) => x.dataset.more === key);
    if (again) again.focus();
    return;
  }
  const btn = e.target.closest("[data-run]");
  if (!btn || state.busy) return;
  openRun(state.runs.find((x) => x.run_id === btn.dataset.run));
});

/** 지난 실행 하나를 결과 화면으로 연다 — 사이드바 기록 줄과 첫 화면 '지난 확인' 이 같이 쓴다. */
function openRun(r) {
  if (!r || state.busy) return;
  state.lastRun = r.run_id;
  state.plan = null;
  state.resKind = ""; state.resSel = "";
  showResult({ run_id: r.run_id, summary: r.summary, created_at: r.created_at,
               spec: r.spec, target: r.target, report_url: `/runs/${r.run_id}/report.html` });
}

// ── 기획서 묶음 · 프로젝트 ─────────────────────────────────────────────────

/**
 * 기획서 셀렉트를 묶음별로 그린다. 지금 고른 프로젝트의 묶음이 맨 위다.
 *
 * 다른 묶음도 고를 수 있게 둔다 — 예시 기획서를 프로젝트 이름으로 돌려 보는 일이 흔하고,
 * 막으면 '프로젝트를 지워야 예시가 보인다' 가 된다.
 */
function renderSpecs(select) {
  const current = $("project").value.trim();
  const keep = select !== undefined ? select : $("pdf").value;
  // 값은 경로, 보이는 것은 파일 이름 — 폴더가 매 줄 반복되면 이름이 안 보인다.
  const base = (p) => p.split(/[\\/]/).pop();
  const mine = (g) => current !== "" && g.project === current;
  const groups = [...state.specGroups].sort((a, b) => mine(b) - mine(a));
  $("pdf").innerHTML = groups.map((g) => `
    <optgroup label="${esc(g.project ? `프로젝트 · ${g.label}` : g.label)}">
      ${g.specs.map((p) => `<option value="${esc(p)}">${esc(base(p))}</option>`).join("")}
    </optgroup>`).join("")
    || `<option value="" disabled selected>기획서 PDF 를 먼저 올려 주세요</option>`;
  if (keep && [...$("pdf").options].some((o) => o.value === keep)) $("pdf").value = keep;
}

// 프로젝트는 목록에서 고른다. 고른 이름은 숨은 칸(#project)이 담는다.
// 새로 만들 때는 '새 프로젝트 만들기' 를 골라 이름을 적고 [추가] 를 눌러야 목록에 들어가
// 선택된다 — 전에는 적는 글자가 곧바로 프로젝트 이름이 되어, 다 적었는지 아닌지와
// 무관하게 그 이름으로 계획·올리기가 나갔다.
// 이름에 쓸 수 없는 글자(:)를 넣어 실제 프로젝트 이름과 겹치지 않게 한다.
const NEW_PROJECT = "::new";

// [추가] 했지만 아직 실행·올리기가 없는 이름. 서버는 기획서나 실행이 생겨야 프로젝트를
// 알게 되므로, 그 전까지는 이 브라우저가 기억한다.
const DRAFT_KEY = "prova.projects.draft";

function draftProjects() {
  try { return JSON.parse(localStorage.getItem(DRAFT_KEY)) || []; } catch (e) { return []; }
}

function knownProjects() {
  const current = $("project").value.trim();
  const all = [...(state.projects || []), ...draftProjects(), ...(current ? [current] : [])];
  return [...new Set(all)].sort();
}

function renderProjects(names) {
  if (names) state.projects = names;
  const pick = $("projectPick");
  const making = pick.value === NEW_PROJECT;
  pick.innerHTML = `<option value="">프로젝트 없음</option>` +
    knownProjects().map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("") +
    `<option value="${NEW_PROJECT}">새 프로젝트 만들기…</option>`;
  pick.value = making ? NEW_PROJECT : $("project").value.trim();
  $("projectNewRow").hidden = !making;
}

// 값이 바뀐 것은 이름 칸의 일이다 — 거기 달린 처리(올릴 자리·묶음·저장)를 그대로 태운다.
function setProject(name) {
  const input = $("project");
  input.value = name;
  input.dispatchEvent(new Event("input"));
  input.dispatchEvent(new Event("change"));
}

function projectError(message) {
  $("projectErr").textContent = message || "";
  $("projectErr").hidden = !message;
}

$("projectPick").addEventListener("change", () => {
  const picked = $("projectPick").value;
  projectError("");
  // 만드는 중에는 아직 어느 프로젝트도 아니다.
  setProject(picked === NEW_PROJECT ? "" : picked);
  $("projectNewRow").hidden = picked !== NEW_PROJECT;
  if (picked === NEW_PROJECT) { $("projectNew").value = ""; $("projectNew").focus(); }
});

// 서버(_project_name)와 같은 규칙. 이름이 곧 uploads/ 아래 폴더 이름이다.
function projectNameProblem(name) {
  if (!name) return "프로젝트 이름을 적어 주세요.";
  const forbidden = /[\/\\:*?"<>|\x00-\x1f]/;
  if (name.length > 60 || name.startsWith(".") || name.endsWith(".") || forbidden.test(name)) {
    return "이 이름은 쓸 수 없어요 — 60자 이하로, / \\ : * ? \" < > | 없이, " +
           "점으로 시작하거나 끝나지 않게 적어 주세요.";
  }
  return "";
}

/** 적은 이름을 목록에 넣고 고른다. 넣었으면 true. */
function addProject() {
  const name = $("projectNew").value.trim();
  const problem = projectNameProblem(name);
  if (problem) { projectError(problem); $("projectNew").focus(); return false; }
  projectError("");
  if (!(state.projects || []).includes(name)) {
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify([...new Set([...draftProjects(), name])]));
    } catch (e) { /* 저장 못 해도 이번 화면에서는 고를 수 있다 */ }
  }
  $("projectNew").value = "";
  $("projectPick").value = "";   // '만드는 중' 을 끝낸다
  setProject(name);              // 이미 있는 이름이면 그것을 고르는 것과 같다
  renderProjects();
  return true;
}

$("projectAdd").addEventListener("click", addProject);
$("projectNew").addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); addProject(); }
});
$("projectNew").addEventListener("input", () => projectError(""));

// 이름을 적어 놓고 [추가] 를 안 누른 채 계획을 만들면 '프로젝트 없음' 으로 나간다.
// 조용히 그렇게 두지 않고 멈춰서 알린다 — 다른 처리보다 먼저 돌도록 캡처 단계에 건다.
$("planBtn").addEventListener("click", (e) => {
  if ($("projectNewRow").hidden || !$("projectNew").value.trim()) return;
  e.stopImmediatePropagation();
  projectError("적어 둔 프로젝트 이름이 아직 추가되지 않았어요 — [추가] 를 누르거나 이름을 지워 주세요.");
  $("projectNew").focus();
}, true);

// 사이트 주소가 비었거나 http(s):// 로 시작하지 않으면 칸 바로 아래에 알리고 멈춘다
// (PageSpeed Insights 처럼 — 기획서를 다 읽은 뒤에야 주소 때문에 실패하지 않게).
function urlProblem(url) {
  if (!url) return "검사할 사이트 주소를 넣어 주세요.";
  if (/^https?:\/\//i.test(url) && !/\s/.test(url)) {
    try { if (new URL(url).hostname) return ""; } catch { /* 아래 문구로 알린다 */ }
  }
  return `'${url}' 는 열 수 없는 주소예요. http:// 나 https:// 로 시작하는 전체 주소를 넣어 주세요.`;
}
$("planBtn").addEventListener("click", (e) => {
  const why = urlProblem($("url").value.trim());
  const err = $("urlErr");
  err.textContent = why; err.hidden = !why;
  $("url").setAttribute("aria-invalid", String(Boolean(why)));
  if (!why) return;
  e.stopImmediatePropagation();
  $("url").focus();
}, true);
$("url").addEventListener("input", () => {
  if ($("urlErr").hidden) return;
  $("urlErr").hidden = true; $("url").setAttribute("aria-invalid", "false");
});

// 화면별 주소에 틀린 줄이 있으면 멈춘다 — 그 줄을 빼고 돌리면 적은 화면이 0건이 된다.
// 접힌 '실행 옵션' 안에 있으므로 펼쳐서 보여 준다.
$("planBtn").addEventListener("click", (e) => {
  if (screenUrls().bad.length === 0) return;
  e.stopImmediatePropagation();
  renderScreenUrlsErr();
  $("opts").open = true;
  $("screenUrls").focus();
}, true);

function syncUploadLabel() {
  const btn = $("uploadBtn");
  const label = btn.querySelector("span");
  if (!label || btn.getAttribute("aria-busy") === "true") return;
  const current = $("project").value.trim();
  // 파일 창을 연다 — HIG: 끝에 말줄임
  label.textContent = current ? `'${current}' 에 기획서 올리기…` : "기획서 올리기…";
}

async function refreshSpecs(select) {
  const st = await api("/api/state");
  state.specGroups = st.spec_groups || [];
  renderProjects(st.projects || []);
  renderSpecs(select);
}

// 글자를 칠 때마다: 올릴 자리와 묶음 순서, 실행 기록의 묶음 순서를 맞춘다.
$("project").addEventListener("input", () => {
  syncUploadLabel();
  renderSpecs();
  renderRuns();
});

// 이름을 다 적었을 때: 그 프로젝트에 기획서가 있으면 그중 첫 것을 고른다.
$("project").addEventListener("change", () => {
  const current = $("project").value.trim();
  const own = state.specGroups.find((g) => current !== "" && g.project === current);
  if (own && !own.specs.includes($("pdf").value)) $("pdf").value = own.specs[0];
  saveSettings();
  syncVariant();
  renderChrome();
  renderDocMeta();
});

// ── 기획서 올리기 ──────────────────────────────────────────────────────────

$("uploadBtn").addEventListener("click", () => $("upload").click());

$("upload").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (file) await uploadFile(file);
});

$("dropPick").addEventListener("click", () => $("upload").click());

/**
 * 올린 파일 한 줄 — 21st.dev Attachment States 에서. 상태는 서버가 실제로 하는 일만 보인다:
 * 올리는 중(몇 % 는 브라우저가 보낸 양), 올림, 못 올림. 서버는 받은 파일을 저장만 하므로
 * '처리 중' 단계는 두지 않는다 — 없는 일을 있는 척 보여 주지 않는다.
 * 못 올림은 알림이라 닫지 못하고(디자인 기준 1번) 다시 시도만 있다. 올리는 중의 × 는 멈추기다.
 */
const ATT_X = `<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M3 3l6 6M9 3l-6 6"/></svg>`;
const upload = { xhr: null, file: null };

function sizeText(bytes) {
  if (!Number.isFinite(bytes)) return "";
  return bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function showAttach(stateName, file, { pct = 0, why = "", retry = false, picked = "" } = {}) {
  const box = $("attach");
  if (!stateName) { box.innerHTML = ""; return; }
  const media = stateName === "uploading" ? vmark("run", { say: false })
    : stateName === "done" ? vmark("done", { say: false }) : ICON.warn;
  const say = stateName === "uploading" ? `올리는 중 · <span class="pct">${Math.round(pct * 100)}%</span>`
    : stateName === "done" ? [`올렸어요`, sizeText(file.size), picked].filter(Boolean).join(" · ")
    : `<span class="sr">오류: </span>올리지 못했어요 — ${why}`;
  const acts = stateName === "uploading"
    ? `<button type="button" class="att-x" id="attStop" aria-label="올리기 멈추기" title="올리기 멈추기">${ATT_X}</button>`
    : stateName === "error" && retry ? `<button type="button" class="btn sm" id="attRetry">다시 시도</button>` : "";
  box.innerHTML = `<div class="att" data-state="${stateName}" role="${stateName === "error" ? "alert" : "status"}">` +
    `<span class="att-media">${media}</span>` +
    `<span class="att-body"><b>${esc(file.name)}</b><small>${say}</small></span>` +
    (acts ? `<span class="att-acts">${acts}</span>` : "") +
    (stateName === "uploading" ? `<span class="att-bar" aria-hidden="true"><i></i></span>` : "") + `</div>`;
  if ($("attStop")) $("attStop").addEventListener("click", () => upload.xhr && upload.xhr.abort());
  if ($("attRetry")) $("attRetry").addEventListener("click", () => upload.file && uploadFile(upload.file));
  if (stateName === "uploading") setAttachPct(pct);
}

// 몇 % 만 바꾼다 — 줄을 새로 그리면 도는 호가 처음부터 다시 돈다.
function setAttachPct(pct) {
  const row = $("attach").querySelector('.att[data-state="uploading"]');
  if (!row) return;
  row.querySelector(".pct").textContent = `${Math.round(pct * 100)}%`;
  row.style.setProperty("--p", String(pct));
}

// fetch 는 보낸 양을 알려 주지 않는다 — 몇 % 를 보이려고 업로드만 XMLHttpRequest 로 보낸다.
function postWithProgress(path, body, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    upload.xhr = xhr;
    xhr.open("POST", path);
    xhr.responseType = "json";
    xhr.upload.addEventListener("progress", (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); });
    xhr.addEventListener("load", () => {
      const out = xhr.response || {};
      if (xhr.status >= 200 && xhr.status < 300) resolve(out);
      else reject(new ApiError(detailText(out.detail) || `${xhr.status} ${xhr.statusText}`, xhr.status));
    });
    xhr.addEventListener("error", () =>
      reject(new ApiError("서버에 연결하지 못했어요. prova serve 가 켜져 있는지 확인해 주세요.", 0)));
    xhr.addEventListener("abort", () => reject(new ApiError("멈췄어요", -1)));
    xhr.send(body);
  });
}

async function uploadFile(file) {
  const btn = $("uploadBtn");
  if (btn.getAttribute("aria-busy") === "true") return;
  upload.file = file;
  busyButton(btn, "올리는 중");
  renderChrome();
  showAttach("uploading", file);
  try {
    const fd = new FormData();
    fd.append("file", file);
    // 기획서는 지금 적힌 프로젝트의 폴더로 들어간다 (서버가 이름을 확인한다).
    fd.append("project", $("project").value.trim());
    const out = await postWithProgress("/api/upload", fd, setAttachPct);
    // JSON 은 Figma 응답, PDF 는 기획서 — 올라간 쪽 셀렉트에 넣고 선택한다.
    const isJson = out.path.toLowerCase().endsWith(".json");
    if (isJson) {
      const target = $("figma");
      if (![...target.options].some((o) => o.value === out.path)) {
        const opt = document.createElement("option");
        opt.value = out.path; opt.textContent = out.path;
        target.appendChild(opt);
      }
      target.value = out.path;
    } else {
      await refreshSpecs(out.path);
    }
    $("formNote").innerHTML = "";
    showAttach("done", file, { picked: isJson ? "실행 옵션의 Figma 자료로 골랐어요" : "기획서로 골랐어요" });
    saveSettings();
    syncVariant();
    renderChrome();
    renderDocMeta();
  } catch (err) {
    // 멈춘 것은 사람이 한 일이니 줄을 거둔다. 실패는 조용히 사라지면 올라간 줄 안다 — 남긴다.
    if (err.status === -1) showAttach(null);
    else showAttach("error", file, { why: esc(err.message), retry: true });
  } finally {
    upload.xhr = null;
    idleButton(btn); syncUploadLabel();
    renderChrome();
  }
}

/**
 * 기획서 상자에 파일을 끌어 놓아도 올라간다 — 21st.dev File Upload 의 '끌어 놓기'.
 * 놓을 수 있는 동안 끌어 놓는 자리가 파랗게 서고 문서 카드 셋이 벌어진다(app.css .gbox.dropping).
 * PDF·JSON 이 아니면 올리지 않고 그 줄에 알린다. 상자 밖에 놓쳐도 브라우저가 파일을 열어
 * 화면을 떠나지 않게 막는다.
 */
(function dropToUpload() {
  const zone = $("dropZone");
  const hasFiles = (e) => [...(e.dataTransfer && e.dataTransfer.types || [])].includes("Files");
  let depth = 0;
  const leave = () => { depth = 0; zone.classList.remove("dropping"); };
  zone.addEventListener("dragenter", (e) => {
    if (!hasFiles(e) || $("uploadBtn").getAttribute("aria-busy") === "true") return;
    e.preventDefault();
    if (depth++ === 0) zone.classList.add("dropping");
  });
  zone.addEventListener("dragover", (e) => { if (hasFiles(e)) { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; } });
  zone.addEventListener("dragleave", () => { if (--depth <= 0) leave(); });
  zone.addEventListener("drop", async (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    leave();
    if (upload.xhr) return;
    const file = e.dataTransfer.files[0];
    if (!file) return;
    if (!/\.(pdf|json)$/i.test(file.name)) {
      upload.file = null;
      showAttach("error", file, { why: "PDF(기획서) 또는 JSON(Figma 응답)만 올릴 수 있어요." });
      return;
    }
    await uploadFile(file);
  });
  window.addEventListener("dragover", (e) => { if (hasFiles(e)) e.preventDefault(); });
  window.addEventListener("drop", (e) => { if (hasFiles(e)) e.preventDefault(); });
})();

// ── 예시 사이트 고르기 ─────────────────────────────────────────────────────

function setVariant(which) {
  const url = $("url").value.trim();
  $("url").value = url.replace(/\/(good|bad)(\/|$)/, `/${which}$2`);
  syncVariant();
  saveSettings();
  renderChrome();
}

function syncVariant() {
  const m = /\/(good|bad)(\/|$)/.exec($("url").value);
  $("segGood").setAttribute("aria-pressed", String(m ? m[1] === "good" : false));
  $("segBad").setAttribute("aria-pressed", String(m ? m[1] === "bad" : false));
  $("variantRow").hidden = !($("pdf").value || "").startsWith("fixtures/");
  placeSegThumb();
}

// 예시 사이트 고르기의 흰 판도 단계 표시와 같은 방식으로 미끄러진다.
const segThumb = stretchThumb($("variantRow"));
function placeSegThumb(instant = false) {
  const seg = $("variantRow");
  const on = seg.querySelector('button[aria-pressed="true"]');
  if (!on || !on.offsetWidth) { segThumb.to(null); delete seg.dataset.thumb; return; }
  segThumb.to(on, { instant });
  seg.dataset.thumb = "1";
}

$("segGood").addEventListener("click", () => setVariant("good"));
$("segBad").addEventListener("click", () => setVariant("bad"));
// ← → 로도 고른다. 고른 쪽으로 초점도 옮긴다.
$("variantRow").addEventListener("keydown", (e) => {
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
  e.preventDefault();
  const which = e.key === "ArrowRight" ? "bad" : "good";
  setVariant(which);
  $(which === "bad" ? "segBad" : "segGood").focus();
});

["vlm", "dryRun"].forEach((id) => $(id).addEventListener("change", renderChrome));
$("screenUrls").addEventListener("input", () => {
  renderScreenUrlsErr(); renderChrome(); saveSettings();
});

["pdf", "url", "backend", "figma"].forEach((id) =>
  $(id).addEventListener("change", () => { saveSettings(); syncVariant(); renderChrome(); renderDocMeta(); }));

$("url").addEventListener("input", () => { syncVariant(); renderChrome(); });

// Ctrl/Cmd + Enter 로 다음 단계. 단추 위 표시는 쓰는 컴퓨터에 맞춘다(맥 ⌘↵, 그 밖 Ctrl ↵).
const platform = navigator.userAgentData?.platform || navigator.platform || "";
$("planBtn").querySelector("kbd").textContent = /mac|iphone|ipad/i.test(platform) ? "⌘↵" : "Ctrl ↵";
document.addEventListener("keydown", (e) => {
  if (document.querySelector("dialog[open]") || !(e.key === "Enter" && (e.ctrlKey || e.metaKey))) return;
  const view = document.body.dataset.view;
  const run = $("runBtn");
  if (view === "plan" && run && !run.disabled) { run.click(); return; }
  if (view === "form" && !$("planBtn").disabled) $("planBtn").click();
});

// ── 밝게 / 어둡게 — 사이드바 아래 스위치 (보고서의 _THEME_BTN_JS 를 그대로 옮겼다) ─────────────────
// 저장한 값이 없으면 OS 설정을 따르고, OS 를 바꾸면 따라간다. 한 번 바꾸면 'prova-theme' 에 남아
// 웹 UI 와 보고서가 같은 모드로 열린다.
(function () {
  var btn = document.getElementById('themeBtn'), root = document.documentElement;
  if (!btn) return;
  var knob = btn.querySelector('.tg-knob'), fill = btn.querySelector('.tg-fill');
  var sun = btn.querySelector('.tg-ico.sun'), moon = btn.querySelector('.tg-ico.moon');
  var ks = btn.querySelector('.k-sun'), km = btn.querySelector('.k-moon');
  var still = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  var os = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
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
  btn._settle = function () { btn.setAttribute('aria-checked', String(dark())); settle(); };
  s.p = s.q = dark() ? 1 : 0;
  var g0 = goal(); s.L.x = g0[0]; s.R.x = g0[1];
  btn.setAttribute('aria-checked', String(dark()));
  paint();
})();;
(function () {
  var os = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  if (!os || !os.addEventListener) return;
  os.addEventListener('change', function () {
    var stored = null;
    try { stored = localStorage.getItem('prova-theme'); } catch (e) {}
    if (stored === 'light' || stored === 'dark') return;
    // 저장한 값이 없으면 OS 를 따라 손잡이·상태를 다시 맞춘다
    var btn = document.getElementById('themeBtn');
    if (btn && btn._settle) btn._settle();
  });
})();

// ── 시작 ───────────────────────────────────────────────────────────────────

async function boot() {
  try {
    const st = await api("/api/state");
    state.serverBackend = st.backend;
    const saved = loadSettings();
    state.specGroups = st.spec_groups || [];
    renderProjects(st.projects || []);
    if (typeof saved.screenUrls === "string") $("screenUrls").value = saved.screenUrls;
    if (saved.project) { $("project").value = saved.project; renderProjects(); }
    else renderProjects();
    syncUploadLabel();
    renderSpecs(saved.pdf || "");
    $("figma").innerHTML = `<option value="">없음 — 기획서만</option>` +
      (st.figmas || []).map((p) =>
        `<option value="${esc(p)}">${esc(p)}</option>`).join("");
    $("backend").value = st.backend;

    if (saved.figma && [...$("figma").options].some((o) => o.value === saved.figma)) {
      $("figma").value = saved.figma;
    }
    if (saved.url) $("url").value = saved.url;
    // 지난번 선택이 서버 기본값을 덮을 때는 그 사실을 보인다 — 한 번 mock 을
    // 고른 사람이 모르는 채 계속 mock 으로 돌지 않게.
    // 서버를 연습용 설정(configs/demo.yaml)으로 띄웠다면 그 뜻이 우선이다 — 지난번에
    // 고른 '실제 모델' 이 남아 있으면 모델 서버 없이 띄운 데모가 바로 실패한다.
    if (saved.backend && saved.backend !== st.backend && st.backend !== "mock") {
      $("backend").value = saved.backend;
      $("backend").closest(".ctl").insertAdjacentHTML("beforeend",
        `<div class="hint">지난번 선택이에요 — 서버 기본값은 ${esc(st.backend)}</div>`);
    }
  } catch (err) {
    // 여기서 조용히 실패하면 화면이 죽은 채로 남는다.
    showBlank();
    $("formNote").innerHTML = alertBox("fail", "서버에 연결하지 못했어요", esc(err.message));
    return;
  }
  syncVariant();
  renderChrome();
  showBlank();
  loadRuns();
}

boot();
