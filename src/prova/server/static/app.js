/* Prova 작업 콘솔.
 *
 * 프레임워크를 쓰지 않는다. 상태가 셋뿐이고(설정·계획·결과) 화면 전환이 없으므로
 * 프레임워크의 값보다 빌드 단계와 CDN 의존이 더 비싸다 — 리포트가 폐쇄망에서
 * 열려야 한다는 원칙과 같은 이유다.
 *
 * 화면은 한 번에 한 단계만 보여준다: 빈 상태 → 계획 확인 → 실행 중 → 결과.
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
  search: `<svg width="13" height="13" viewBox="0 0 14 14" fill="none" aria-hidden="true"><circle cx="6" cy="6" r="4.2" stroke="currentColor" stroke-width="1.5"/><path d="M9.2 9.2l3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`,
};

// 알림 상자의 종류를 읽어 주는 프로그램에도 알린다 — 21st.dev Notifications 의 role 에서.
// 오류는 바로 끼어들어 읽고(alert), 주의·참고는 하던 말을 마친 뒤 읽는다(status).
// 종류는 아이콘 모양과 색으로만 보이므로 앞에 낱말을 숨겨 붙인다(HIG: 색·모양만으로 전하지 않는다).
// 닫기(×)는 넣지 않는다 — 디자인 기준 1번 '알림 상자는 숨기거나 접지 않는다'.
const ALERT_SAY = { fail: ["alert", "오류"], warn: ["status", "주의"], info: ["status", "참고"] };
function alertBox(kind, title, why) {
  const [role, say] = ALERT_SAY[kind] || ALERT_SAY.info;
  return `<div class="alert ${kind}" role="${role}">${ICON[kind] || ICON.info}<div>` +
    `<b><span class="sr">${say}: </span>${title}</b>${why ? `<div class="why">${why}</div>` : ""}</div></div>`;
}

// ── 움직임 ─────────────────────────────────────────────────────────────────
// 상태가 바뀔 때만 움직인다 — 단계 이동, 항목 완료, 숫자 바뀜, 호버 위치. 들어올 때
// 장식으로 흔들지 않는다. 화면 설정이 '동작 줄이기' 면 바뀐 모습만 바로 보인다.
// 동작은 21st.dev 컴포넌트에서 옮겼고(이름은 각 함수 위), 겉모양은 tokens.css 를 따른다.
const reduceMotion = () =>
  !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

/**
 * 목록 위를 미끄러지는 호버 배경 한 장 (21st.dev 'Fluid Hover Highlight').
 *
 * 줄마다 배경이 켜졌다 꺼지는 대신 한 장이 올린 줄로 옮겨 선다 — Apple HIG 에 맞춰(2026-11-24)
 * 줄 사이를 날아가지는 않고 바로 선다. 펼쳐서 키가 바뀌면 따라 늘어난다. 나가면 사라진다.
 * 상자를 innerHTML 로 다시 그려도 다음 호버 때 배경을 새로 만든다. 터치에서는 쓰지 않는다.
 */
function fluidHover(box, selector) {
  if (!box) return;
  box.classList.add("has-hl");
  if (box.dataset.hl) return;            // 이벤트는 상자마다 한 번만 건다
  box.dataset.hl = "1";
  let row = null, rowH = 0;
  // 펼친 줄은 키가 바뀐다 — 펼침이 260ms 동안 자라므로 매 프레임 따라간다(처음 관찰은 건너뛴다).
  const ro = window.ResizeObserver ? new ResizeObserver(([en]) => {
    const h = en.target.getBoundingClientRect().height;
    if (en.target === row && Math.abs(h - rowH) > 0.5) { rowH = h; place(true); }
  }) : null;
  const layer = () => {
    let hl = box.querySelector(":scope > .hl");
    if (!hl) {
      hl = document.createElement("div");
      hl.className = "hl";
      hl.setAttribute("aria-hidden", "true");
      box.prepend(hl);
    }
    return hl;
  };
  const hide = () => {
    row = null;
    if (ro) ro.disconnect();
    const hl = box.querySelector(":scope > .hl");
    if (hl) hl.classList.remove("on");
  };
  const place = (snap) => {
    if (!row || !row.isConnected) { hide(); return; }
    const hl = layer();
    const b = box.getBoundingClientRect(), r = row.getBoundingClientRect();
    if (snap) hl.style.transition = "none";
    hl.style.transform = `translate(${r.left - b.left}px, ${r.top - b.top}px)`;
    hl.style.width = `${r.width}px`;
    hl.style.height = `${r.height}px`;
    if (snap) { hl.getBoundingClientRect(); hl.style.transition = ""; }
    hl.classList.add("on");
  };
  box.addEventListener("pointerover", (e) => {
    if (e.pointerType === "touch") return;
    const r = e.target.closest(selector);
    if (!r || !box.contains(r) || r === row) return;
    row = r;
    rowH = r.getBoundingClientRect().height;
    if (ro) { ro.disconnect(); ro.observe(r); }
    // Apple HIG Motion: 목록 위를 훑는 일은 아주 잦다 — 배경이 줄 사이를 날아가지 않고 그 줄에 바로 선다.
    place(true);
  });
  box.addEventListener("pointerleave", hide);
  // ResizeObserver 가 없는 브라우저 — 펼친 직후 한 번만 맞춘다. toggle 은 올라오지 않아 잡는 단계에서 받는다.
  if (!ro) box.addEventListener("toggle", () => place(false), true);
}

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
 *
 * 21st.dev 'Animated Generate Button' 에서 '누르면 그 버튼이 진행 중 이름으로 바뀐다' 만 가져왔다.
 * Apple HIG Buttons 도 같은 말을 한다 — 바로 끝나지 않는 동작은 버튼 안에 진행 표시를 띄운다.
 * 버튼은 줄어들지 않는다(옆 버튼이 밀려 움직이지 않게). 눌린 동안은 다시 누를 수 없다.
 * 원본의 반짝이 기호·글자별 반짝임·빛 번짐·확대·흐림·그림자 여러 겹은 버렸다.
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
 * 늘어났다 줄어드는 선택 판 (21st.dev 'Liquid Navbar — Waterline' 의 CSS 대체 경로).
 *
 * 판의 앞쪽은 빠른 용수철로 새 자리에 먼저 닿고, 뒤쪽은 70ms 늦게 느린 용수철로
 * 따라온다. 그래서 판이 잠깐 늘어났다가 제 크기로 줄어든다. 빨리 움직이는 동안은
 * 조금 납작해지고, 끝에 닿으면 살짝 눌린다. 움직임이 멎으면 매 프레임 계산도 멈춘다.
 * 원본의 물 셰이더(WebGL)·물방울 갈라짐·물결·소리·아이콘 장면·유리 굴절은 쓰지 않는다.
 *
 * host 에 --thumb-l(왼쪽 끝) · --thumb-w(폭) · --thumb-sy(세로 배율) 를 적는다.
 * 그리는 쪽(CSS 의 ::before)이 이 세 값을 읽는다.
 */
function stretchThumb(host) {
  const s = { a: { x: 0, v: 0 }, b: { x: 0, v: 0 }, sy: { s: 1, v: 0 }, lead: 0, lagFrom: 0,
              x: 0, hw: 0, r: 0, hwNow: 0, lo: 0, hi: 0, raf: 0, last: 0, ready: false };
  const paint = () => {
    const sep = Math.abs(s.a.x - s.b.x);
    const thin = Math.min(sep / (2 * s.hwNow || 1), 1);
    const q = Math.max(0, s.hwNow - s.r), r = s.r * (1 - 0.3 * thin);   // 늘어날수록 조금 가늘어진다
    host.style.setProperty("--thumb-l", `${Math.min(s.a.x, s.b.x) - q - r}px`);
    host.style.setProperty("--thumb-w", `${sep + 2 * (q + r)}px`);
    host.style.setProperty("--thumb-sy", s.sy.s.toFixed(4));
  };
  const step = (dt, now) => {
    let still = true;
    s.hwNow += (s.hw - s.hwNow) * Math.min(1, dt * 12);
    // Apple HIG Motion(2026-11-24): 자주 누르는 컨트롤의 움직임은 짧고 정확하게. 앞·뒤 끝의 시간차로
    // 늘어나던 것, 빨리 갈 때 납작해지던 것, 끝에서 되튀던 것을 뺐다. 두 끝이 같은 용수철(임계 감쇠 —
    // 넘치지 않는다)로 함께 가서 판은 0.25초 안에 미끄러져 멎기만 한다.
    [s.a, s.b].forEach((B) => {
      B.v += (260 * (s.x - B.x) - 32 * B.v) * dt;
      B.x = Math.max(s.lo, Math.min(s.hi, B.x + B.v * dt));
      if (Math.abs(s.x - B.x) > 0.3 || Math.abs(B.v) > 3) still = false;
    });
    return still;
  };
  const snap = () => {
    s.a.x = s.b.x = s.x; s.a.v = s.b.v = 0; s.sy.s = 1; s.sy.v = 0; s.hwNow = s.hw;
    cancelAnimationFrame(s.raf); s.raf = 0;
    paint();
  };
  const loop = () => {
    if (s.raf) return;
    s.last = performance.now();
    const tick = (now) => {
      const dt = Math.min((now - s.last) / 1000, 1 / 30);
      s.last = now;
      const still = step(dt, now);
      if (still) { s.raf = 0; snap(); return; }
      paint();
      s.raf = requestAnimationFrame(tick);
    };
    s.raf = requestAnimationFrame(tick);
  };
  return {
    /** el 아래로 판을 옮긴다. 처음 자리·창 크기 바뀜·동작 줄이기 설정에서는 바로 옮긴다. */
    to(el, { instant = false, lo, hi } = {}) {
      if (!el || !el.offsetWidth) { s.ready = false; return; }   // 숨어 있으면 다음에 처음처럼
      const x = el.offsetLeft + el.offsetWidth / 2;
      s.hw = el.offsetWidth / 2;
      s.r = el.offsetHeight / 2;
      s.lo = lo ?? -Infinity; s.hi = hi ?? Infinity;
      const moved = Math.abs(x - s.x) > 0.5;
      s.x = x;
      if (!s.ready || instant || reduceMotion()) { s.ready = true; snap(); return; }
      if (!moved) { paint(); return; }
      s.lead = Math.abs(x - s.a.x) <= Math.abs(x - s.b.x) ? 0 : 1;   // 가까운 쪽이 앞장선다
      s.lagFrom = performance.now() + 70;
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
    throw new ApiError("서버에 연결하지 못했습니다. prova serve 가 살아 있는지 확인하세요.", 0);
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(detailText(body.detail) || `${res.status} ${res.statusText}`, res.status);
  return body;
}

// FastAPI 의 422 는 detail 이 배열이다. 그대로 쓰면 화면에 [object Object] 가 뜬다.
function detailText(detail) {
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || JSON.stringify(d)).join(" / ")
      || "요청 형식이 올바르지 않습니다";
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
        throw new ApiError("서버와의 연결이 끊겼습니다. 작업은 계속 돌고 있을 수 있습니다.", 0);
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
  result: null,      // 마지막 실행 결과
  filter: "",        // 케이스 검색어
  onlyOff: false,    // 제외된 것만 보기
  serverBackend: "mock",
  busy: false,
  specGroups: [],    // 기획서 묶음 — 프로젝트 폴더들, 프로젝트 없이 올린 것, 예시
  projects: [],      // 고를 수 있는 프로젝트 이름
  runs: [],          // 실행 기록 (프로젝트를 바꾸면 다시 그리기만 한다)
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

// ── 상단 · 칩 ──────────────────────────────────────────────────────────────

// 화면에 보이는 이름. 값(mock·vllm·replay)은 서버와 주고받는 이름이라 그대로 둔다.
const BACKEND_NAME = { mock: "연습용", vllm: "실제 모델", replay: "저장된 응답" };

// Apple HIG Toolbars: 창 제목은 앱 이름이 아니라 지금 보는 곳을 짧게 — 탭을 여러 개 띄워도 구별된다.
// 실행 중에는 'n/N 실행 중' 이 대신 선다(pushProgress).
const STEP_TITLE = { 1: "기획서", 2: "항목 검토", 3: "실행", 4: "결과" };
const pageTitle = () => `${STEP_TITLE[document.body.dataset.step] || STEP_TITLE[1]} — Prova`;

function renderChrome() {
  syncStepper();
  if (!state.busy) document.title = pageTitle();
  const f = form();
  const spec = (f.pdf || "").split("/").pop() || "기획서 없음";
  $("crumbs").innerHTML =
    `<b>${esc(spec)}</b><span class="sep">→</span><span>${esc(f.url || "대상 없음")}</span>`;

  $("chips").innerHTML =
    `<span class="chip ${state.busy ? "busy" : "ok"}"><i class="dot"></i>` +
    `${state.busy ? "실행 중" : "준비됨"}</span>` +
    `<span class="chip">${esc(BACKEND_NAME[f.backend] || f.backend)}</span>` +
    (f.figma ? `<span class="chip">병합 — 디자인 대조</span>` : "");

  // 실행 옵션은 접혀 있다 — 지금 값은 접힌 채로도 보여야 모르고 켠 채 돌리지 않는다.
  const nUrls = Object.keys(f.screen_urls).length;
  $("optsNow").textContent = [BACKEND_NAME[f.backend] || f.backend, f.figma && "Figma 함께",
    nUrls && `화면 주소 ${nUrls}개`,
    $("vlm").checked && "이미지로 찾기 켬", $("dryRun").checked && "쓰기 막기 켬",
  ].filter(Boolean).join(" · ");
}

// ── 무대 (한 번에 한 상태만) ────────────────────────────────────────────────

// 지금 몇 단계인지. 1단계에서만 입력 양식이 보이고, 나머지는 무대가 화면을 다 쓴다.
function setStep(n) {
  const prev = Number(document.body.dataset.step) || 0;
  document.body.dataset.step = n;
  for (const el of $("stepper").querySelectorAll("[data-step]")) {
    const s = Number(el.dataset.step);
    if (s === n) el.setAttribute("aria-current", "step");
    else el.removeAttribute("aria-current");
    // 지난 단계는 체크, 지금 단계는 검은 원, 남은 단계는 빈 원. 잇는 선은 지난 구간만 채운다.
    el.parentElement.dataset.state = s < n ? "done" : s === n ? "now" : "next";
  }
  syncStepper();
  placeThumb();
  if (!state.busy) document.title = pageTitle();
  if (prev && prev !== n) stepChanged(prev, n);
}

/**
 * 갈 수 있는 단계만 누를 수 있다 (21st.dev 'Wizard Steps' 의 '가 본 곳까지만').
 * 계획이 없을 때의 '항목 검토', 실행 중의 번호는 눌러도 아무 일이 없었는데 단추처럼 보였다.
 */
function syncStepper() {
  for (const b of $("stepper").querySelectorAll("button[data-step]")) {
    b.disabled = state.busy || (b.dataset.step === "2" && !state.plan);
  }
}

/**
 * 단계가 바뀔 때 — 'Wizard Steps' 에서 세 가지만 가져왔다.
 * 1) 앞 단계로 가면 새 화면이 오른쪽에서, 뒤로 가면 왼쪽에서 16px 들어온다. 어느 쪽으로
 *    움직였는지가 보인다. 나가는 화면은 기다리지 않는다(화면을 늦게 바꾸지 않는다).
 * 2) 화면 읽기 프로그램에 '4단계 중 2단계, 항목 검토' 를 알린다.
 * 3) 누른 단추가 새 화면에 없으면 초점을 새 화면으로 옮긴다 — 문서 맨 앞으로 튀지 않게.
 */
function stepChanged(prev, n) {
  const app = document.querySelector(".app");
  const all = $("stepper").querySelectorAll("[data-step]");
  // body 에도 data-step 이 있어서 "> .lb" 로 단추 바로 아래만 본다
  const lb = $("stepper").querySelector(`[data-step="${n}"] > .lb`);
  $("stepSay").textContent = `${all.length}단계 중 ${n}단계, ${lb ? lb.textContent : ""}`;
  if (!reduceMotion() && app.animate) {
    const d = n > prev ? 1 : -1;
    app.animate([{ opacity: 0, transform: `translateX(${d * 16}px)` }, { opacity: 1, transform: "none" }],
                { duration: 260, easing: "cubic-bezier(0.23, 1, 0.32, 1)" });
  }
  requestAnimationFrame(() => {
    const a = document.activeElement;
    if (a && a !== document.body && a.isConnected && a.getClientRects().length) return;
    app.focus({ preventScroll: true });
  });
}

/**
 * 지금 단계의 검은 원은 하나뿐이고, 단계가 바뀌면 그 원이 옆 번호로 미끄러진다
 * (21st.dev 'Steps' 의 sliding thumb). 처음 자리를 잡을 때는 움직이지 않는다.
 */
function placeThumb() {
  // 위 막대가 두 줄이라 키가 화면 폭마다 다르다 — 계획 화면의 고정 막대가 그 아래에 붙게 알린다.
  document.documentElement.style.setProperty("--topbar-h", `${document.querySelector(".topbar").offsetHeight}px`);
  const st = $("stepper");
  const no = st.querySelector("[aria-current] .no");
  if (!no) return;
  st.style.setProperty("--thumb-y", `${no.offsetTop}px`);
  stepThumb.to(no, { instant: placeThumb.resizing });
  st.dataset.ready = "1";
}
const stepThumb = stretchThumb($("stepper"));
window.addEventListener("resize", () => {
  placeThumb.resizing = true; placeThumb(); placeSegThumb(true); placeThumb.resizing = false;
});

$("stepper").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-step]");
  const n = btn && btn.dataset.step;
  if (state.busy || !btn) return;
  if (n === "1") showBlank();
  if (n === "2" && state.plan) showPlan();
});

function showBlank() {
  setStep(1);
  $("stageChips").innerHTML = "";
  // 진행 순서 안내는 두지 않는다 — 위쪽 단계 표시(1 기획서 · 2 항목 검토 …)와 같은 말이다.
  $("stage").innerHTML = "";
}

// 경과 시간. 몇 분 걸리는 실행에서 멈춘 것과 도는 것을 구별하게 한다.
let elapsedTimer = null;

function showProgress(title, lines) {
  setStep(title === "실행 중" ? 3 : 2);
  $("stageChips").innerHTML = `<span class="chip busy"><i class="dot"></i>실행 중</span>`;
  $("stage").innerHTML = `
    <div class="head"><h1>${esc(title)}</h1><span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
      <span class="elapsed" id="pElapsed">0초</span></div>
    <div class="pnow" id="pNow" aria-live="polite"></div>
    <progress id="pBar" class="sr" hidden></progress>
    <div class="pbar" id="pTrack" hidden aria-hidden="true"><i id="pFill"></i></div>
    <div class="ptally" id="pTally" hidden></div>
    ${title === "실행 중" ? `<button class="btn ghost" id="pStop" type="button" hidden>멈추기</button>` : ""}
    <div class="steps" id="pSteps">${planSteps(title)}</div>
    <details class="raw" id="pRaw"><summary>진행 로그 전체<span class="n" id="pLogN"></span></summary>
      <div class="logbox"><pre class="log" id="pLog" role="log" aria-live="polite"></pre>
        <button class="btn ghost log-jump" id="pLogJump" type="button" hidden></button></div></details>`;
  followLog();
  pushProgress(lines || []);
  clearInterval(elapsedTimer);
  const t0 = Date.now();
  elapsedTimer = setInterval(() => {
    const el = $("pElapsed");
    if (!el) { clearInterval(elapsedTimer); return; }  // 화면이 결과로 바뀌면 멈춘다
    el.textContent = `${Math.round((Date.now() - t0) / 1000)}초`;
  }, 1000);
}

/* ── 진행 로그 — 흘러 들어오는 글 ─────────────────────────────────────────
 * 21st.dev 'Response Stream' 에서 '도착하는 대로 덧붙인다(AsyncIterable)' 와 '멈춤·이어 보기' 만.
 * 서버가 보내온 줄 묶음을 받은 그대로 붙이고, 새 묶음만 잠깐 옅게 들어온다. 이미 다 온 글을
 * 한 글자·한 낱말씩 흘려 보이는 타자기·페이드 연출은 쓰지 않는다 — 읽기만 늦어진다.
 * 맨 아래를 보고 있으면 따라 내려가고, 위로 올려 읽는 중이면 끌어내리지 않는다. 그동안 온 줄 수를
 * '새 줄 n개 — 맨 아래로' 로 알려 준다. 접혀 있어도 머리줄의 줄 수가 늘어 일이 도는 것이 보인다. */
const atLogEnd = (log) => log.scrollHeight - log.scrollTop - log.clientHeight < 24;
// 가려진 줄이 있는 쪽 가장자리만 흐린다 — 21st.dev AI Thinking 의 위아래 흐림에서. 다 보이면 걸지 않는다.
function logEdges(log) {
  log.classList.toggle("cut-top", log.scrollTop > 2);
  log.classList.toggle("cut-bottom", log.scrollHeight - log.scrollTop - log.clientHeight > 2);
}

function followLog() {
  const log = $("pLog"), jump = $("pLogJump"), raw = $("pRaw");
  if (!log || !jump) return;
  // 바로 맨 아래로 간다. 부드럽게 굴리면 그사이 온 줄을 놓치고, 기다리게 할 이유도 없다(HIG Motion).
  const toEnd = () => { log.scrollTop = log.scrollHeight; jump.hidden = true; log.dataset.unseen = 0; logEdges(log); };
  jump.addEventListener("click", toEnd);
  log.addEventListener("scroll", () => {
    logEdges(log);
    if (atLogEnd(log)) { jump.hidden = true; log.dataset.unseen = 0; }
  }, { passive: true });
  raw.addEventListener("toggle", () => {
    if (raw.open) { log.scrollTop = log.scrollHeight; jump.hidden = true; logEdges(log); }
  });
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

/**
 * 진행 메시지를 단계로 접어서 보여준다.
 *
 * 파이프라인은 "S1 설계 문서 추출" 같은 머리줄과 그 아래 들여쓴 상세를 보낸다.
 * 날것으로 쏟으면 사람이 어디쯤인지 모른다 — 머리줄을 단계로, 들여쓴 줄을 그
 * 단계의 상세로 읽는다. 원문은 접힌 로그에 그대로 남긴다.
 */
function pushProgress(messages) {
  const log = $("pLog"), steps = $("pSteps");
  if (!log || !steps) return;
  appendLog(log, messages);

  for (const raw0 of messages) {
    // 지금까지의 판정 수 (nodes.run_cases 의 '집계' 줄). 단계 목록에 쌓지 않는다.
    const t = /집계 통과 (\d+) · 기획서와 다름 (\d+) · 실행 문제 (\d+)(?: · 확인 불가 (\d+))?/.exec(raw0);
    if (t) {
      const el = $("pTally");
      el.hidden = false;
      // 칸은 한 번 만들고 숫자만 바꾼다 — 바뀐 숫자만 밀어 올린다.
      if (!el.firstChild) {
        el.innerHTML = `<span class="ok">통과 <b data-k="ok"></b></span>` +
          `<span class="fail">기획서와 다름 <b data-k="fail"></b></span>` +
          `<span class="infra">실행 문제 <b data-k="infra"></b></span>` +
          `<span class="unv" hidden>확인 불가 <b data-k="unv"></b></span>`;
      }
      const k = (key) => el.querySelector(`[data-k="${key}"]`);
      swapNumber(k("ok"), t[1]);
      swapNumber(k("fail"), t[2]);
      swapNumber(k("infra"), t[3]);
      k("unv").parentElement.hidden = !(t[4] && t[4] !== "0");
      swapNumber(k("unv"), t[4] || "0");
      continue;
    }
    const raw = plainProgress(raw0);
    // 케이스 줄은 단계 목록에 쌓지 않고 '몇 건 중 몇 번째' 로 보인다. 원문은 로그에 남는다.
    const m = /케이스 (\d+)\/(\d+) · (.+)/.exec(raw);
    if (m) {
      $("pNow").textContent = `${m[2]}건 중 ${m[1]}번째 — ${m[3]}`;
      const bar = $("pBar");
      bar.hidden = false; bar.max = Number(m[2]); bar.value = Number(m[1]) - 1;
      bar.setAttribute("aria-valuetext", `${bar.max}건 중 ${bar.value}건 끝남`);
      // 보이는 막대는 따로 그린다 — <progress> 는 값이 바뀔 때 부드럽게 차오르지 않는다.
      $("pTrack").hidden = false;
      $("pFill").style.width = `${(bar.value / bar.max) * 100}%`;
      meterStep(steps.querySelector(".pstep.active"), bar.value / bar.max);
      // 다른 탭에 가 있어도 탭 이름에서 어디쯤인지 보이게 한다. 끝나면 renderChrome 이 되돌린다.
      document.title = `${bar.value}/${bar.max} 실행 중 — Prova`;
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
        // '!' 로 시작하는 줄은 주의 — 기호는 CSS 가 그리고, 읽어 주는 프로그램에는 '주의' 라고 알린다.
        if (/^!/.test(text)) {
          d.classList.add("warn");
          d.innerHTML = `<span class="sr">주의: </span>`;
          d.append(text.replace(/^!\s*/, ""));
        } else {
          d.textContent = text;
        }
        last.querySelector(".body").appendChild(d);
        continue;
      }
    }
    const prev = currentStep(steps);
    if (prev) doneStep(prev);
    const label = text.replace(/^S\d(~S\d)?\s+/, "");
    const key = (PLAN_STEPS.find(([, name]) => label.startsWith(name)) || [])[0];
    let el = key && steps.querySelector(`.pstep.todo[data-key="${key}"]`);
    if (el) {
      // 건너뛴 앞 단계(이미 만든 계획으로 바로 실행 등)는 지운다 — 남겨 두면 안 한 일이 '할 일'로 보인다.
      while (el.previousElementSibling && el.previousElementSibling.classList.contains("todo")) {
        el.previousElementSibling.remove();
      }
      el.classList.remove("todo");
    } else {
      el = document.createElement("div");
      steps.insertBefore(el, steps.querySelector(".pstep.todo"));
    }
    el.className = "pstep active";
    el.dataset.t0 = Date.now();
    // 지금 단계는 모양(도는 호·바탕)만이 아니라 글자로도 말한다 — HIG '색·모양만으로 전하지 않는다'.
    // 21st.dev AI Thought Chain 의 'In progress' 꼬리표에서. 끝나면 같은 자리가 걸린 시간이 된다.
    el.innerHTML = `<span class="mark">${STEP_MARK}</span>` +
      `<div class="body">${esc(label)}</div><span class="t">진행 중</span>`;
  }
}

/**
 * 앞으로 할 단계를 처음부터 깐다 — 21st.dev 'AI Planning' 에서 '계획 전체를 먼저 보이고
 * 하나씩 채운다' 만 가져왔다. 몇 단계 중 어디쯤이고 무엇이 남았는지가 처음부터 보인다.
 * 남은 단계는 빈 원과 흐린 글자, 시작되면 도는 호, 끝나면 체크와 걸린 시간.
 * 상태별 색·아이콘, 단계마다 접는 칸, 위에서 미끄러져 들어오는 등장은 쓰지 않는다
 * (색은 판정에만, HIG Motion). 이름은 PROGRESS_WORDS 가 바꾼 말과 같아야 켜진다.
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
    `<div class="pstep todo" data-key="${k}"><span class="mark">${STEP_MARK}</span>` +
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
  [/mock 백엔드로 실행합니다 — 설계 문서 추출에 실제 모델을 쓰지 않습니다\./, "연습용으로 실행합니다 — 기획서를 실제 모델로 읽지 않습니다."],
  [/^(\s*)S1 사람이 고친 추출 결과를 씁니다.*$/, "$1기획서 읽기 — 고친 내용을 씁니다"],
  [/^(\s*)S1 설계 문서 추출/, "$1기획서 읽기"],
  [/^(\s*)S2 테스트 케이스 생성/, "$1확인할 항목 만들기"],
  [/^(\s*)S3~S5 브라우저 실행 및 판정/, "$1브라우저로 하나씩 확인"],
  [/^(\s*)S6 리포트 생성/, "$1리포트 만들기"],
  [/화면 '(.+?)' · 요소 (\d+)개/, "'$1' 화면 · 입력칸·버튼 $2개"],
  [/케이스 (\d+)개 \(정상 (\d+) · 위반 (\d+)/, "항목 $1개 (정상 동작 $2 · 막혀야 하는 입력 $3"],
  [/승인 목록 → (\d+)개 실행/, "승인한 $1개를 실행합니다"],
];
function plainProgress(line) {
  for (const [re, to] of PROGRESS_WORDS) line = line.replace(re, to);
  return line;
}

/**
 * 단계 표시 — 도는 호, 끝나면 체크가 그려진다 (21st.dev 'Agent Todo List' 의 상태 표시).
 * 색은 쓰지 않는다. 끝난 단계는 '통과' 가 아니라 지나간 것이다 — 초록은 판정에만.
 */
const STEP_MARK = `<svg class="st" viewBox="0 0 20 20" aria-hidden="true">` +
  `<circle class="trk" cx="10" cy="10" r="7"/>` +
  `<circle class="arc" cx="10" cy="10" r="7" pathLength="100"/>` +
  `<path class="ok" d="M6.7 10.3l2.3 2.3 4.4-4.6" pathLength="1"/></svg>`;

/**
 * 셀 수 있는 단계(케이스를 하나씩 도는 단계)는 도는 호 대신 끝난 만큼 찬 원을 그린다.
 * 21st.dev Circle Progress 에서 '값만큼 차오르는 원'만 가져왔다 — 채운 비율에 따라 색이
 * 바뀌는 부분과 그라데이션은 버렸다. 진행은 좋고 나쁨이 아니고, 색은 판정에만 쓴다.
 * 첫 케이스가 끝나기 전에는 도는 호를 그대로 둔다 — 멈춘 것처럼 보이지 않게.
 * 끝나면(doneStep) 원이 마저 차고 체크가 그려진다.
 */
function meterStep(el, ratio) {
  if (!el || !(ratio > 0)) return;
  el.classList.add("metered");
  el.style.setProperty("--left", (100 - Math.min(Math.max(ratio, 0), 1) * 100).toFixed(2));
}

// 끝난 단계에 걸린 시간을 오른쪽에 적는다 — 1초 넘게 걸린 단계만.
function doneStep(el) {
  if (!el.classList.contains("active")) return;
  el.classList.remove("active");
  el.classList.add("done");
  const sec = Math.round((Date.now() - Number(el.dataset.t0 || Date.now())) / 1000);
  const t = el.querySelector(".t");
  if (t) t.textContent = sec >= 1 ? `${sec}초` : "";
}

function finishProgress() {
  const last = $("pSteps") && currentStep($("pSteps"));
  if (last) doneStep(last);
}

function showError(title, message) {
  setStep(1);
  $("stageChips").innerHTML = "";
  $("stage").innerHTML = alertBox("fail", esc(title), esc(message));
}

// ── 계획 확인 ──────────────────────────────────────────────────────────────

function screenName(id) {
  return (state.plan.screens && state.plan.screens[id]) || id || "기타";
}

function visibleCases() {
  const q = state.filter.trim().toLowerCase();
  return state.plan.cases.filter((c) => {
    if (state.onlyOff && c.selected) return false;
    if (!q) return true;
    return (c.case_id + " " + c.title + " " + (c.violates || "") + " " +
            screenName(c.screen_id)).toLowerCase().includes(q);
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
  if (p.url_note) out.push(alertBox("info", "대상 URL 을 고쳤습니다", esc(p.url_note)));

  // 기획↔디자인 불일치 — 케이스를 승인하기 전에 봐야 한다. 구현을 검증하기
  // 전에 입력끼리 모순이면 그것부터 정리하는 것이 순서다 (s1_merge).
  if ((p.design_mismatches || []).length) {
    out.push(alertBox("warn",
      `기획↔디자인 불일치 ${p.design_mismatches.length}건`,
      "구현을 고치기 전에 두 입력 중 어느 쪽이 맞는지부터 정해야 합니다. " +
      "어긋난 항목은 판정에서 빠집니다." +
      p.design_mismatches.map((m) => `<div style="margin-top:6px">${esc(m)}</div>`).join("")));
  }

  if (p.fallback) {
    out.push(alertBox("warn", "요청을 해석하지 못해 전체 케이스를 골랐습니다",
      "해석 실패는 적게 검사하는 쪽이 아니라 많이 검사하는 쪽으로 넘어집니다 — " +
      "적게 고르면 결함이 숨지만 많이 고르면 숨지 않습니다." +
      (p.warnings || []).map((w) => `<div style="margin-top:6px">${esc(w)}</div>`).join("")));
  } else {
    if (p.request && p.reason) {
      out.push(alertBox("info", "이렇게 이해했습니다", esc(p.reason)));
    }
    for (const w of p.warnings || []) out.push(alertBox("warn", esc(w), ""));
    if ((p.widened || []).length) {
      // 모델이 고른 것과 코드가 더한 것을 구분해 보인다 (selector.widen_selection).
      out.push(alertBox("info", `도구가 넓힌 케이스 ${p.widened.length}건`,
        "모델이 가리킨 묶음(건수·정렬·흐름 등)을 코드가 채웠습니다: " + esc(p.widened.join(", "))));
    }
  }

  // 요청이 화면을 이름으로 지목했는데 일부만 골라진 경우. "몇 건 제외" 만
  // 보면 그 화면을 확인했다고 읽힌다 — 실측에서 "회원가입이 잘 되는지" 에
  // 17건 중 6건만 골라지는 것이 프롬프트로는 안 고쳐졌고, 이 경고가 그 남은
  // 구멍의 방어선이다. 사람이 체크를 바꾸면 함께 갱신된다.
  for (const c of liveCoverage()) {
    if (c.named && c.selected > 0 && c.selected < c.total) {
      out.push(alertBox("warn",
        `'${esc(c.name)}' 화면은 ${c.total}건 중 ${c.selected}건만 실행됩니다`,
        `요청이 이 화면을 가리켰지만 일부만 골라졌습니다. 이대로 실행하면 ` +
        `이 화면의 통과율은 <b>화면 전체의 상태를 뜻하지 않습니다.</b> ` +
        `화면 그룹의 [모두 켜기]로 전부 확인할 수 있습니다.`));
    }
  }

  const off = p.cases.filter((c) => !c.selected).length;
  if (off) {
    out.push(alertBox("info", `이번 실행에서 ${off}건을 제외합니다`,
      "<b>통과한 것이 아니라 확인하지 않는 것</b>입니다. 빠지면 안 되는 것이 있으면 " +
      "아래에서 도로 켜 주세요."));
  }

  if ((p.coverage_gaps || []).length) {
    out.push(alertBox("warn",
      `기획서에 있으나 케이스가 없는 항목 ${p.coverage_gaps.length}건`,
      p.coverage_gaps.map((g) => esc(g)).join("<br>")));
  }
  return out.join("");
}

function showPlan() {
  setStep(2);
  const p = state.plan;
  $("stageChips").innerHTML =
    `<span class="chip">생성 ${p.total_generated}건</span>`;

  $("stage").innerHTML = `
    <div class="head">
      <h1>계획 확인</h1>
      <div class="sub">${p.request
        ? `요청 — ${esc(p.request)}`
        : "요청이 없어 전체 케이스를 골랐습니다"}</div>
    </div>
    <div id="planNotes"></div>
    <details class="spec" id="specPanel"></details>
    <div class="toolbar">
      <div class="count" id="count"></div>
      <button class="btn ghost quiet" id="allBtn" type="button">모두 켜기</button>
      <button class="btn ghost quiet" id="offBtn" type="button" aria-pressed="false">꺼 둔 것만 보기</button>
      <label class="search">
        ${ICON.search}
        <span class="sr">케이스 검색</span>
        <input type="text" id="q" placeholder="케이스 검색" spellcheck="false">
      </label>
      <button class="btn ghost" id="backBtn" type="button">요청 고치기</button>
      <button class="btn primary" id="runBtn" type="button">이대로 실행</button>
      <span class="hint" id="runHint"></span>
    </div>
    <div id="groups"></div>`;

  $("q").addEventListener("input", (e) => {
    state.filter = e.target.value;
    renderGroups();
  });
  $("allBtn").addEventListener("click", () => {
    p.cases.forEach((c) => { c.selected = true; });
    renderPlanBody();
  });
  $("offBtn").addEventListener("click", (e) => {
    state.onlyOff = !state.onlyOff;
    e.currentTarget.setAttribute("aria-pressed", String(state.onlyOff));
    renderGroups();
  });
  $("backBtn").addEventListener("click", () => {
    state.plan = null;
    showBlank();
    renderChrome();
    $("request").focus();
  });
  $("runBtn").addEventListener("click", startRun);
  $("groups").addEventListener("click", onCite);

  state.draft = JSON.parse(JSON.stringify(p.doc || { screens: [] }));
  state.dirty = false;
  renderSpec();
  renderPlanBody();
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
  const head = `<summary><b>기획서에서 읽은 내용</b>
    <span class="hint">${edits.length
      ? `사람이 고친 값 ${edits.length}건으로 만든 케이스입니다`
      : "잘못 읽은 칸이 있으면 기획서 문구 그대로 고친 뒤, 아래 '고친 내용으로 항목 다시 만들기' 를 누르세요"}</span></summary>`;
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
    return `<section class="group spec-screen">
      <header><h3>${esc(sc.screen_name)}</h3></header>
      <div class="spec-metas">${meta}</div>
      <div class="spec-scroll"><table class="spec-table">
        <thead><tr><th>종류</th>${EL_FIELDS.map(([, n]) => `<th>${n}</th>`).join("")}<th></th></tr></thead>
        <tbody>${rows}</tbody></table></div>
    </section>`;
  }).join("");
  const list = edits.length
    ? `<ul class="spec-edits">${edits.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>` : "";
  $("specPanel").innerHTML = head + list + screens + `
    <div class="runbar"><button class="btn ghost" id="replanBtn" type="button" disabled>
      고친 내용으로 항목 다시 만들기</button>
      <span class="hint" id="specHint">칸을 고치면 누를 수 있습니다</span></div>`;
  if (edits.length) $("specPanel").open = true;

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

// 고친 뒤 다시 만들지 않고 실행하면 화면의 케이스와 문서가 어긋난다 — 실행을 막는다.
function markDirty() {
  state.dirty = true;
  $("replanBtn").disabled = false;
  $("specHint").textContent = "고친 내용은 이 버튼을 눌러야 항목에 반영됩니다";
  renderCount();
}

function draftDoc() {
  const d = JSON.parse(JSON.stringify(state.draft));
  for (const sc of d.screens) {
    sc.elements = sc.elements.filter((e) => !e._removed);
  }
  return d;
}

async function replan() {
  const doc = draftDoc();
  showProgress("고친 내용으로 케이스를 다시 만드는 중", []);
  state.busy = true;
  renderChrome();
  try {
    const { job_id } = await api("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...form(), doc }),
    });
    state.plan = await follow(job_id, pushProgress);
    state.filter = ""; state.onlyOff = false;
    showPlan();
  } catch (err) {
    showError("케이스를 다시 만들지 못했습니다", err.message);
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
        : `<li class="fm-edge" data-via="url" title="주소로 바로 들어갑니다 — 화면을 잇는 버튼·링크는 확인하지 않습니다"><span>주소로 이동</span></li>`);
    }
    parts.push(`<li class="fm-node"><b>${esc(screenName(sid))}</b>` +
      (path(sid) ? `<code>${esc(path(sid))}</code>` : "") + `</li>`);
  });
  return `<ol class="flowmap" aria-label="화면 흐름">${parts.join("")}</ol>`;
}

function renderPlanBody() {
  $("planNotes").innerHTML = planNotes();
  renderGroups();
  renderCount();
}

function renderGroups() {
  const shown = visibleCases();
  if (!shown.length) {
    $("groups").innerHTML =
      `<div class="empty-line">조건에 맞는 케이스가 없습니다.</div>`;
    return;
  }

  // 화면별로 묶는다. multi_spec 은 케이스가 39개라 한 덩어리면 벽이 된다.
  const order = [];
  const byScreen = new Map();
  for (const c of shown) {
    const key = c.flow_id ? `flow:${c.flow_id}` : c.screen_id;
    if (!byScreen.has(key)) { byScreen.set(key, []); order.push(key); }
    byScreen.get(key).push(c);
  }

  $("groups").innerHTML = order.map((key) => {
    const list = byScreen.get(key);
    const title = key.startsWith("flow:")
      ? `흐름 <code class="fid">${esc(key.slice(5))}</code>` : esc(screenName(key));
    const flow = key.startsWith("flow:") &&
      ((state.plan.doc && state.plan.doc.flows) || []).find((f) => f.flow_id === key.slice(5));
    const on = list.filter((c) => c.selected).length;
    return `<section class="group">
      <header>
        <h3>${title}</h3>
        <span class="n">${on}/${list.length}</span>
        <button class="btn ghost quiet" data-group="${esc(key)}" type="button">
          ${on === list.length ? "모두 끄기" : "모두 켜기"}</button>
      </header>
      ${flow && flow.screen_ids.length > 1 ? flowMap(flow) : ""}
      ${byTarget(list)}
    </section>`;
  }).join("");

  $("groups").querySelectorAll("[data-group]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const list = byScreen.get(btn.dataset.group);
      const turnOn = list.some((c) => !c.selected);
      list.forEach((c) => { c.selected = turnOn; });
      renderPlanBody();
    });
  });

  fluidHover($("groups"), ".case");
  const bar = document.querySelector(".toolbar");
  if (bar) document.documentElement.style.setProperty("--toolbar-h", `${bar.offsetHeight}px`);

  $("groups").querySelectorAll(".case").forEach((row) => {
    row.querySelector("input").addEventListener("change", (e) => {
      const box = e.target;
      const c = state.plan.cases.find((x) => x.case_id === row.dataset.id);
      c.selected = box.checked;
      row.classList.toggle("off", !c.selected);
      // 안내와 개수가 사람의 조작을 따라와야 한다. 가장 중요한 안내가
      // 따라오지 않으면 확인 단계가 형식만 남는다.
      $("planNotes").innerHTML = planNotes();
      renderCount();
      row.closest(".group").querySelector(".n").textContent = groupCount(row);
    });
  });
}

// 화면 안에서 기획서 항목(이메일·비밀번호…)별로 한 번 더 묶는다 — 기획서 표와 나란히 대조하기 쉽다.
function byTarget(list) {
  const by = new Map();
  for (const c of list) {
    const k = c.target_label || "";
    if (!by.has(k)) by.set(k, []);
    by.get(k).push(c);
  }
  if (by.size < 2) return list.map((c) => caseRow(c)).join("");
  return [...by].map(([k, cs]) =>
    `<div class="subhead">${esc(k || "화면 전체")}<span>${cs.length}</span></div>` +
    cs.map((c) => caseRow(c, true)).join("")).join("");
}

function groupCount(row) {
  const rows = [...row.closest(".group").querySelectorAll(".case")];
  const on = rows.filter((r) => r.querySelector("input").checked).length;
  return `${on}/${rows.length}`;
}

// 사람이 읽는 제목을 먼저, 내부 id 는 작게 뒤로. 스크린 리더도 제목을 읽는다.
// grouped: 항목 머리줄 아래에 놓인 줄 — 꼬리표에 항목 이름을 되풀이하지 않는다.
// 제목을 누르면 절차·기대가 펼쳐진다 — 줄마다 '절차·기대 보기' 를 되풀이하지 않는다.
// 선택은 체크박스로만 바꾼다. 읽으려고 누른 것이 케이스를 끄면 안 된다.
function caseRow(c, grouped) {
  const tags =
    (c.violates ? `<span class="tag rule" title="${esc(c.violates)}">${
      esc([grouped ? "" : c.target_label, c.rule_label || c.violates].filter(Boolean).join(" · "))}</span>` : "") +
    (c.flow_id ? `<span class="tag flow">흐름</span>` : "");
  const head = `<span class="desc">${esc(c.title)}</span>${tags}`;
  return `<div class="case ${c.selected ? "" : "off"}" data-id="${esc(c.case_id)}">
    <input type="checkbox" ${c.selected ? "checked" : ""}
           aria-label="${esc(c.title)} 실행">
    ${caseHow(c, head) || `<div class="line">${head}</div>`}
  </div>`;
}

// 무슨 값을 넣고 무엇을 기대하는지. 제목만 보고 승인하지 않게 한다 (prova/wording.py).
function caseHow(c, head) {
  if (!(c.steps || []).length && !c.expected) return "";
  const src = (c.sources || []).map(readSource);
  const id = `src-${c.case_id}`;
  return `<details class="how">
    <summary class="line">${head}</summary>
    <ol>${(c.steps || []).map((s) => `<li>${esc(s.replace(/^(준비 )?\d+\. /, "$1"))}</li>`).join("")}</ol>
    ${c.expected ? `<div class="expect"><b>기대</b> <span>${citedExpect(c.expected, src, id)}</span></div>` : ""}
    ${src.length ? `<div class="srcs" id="${esc(id)}">
      <button type="button" class="srcs-btn" aria-expanded="false" aria-controls="${esc(id)}-list">
        <b>기획서 근거</b> ${src.length}곳</button>
      <div class="srcs-list" id="${esc(id)}-list"><div>${src.map((s, i) =>
        `<p data-i="${i}"><b>${s.page ? `${s.page}쪽 ${s.kind}` : "기획서"}</b> ${esc(s.quote)}</p>`).join("")}</div></div>
    </div>` : ""}
    <div class="expect src"><b>케이스 번호</b> ${esc(c.case_id)}</div>
  </details>`;
}

/* ── 기획서 근거를 그 말이 나온 자리에 ─────────────────────────────────────
 * 21st.dev Streaming Text 에서 '문장 안의 출처 칩' 과 '출처 목록이 펼쳐진다' 만 가져왔다.
 * 기대 문장의 따옴표 값('가입이 완료되었습니다')이 기획서 원문에 있으면 그 값이 든 마디 끝에
 * '2쪽' 칩을 붙인다. 못 찾은 근거는 문장 끝에 붙는다. 칩을 누르면 아래 근거 목록이 펼쳐지고
 * 그 칩의 원문만 진해진다. 낱말이 하나씩 흐려졌다 나타나는 효과는 버렸다 — Prova 의 문장은 이미
 * 다 만들어진 것이라 흘려 보여 주면 읽기만 늦어진다. 아바타·후속 질문·좋아요 버튼도 버렸다. */
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
      `<button type="button" class="cite" data-src="${idx.join(" ")}" aria-controls="${esc(id)}-list"
         aria-expanded="false" title="기획서 원문 보기">${label}<span class="sr"> 기획서 원문 보기</span></button>`;
    last = pos;
  }
  return html + esc(expected.slice(last));
}

// 칩은 목록을 펼치고 제 원문만 진하게 한다. 같은 칩을 다시 누르면 접는다. 목록 머리줄은 그냥 펼치고 접는다.
function onCite(e) {
  const btn = e.target.closest(".cite, .srcs-btn");
  if (!btn) return;
  const how = btn.closest(".how"), box = how && how.querySelector(".srcs");
  if (!box) return;
  const chip = btn.classList.contains("cite");
  const same = chip && btn.classList.contains("on");
  const open = chip ? !same || !box.classList.contains("open") : !box.classList.contains("open");
  const on = new Set(chip && open ? btn.dataset.src.split(" ") : []);
  box.classList.toggle("open", open);
  box.classList.toggle("picked", on.size > 0);
  box.querySelectorAll(".srcs-list p").forEach((p) => p.classList.toggle("on", on.has(p.dataset.i)));
  how.querySelectorAll(".cite").forEach((c) => {
    c.classList.toggle("on", open && c === btn);
    c.setAttribute("aria-expanded", String(open));
  });
  box.querySelector(".srcs-btn").setAttribute("aria-expanded", String(open));
}

function picked() {
  return state.plan.cases.filter((c) => c.selected).map((c) => c.case_id);
}

function renderCount() {
  const n = picked().length, all = state.plan.cases.length;
  $("count").innerHTML =
    `<b>${n}</b>건 실행 <span class="off">· ${all - n}건 제외</span>`;
  // 0건 실행은 "전체 0건, 통과율 100%" 리포트가 된다. 누를 수 없게 막는다.
  const run = $("runBtn");
  run.disabled = n === 0 || state.dirty;
  $("runHint").textContent = n === 0
    ? "0건은 실행할 수 없습니다 — 통과율 100% 리포트가 됩니다"
    : state.dirty ? "기획서 내용을 고쳤습니다 — 먼저 [다시 만들기]" : "";
}

// ── 실행 ───────────────────────────────────────────────────────────────────

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
        busyButton(stop, "지금 항목이 끝나면 멈춥니다");
        try { await api(`/api/job/${job_id}/cancel`, { method: "POST" }); } catch (e) { /* 이미 끝났다 */ }
      };
    }
    const out = await follow(job_id, pushProgress);
    finishProgress();
    state.result = out;
    showResult(out);
    loadRuns();
  } catch (err) {
    if (err.status === 409) {
      // 409 는 셋이다 — 이미 실행 중, 대상 빌드가 낡음, 2차 경로 서버 없음.
      // 이유는 서버가 말한다. 한 문구로 뭉치면 낡은 대상을 '실행 중' 으로 안내한다.
      showError("실행을 시작하지 않았습니다", err.message);
    } else if (err.message.startsWith("실행을 멈췄습니다")) {
      showError("실행을 멈췄습니다", "같은 항목으로 다시 돌리려면 위의 '2 항목 검토' 를 누르세요.");
    } else {
      showError("실행 실패", err.message);
    }
  } finally {
    state.busy = false;
    renderChrome();
  }
}

function showResult(out) {
  setStep(4);
  const s = out.summary;
  const planned = state.plan ? state.plan.cases.length : s.total;
  const off = planned - s.total;

  // 실패를 결함(기획서와 다름, 빨강)과 실행 문제(도구·환경, 보라)로 가른다.
  // defects 가 없는 옛 리포트는 실패를 전부 결함으로 읽던 예전 모양 그대로 둔다.
  // 확인 불가는 결함도 실행 문제도 아니다(요구서 4절 2번) — 따로 센다.
  const defects = s.defects ?? s.fail;
  const unv = s.unverifiable || 0;
  const infra = s.fail - defects - unv;
  $("stageChips").innerHTML =
    `<span class="chip ${defects ? "fail" : infra ? "infra" : unv ? "unv" : "ok"}"><i class="dot"></i>` +
    `${defects ? `기획서와 다름 ${defects}건` : infra ? `실행 문제 ${infra}건` : unv ? `확인 불가 ${unv}건` : "전부 통과"}</span>`;

  const notes = [];
  if (off > 0) {
    notes.push(alertBox("info", "이 통과율은 전체 상태가 아닙니다",
      `생성된 ${planned}건 중 ${s.total}건만 실행했습니다. 나머지 ${off}건은 ` +
      `<b>통과한 것이 아니라 확인하지 않은 것</b>입니다.`));
  }
  if (s.vlm) {
    notes.push(alertBox("info", "화면 이미지로 찾기를 켜고 실행했습니다",
      `라벨로 못 찾은 요소를 화면 이미지로 찾았습니다 (${esc(s.vlm)}) — ` +
      `보정한 케이스 ${s.healed || 0}건. 보정한 케이스는 리포트에 따로 표시됩니다.`));
  }
  if (s.not_found_without_vlm) {
    // 끈 실행은 필요한 상황이 와도 스스로 켜지지 않는다 — 다시 돌려 볼 만하다는 것을 알린다.
    notes.push(alertBox("info", `요소를 찾지 못한 케이스 ${s.not_found_without_vlm}건`,
      `화면 이미지로 찾기를 켜지 않은 실행입니다. 스크린샷에 그 요소가 보이는데 못 찾았다면 ` +
      `<b>실행 옵션의 '화면 이미지로 찾기' 를 켜서 다시 돌려 보세요</b> (모델 서버 필요). ` +
      `스크린샷에도 없다면 구현이 빠뜨린 것일 수 있고, 켜도 달라지지 않습니다.`));
  }
  if (s.dry_run) {
    // 확인 불가도 실패 칸에 센다(확인하지 못한 것을 통과로 세지 않는다). 그 실패의 성질을 바로 말한다.
    const d = s.dry_run;
    notes.push(alertBox("warn", "쓰기 요청을 막고 실행했습니다",
      `막은 케이스 ${d.cases_blocked || 0}건은 서버 응답을 못 봐 '확인 불가' 로 실패에 셉니다 — ` +
      `<b>구현 결함이 아닙니다.</b> 막지 않은 ${s.total - (d.cases_blocked || 0)}건 중 통과 ${s.pass}. ` +
      `${esc(d.limits || "")}`));
  }
  if (s.llm_backend === "mock") {
    notes.push(alertBox("warn", "연습용으로 실행한 결과입니다",
      "기획서를 실제 모델로 읽지 않았습니다. 실제 검증 결과로 쓰지 마세요."));
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
  const api = `/api/report/${encodeURIComponent(runId)}`;

  $("stage").innerHTML = `
    <div class="head result-head">
      <div>
      <h1>${defects
        ? `${s.total}건 중 <mark class="fail">${defects}건이 기획서와 다릅니다.</mark>`
        : infra
        ? `${s.total}건 중 <mark class="infra">${infra}건을 실행 문제로 확인하지 못했습니다.</mark>`
        : unv
        ? `${s.total}건 중 <mark class="unv">${unv}건은 판정할 근거가 없습니다.</mark>`
        : `<mark class="pass">${s.total}건 모두 통과했습니다.</mark>`}</h1>
      ${cond ? `<div class="cond">${esc(cond)}</div>` : ""}
      </div>
      <div class="actions">
        <a class="btn primary" href="${esc(base)}report.xlsx" download>엑셀 받기</a>
        <a class="btn ghost" href="${esc(api)}/pdf" download>PDF 받기</a>
        <a class="btn ghost" href="${esc(out.report_url)}" target="_blank" rel="noopener">리포트 파일 열기</a>
        ${state.plan ? `<button class="btn ghost" id="againBtn" type="button">다시 실행</button>` : ""}
      </div>
    </div>
    ${notes.join("")}
    <div class="result-chart">
      ${donutBlock({ defect: defects, infra, unv, pass: s.pass })}
      <dl class="sumstrip">
        <div class="f${defects ? " hot" : ""}" data-k="defect"><dt>기획서와 다름</dt><dd>${defects}</dd></div>
        <div class="x${infra ? " hot" : ""}" data-k="infra"><dt>실행 문제</dt><dd>${infra}</dd></div>
        ${unv ? `<div class="u" data-k="unv"><dt>확인 불가</dt><dd>${unv}</dd></div>` : ""}
        <div class="p" data-k="pass"><dt>통과</dt><dd>${s.pass}</dd></div>
        <div class="r" data-k="pass"><dt>통과율</dt><dd>${s.pass_rate}%</dd></div>
      </dl>
    </div>
    <div class="reportbox">
      <iframe id="reportFrame" src="${esc(out.report_url)}" title="검증 리포트" scrolling="no"
              allow="clipboard-write"></iframe>
    </div>`;
  // 같은 항목·같은 옵션으로 한 번 더 — 고친 뒤 확인할 때 1·2단계를 다시 밟지 않는다.
  const again = $("againBtn");
  if (again) again.addEventListener("click", startRun);
  $("stage").querySelectorAll(".sumstrip dd").forEach(rollIn);
  linkDonut($("stage").querySelector(".result-chart"));
  fitFrame($("stage").querySelector("iframe"));
}

// ── 원형차트(도넛) ────────────────────────────────────────────────────────
// 리포트 파일의 도넛(report_builder._donut_svg)과 같은 그림이다 — 결함 → 실행 문제 →
// 확인 불가 → 통과, 12시에서 시계 방향. 이름표는 옆의 숫자 칸(sumstrip)이 맡는다 —
// 색만으로 말하지 않는다. 알림 상자 아래에 둔다 — 알림이 숫자보다 눈에 덜 띄면 안 된다(요구서 4절 1번).
//
// 21st.dev Donut Chart 에서 가져온 것: 12시부터 한 번에 그려지는 것, 조각이나 숫자 칸에
// 올리면 서로 짚고 가운데 글자가 그 조각의 수·비율로 바뀌는 것. 버린 것: 빛 번짐·커짐,
// 조각마다 따로 늦게 나타나기, 이름표가 하나씩 미끄러져 들어오기, 그림자 카드.
const DONUT_LABELS = { defect: "기획서와 다름", infra: "실행 문제", unv: "확인 불가", pass: "통과" };
let donutSeq = 0;

function donutBlock(n) {
  const keys = Object.keys(DONUT_LABELS).filter((k) => n[k] > 0);
  const total = keys.reduce((a, k) => a + n[k], 0);
  if (!total) return "";
  const size = 132, c = size / 2, w = 16, r = c - w / 2 - 1, len = 2 * Math.PI * r;
  const gap = keys.length > 1 ? 2 : 0;
  const pct = (k) => `${Math.round((n[k] / total) * 100)}%`;
  const id = `donutSweep${++donutSeq}`;
  let off = 0;
  const arcs = keys.map((k) => {
    const arc = (n[k] / total) * len, drawn = Math.max(arc - gap, 0.5);
    const el = `<circle class="seg ${k}" data-k="${k}" data-n="${n[k]}" data-pct="${pct(k)}" cx="${c}" cy="${c}" r="${r}" fill="none" stroke-width="${w}"
      stroke-dasharray="${drawn.toFixed(2)} ${(len - drawn).toFixed(2)}" stroke-dashoffset="${(-off).toFixed(2)}">
      <title>${DONUT_LABELS[k]} ${n[k]}건 (${pct(k)})</title></circle>`;
    off += arc;
    return el;
  }).join("");
  const aria = keys.map((k) => `${DONUT_LABELS[k]} ${n[k]}건`).join(", ");
  return `
    <div class="donut" data-total="${total}">
      <svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" role="img" aria-label="전체 ${total}건 — ${aria}">
        <mask id="${id}" class="sweep-mask"><circle class="sweep" cx="${c}" cy="${c}" r="${r}" fill="none"
          stroke-width="${w + 4}" pathLength="100"/></mask>
        <circle class="track" cx="${c}" cy="${c}" r="${r}" fill="none" stroke-width="${w}"/>
        <g transform="rotate(-90 ${c} ${c})" mask="url(#${id})">${arcs}</g>
        <text x="${c}" y="${c + 4}" class="big">${total}</text>
        <text x="${c}" y="${c + 22}" class="small">케이스</text>
      </svg>
    </div>`;
}

/**
 * 조각 ↔ 숫자 칸을 잇는다. 어느 쪽에 올려도 그 조각과 칸만 진하고, 가운데가 '16 / 41%' 로
 * 바뀐다. 0건인 칸은 조각이 없으니 잇지 않는다. 글자는 모두 화면에 이미 있으니 마우스용 덧붙임이다.
 */
function linkDonut(root) {
  const donut = root && root.querySelector(".donut");
  if (!donut) return;
  const big = donut.querySelector(".big"), small = donut.querySelector(".small");
  const has = new Set([...donut.querySelectorAll(".seg")].map((e) => e.dataset.k));
  let on = "";
  const show = (k) => {
    k = has.has(k) ? k : "";
    if (k === on) return;
    on = k;
    if (k) root.dataset.on = k; else delete root.dataset.on;
    const seg = k && donut.querySelector(`.seg[data-k="${k}"]`);
    big.textContent = seg ? seg.dataset.n : donut.dataset.total;
    // 이름은 옆에서 진해진 숫자 칸이 말한다 — 가운데는 수와 비율만(구멍에 들어가는 길이).
    small.textContent = seg ? seg.dataset.pct : "케이스";
    if (!reduceMotion() && big.animate) {
      for (const t of [big, small]) t.animate([{ opacity: 0.25 }, { opacity: 1 }], { duration: 160, easing: "ease-out" });
    }
  };
  root.addEventListener("pointerover", (e) => {
    const hit = e.target.closest(".seg, .sumstrip > div");
    show(hit ? hit.dataset.k : "");
  });
  root.addEventListener("pointerleave", () => show(""));
}

// 화면 모드는 OS 설정만 따른다 — Apple HIG Dark Mode: 앱 안에 밝게/어둡게 설정을 따로 두면
// 사람이 두 곳을 맞춰야 하고, OS 를 바꿨는데 이 화면만 안 바뀌면 고장 난 줄 안다.
// 리포트(iframe)도 같은 OS 설정을 따르므로 따로 맞출 것이 없다.

/**
 * 리포트 틀의 높이를 내용에 맞춘다 — 틀 안에 스크롤이 또 생기면 페이지 스크롤과 겹쳐
 * 어디를 굴려야 할지 헷갈린다. 펼침·접기로 높이가 바뀌어도 따라간다 (같은 출처라 읽을 수 있다).
 */
function fitFrame(frame) {
  frame.addEventListener("load", () => {
    const doc = frame.contentDocument;
    if (!doc) return;
    const fit = () => { frame.style.height = doc.documentElement.scrollHeight + "px"; };
    new ResizeObserver(fit).observe(doc.body);
    fit();
  });
}

// ── 계획 만들기 ────────────────────────────────────────────────────────────

$("planBtn").addEventListener("click", async () => {
  saveSettings();
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
    state.filter = ""; state.onlyOff = false;
    showPlan();
  } catch (err) {
    if (err.status === 409) {
      showError("이미 실행 중입니다", "지금 도는 작업이 끝난 뒤 다시 눌러 주세요.");
    } else {
      showError("계획을 만들지 못했습니다", err.message);
    }
  } finally {
    state.busy = false;
    $("planBtn").disabled = false;
    renderChrome();
  }
});

// ── 실행 기록 ──────────────────────────────────────────────────────────────

/**
 * 기록 한 줄의 이름.
 *
 * 기획서 이름만 쓰면 같은 기획서를 반복해서 돌린 목록이 전부 똑같아 보인다 —
 * 실제로 그랬다. 사람이 구분하는 기준은 '어느 화면을 어느 구현으로' 이므로
 * 기획서와 변형(good/bad)을 함께 쓴다.
 */
function runLabel(r) {
  return r.spec || r.run_id;
}

/** 어디를 검사했는지 — 주소에서 http:// 를 뺀 것. 같은 기획서를 다른 구현에 돌린 것을 가른다. */
function runTarget(r) {
  return (r.target || "").replace(/^https?:\/\//, "");
}

/** 언제 돌렸는지. 같은 대상을 여러 번 돌리면 이것만이 구분점이 된다. */
function runWhen(r) {
  const t = r.created_at || "";
  const m = /(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(t);
  return m ? `${m[2]}-${m[3]} ${m[4]}:${m[5]}` : r.run_id;
}

// 묶음마다 처음에 보이는 기록 수. 나머지는 '더 보기' 안에 둔다 — 목록 칸을 잘라 스크롤시키면
// 마지막 줄이 반쯤 가려진다.
const RUNS_SHOWN = 5;

/** 결과 한마디 — 결과 화면과 같은 말(기획서와 다름 · 실행 문제)을 쓴다. */
function runScore(r) {
  const defects = (r.summary && r.summary.defects) ?? r.fail;
  const unv = (r.summary && r.summary.unverifiable) || 0;
  const infra = r.fail - defects - unv;
  if (defects) return `<span class="score fail">기획서와 다름 ${defects}</span>`;
  if (infra) return `<span class="score infra">실행 문제 ${infra}</span>`;
  if (unv) return `<span class="score unv">확인 불가 ${unv}</span>`;
  return `<span class="score pass">전부 통과</span>`;
}

/**
 * 통과 못 한 케이스가 어느 화면에서 났는지 — 많은 순으로. 흐름 케이스는 '흐름' 하나로 묶는다.
 *
 * 21st.dev Animated Card Diagram 에서 '요약이 비켜나고 그 요약을 이루는 것들이 들어온다'
 * 만 가져왔다. 줄에 올리거나 키보드로 오면 둘째 줄(대상·차수·때)이 위로 빠지고 이 줄이
 * 들어온다 — 오른쪽 '기획서와 다름 16' 과 나란히 읽힌다. 빛 번짐·격자·확대·유리 칩은 버렸다.
 * 화면 읽기 프로그램에는 늘 읽힌다.
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
  return `<span class="where"><span class="sr">통과 못 한 곳: </span>` +
    parts.map(([n, c]) => `${esc(n)} <b>${c}</b>`).join(`<i aria-hidden="true"> · </i>`) + `</span>`;
}

async function loadRuns() {
  // 비어 있는 것과 아직 안 온 것을 구분해 준다. 빈 칸만 보이면 사람은
  // 기록이 없는 줄 안다.
  if (!$("runs").children.length) {
    $("runs").innerHTML = `<div class="empty-line">불러오는 중…</div>`;
  }
  try {
    state.runs = (await api("/api/runs?limit=60")).runs;
  } catch (e) {
    $("runs").innerHTML = `<div class="empty-line">기록을 불러오지 못했습니다.</div>`;
    return;
  }
  // 방금 새 이름으로 돌렸으면 그 이름도 이제 고를 수 있는 프로젝트다.
  const ran = state.runs.map((r) => r.project || "").filter(Boolean);
  renderProjects([...new Set([...(state.projects || []), ...ran])].sort());
  renderRuns();
}

/**
 * 실행 기록을 프로젝트별로 묶어 그린다.
 *
 * 최신순 한 줄 목록에서는 'A사 납품을 몇 차까지 돌렸나' 를 보려면 줄을 하나씩 읽어야 했다.
 * 프로젝트마다 접는 묶음으로 두고, 지금 고른 프로젝트만 펼친다. 프로젝트를 비워 두었으면
 * '프로젝트 없음' 을, 고른 프로젝트에 아직 실행이 없으면 가장 최근 묶음을 펼친다.
 * 묶음 안은 최신순이고 줄마다 기획서와 차수를 적는다 — 차수는 기획서별로 센다.
 */
function renderRuns() {
  const runs = state.runs;
  if (!runs.length) {
    $("runs").innerHTML = `<div class="empty-line">아직 실행한 기록이 없습니다.</div>`;
    return;
  }
  const current = $("project").value.trim();
  const groups = new Map();
  runs.forEach((r) => {
    const key = r.project || "";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(r);
  });
  // 지금 고른 프로젝트를 맨 위로, 나머지는 최근에 돌린 순서 그대로.
  const order = [...groups.keys()].sort((a, b) => (b === current) - (a === current));
  const open = groups.has(current) ? current : order[0];
  const shown = $("runs").querySelector(".run[aria-current='true']");
  const shownId = shown ? shown.dataset.run : "";

  $("runs").innerHTML = order.map((key) => `
    <details class="run-group" ${key === open ? "open" : ""}>
      <summary><b>${esc(key || "프로젝트 없음")}</b><span>${groups.get(key).length}회</span></summary>
      ${groups.get(key).map((r, i) => (i === RUNS_SHOWN ? `<details class="run-more"><summary>이전 기록 ${groups.get(key).length - RUNS_SHOWN}개 더 보기</summary>` : "") + `
      <button class="run ${r.fail ? "has-fail" : ""} ${runWhere(r) ? "has-where" : ""}" type="button"
              data-run="${esc(r.run_id)}" title="${esc(r.run_id)} · ${esc(r.target)} · ${r.pass}/${r.total} 통과"
              aria-current="${r.run_id === shownId}">
        <i class="led"></i>
        <span class="who"><b>${esc(runLabel(r))}</b><span class="line2"><span class="meta">${esc(
          [runTarget(r), r.round ? `${r.round}차` : "", runWhen(r)].filter(Boolean).join(" · "))}</span>${runWhere(r)}</span></span>
        ${runScore(r)}
      </button>`).join("")}${groups.get(key).length > RUNS_SHOWN ? "</details>" : ""}
    </details>`).join("");
  fluidHover($("runs"), ".run, .run-group > summary, .run-more > summary");

  $("runs").querySelectorAll("[data-run]").forEach((btn) => {
    btn.addEventListener("click", () => {
      $("runs").querySelectorAll(".run").forEach((b) =>
        b.setAttribute("aria-current", String(b === btn)));
      const r = runs.find((x) => x.run_id === btn.dataset.run);
      state.plan = null;
      showResult({ run_id: r.run_id, summary: r.summary,
                   report_url: `/runs/${r.run_id}/report.html` });
    });
  });
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
    `<option value="${NEW_PROJECT}">＋ 새 프로젝트 만들기…</option>`;
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
    return "이 이름은 쓸 수 없습니다 — 60자 이하로, / \\ : * ? \" < > | 없이, " +
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
  projectError("적어 둔 프로젝트 이름이 아직 추가되지 않았습니다 — [추가] 를 누르거나 이름을 지워 주세요.");
  $("projectNew").focus();
}, true);

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
  const current = $("project").value.trim();
  $("uploadBtn").textContent = current
    ? `'${current}' 에 기획서 올리기…` : "PDF/JSON 올리기…";   // 파일 창을 연다 — HIG: 끝에 말줄임
}

async function refreshSpecs(select) {
  const st = await api("/api/state");
  state.specGroups = st.spec_groups || [];
  renderProjects(st.projects || []);
  renderSpecs(select);
}

// 글자를 칠 때마다: 올릴 자리와 묶음 순서, 펼칠 실행 기록을 맞춘다.
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
  renderChrome();
});

// ── 사이드바 조작 ──────────────────────────────────────────────────────────

$("uploadBtn").addEventListener("click", () => $("upload").click());

$("upload").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const btn = $("uploadBtn");
  busyButton(btn, "올리는 중");
  try {
    const form = new FormData();
    form.append("file", file);
    // 기획서는 지금 적힌 프로젝트의 폴더로 들어간다 (서버가 이름을 확인한다).
    form.append("project", $("project").value.trim());
    const out = await api("/api/upload", { method: "POST", body: form });
    // JSON 은 Figma 응답, PDF 는 기획서 — 올라간 쪽 셀렉트에 넣고 선택한다.
    if (out.path.toLowerCase().endsWith(".json")) {
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
    saveSettings();
    renderChrome();
  } catch (err) {
    // 조용히 사라지면 사용자는 올라간 줄 안다.
    $("stage").insertAdjacentHTML("afterbegin",
      alertBox("fail", "업로드 실패", esc(err.message)));
  } finally {
    idleButton(btn); syncUploadLabel();
    e.target.value = "";
  }
});

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

// 예시 사이트 고르기의 흰 판도 단계 표시와 같은 방식으로 늘어났다 줄어든다.
const segThumb = stretchThumb(document.querySelector("#variantRow .seg"));
function placeSegThumb(instant = false) {
  const seg = document.querySelector("#variantRow .seg");
  const on = seg.querySelector('button[aria-pressed="true"]');
  const [first, last] = [seg.firstElementChild, seg.lastElementChild];
  if (!on || !first.offsetWidth) { segThumb.to(null); return; }
  segThumb.to(on, { instant, lo: first.offsetLeft + first.offsetWidth / 2,
                    hi: last.offsetLeft + last.offsetWidth / 2 });
  seg.dataset.thumb = "1";
}

$("segGood").addEventListener("click", () => setVariant("good"));
$("segBad").addEventListener("click", () => setVariant("bad"));
// 원본 내비처럼 ← → 로도 고른다. 고른 쪽으로 초점도 옮긴다.
document.querySelector("#variantRow .seg").addEventListener("keydown", (e) => {
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
  $(id).addEventListener("change", () => { saveSettings(); syncVariant(); renderChrome(); }));

$("url").addEventListener("input", () => { syncVariant(); renderChrome(); });

// Ctrl/Cmd + Enter 로 다음 단계
document.addEventListener("keydown", (e) => {
  if (!(e.key === "Enter" && (e.ctrlKey || e.metaKey))) return;
  const run = $("runBtn");
  if (run && !run.disabled) { run.click(); return; }
  if (!$("planBtn").disabled) $("planBtn").click();
});

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
      $("backend").insertAdjacentHTML("afterend",
        `<div class="hint">지난번 선택입니다 — 서버 기본값은 ${esc(st.backend)}</div>`);
    }
  } catch (err) {
    // 여기서 조용히 실패하면 화면이 죽은 채로 남는다.
    document.body.insertAdjacentHTML("afterbegin",
      `<div style="padding:16px">${alertBox("fail", "서버에 연결하지 못했습니다",
        esc(err.message))}</div>`);
    return;
  }
  syncVariant();
  renderChrome();
  showBlank();
  loadRuns();
}

boot();
