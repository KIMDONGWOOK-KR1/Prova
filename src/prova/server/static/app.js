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

function alertBox(kind, title, why) {
  return `<div class="alert ${kind}">${ICON[kind] || ICON.info}<div>` +
    `<b>${title}</b>${why ? `<div class="why">${why}</div>` : ""}</div></div>`;
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

function renderChrome() {
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
  document.body.dataset.step = n;
  for (const el of $("stepper").querySelectorAll("[data-step]")) {
    if (Number(el.dataset.step) === n) el.setAttribute("aria-current", "step");
    else el.removeAttribute("aria-current");
  }
}

$("stepper").addEventListener("click", (e) => {
  const n = e.target.dataset && e.target.dataset.step;
  if (state.busy || e.target.tagName !== "BUTTON") return;
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
    <div class="head"><h1>${esc(title)}</h1><span class="spin" aria-hidden="true"></span>
      <span class="elapsed" id="pElapsed">0초</span></div>
    <div class="pnow" id="pNow" aria-live="polite"></div>
    <progress id="pBar" hidden></progress>
    <div class="ptally" id="pTally" hidden></div>
    ${title === "실행 중" ? `<button class="btn ghost" id="pStop" type="button" hidden>멈추기</button>` : ""}
    <div class="steps" id="pSteps"></div>
    <details class="raw"><summary>진행 로그 전체</summary>
      <pre class="log" id="pLog" role="log" aria-live="polite"></pre></details>`;
  pushProgress(lines || []);
  clearInterval(elapsedTimer);
  const t0 = Date.now();
  elapsedTimer = setInterval(() => {
    const el = $("pElapsed");
    if (!el) { clearInterval(elapsedTimer); return; }  // 화면이 결과로 바뀌면 멈춘다
    el.textContent = `${Math.round((Date.now() - t0) / 1000)}초`;
  }, 1000);
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
  log.textContent += messages.join("\n") + "\n";
  log.scrollTop = log.scrollHeight;

  for (const raw0 of messages) {
    // 지금까지의 판정 수 (nodes.run_cases 의 '집계' 줄). 단계 목록에 쌓지 않는다.
    const t = /집계 통과 (\d+) · 기획서와 다름 (\d+) · 실행 문제 (\d+)(?: · 확인 불가 (\d+))?/.exec(raw0);
    if (t) {
      const el = $("pTally");
      el.hidden = false;
      el.innerHTML = `<span class="ok">통과 ${t[1]}</span>` +
        `<span class="fail">기획서와 다름 ${t[2]}</span>` +
        `<span class="infra">실행 문제 ${t[3]}</span>` +
        (t[4] && t[4] !== "0" ? `<span class="unv">확인 불가 ${t[4]}</span>` : "");
      continue;
    }
    const raw = plainProgress(raw0);
    // 케이스 줄은 단계 목록에 쌓지 않고 '몇 건 중 몇 번째' 로 보인다. 원문은 로그에 남는다.
    const m = /케이스 (\d+)\/(\d+) · (.+)/.exec(raw);
    if (m) {
      $("pNow").textContent = `${m[2]}건 중 ${m[1]}번째 — ${m[3]}`;
      const bar = $("pBar");
      bar.hidden = false; bar.max = Number(m[2]); bar.value = Number(m[1]) - 1;
      continue;
    }
    const isDetail = /^\s{2,}/.test(raw) || raw.trimStart().startsWith("!");
    const text = raw.trim();
    if (!text) continue;
    if (isDetail) {
      const last = steps.lastElementChild;
      if (last) {
        const d = document.createElement("div");
        d.className = "detail";
        d.textContent = text.replace(/^!\s*/, "⚠ ");
        last.querySelector(".body").appendChild(d);
        continue;
      }
    }
    const prev = steps.lastElementChild;
    if (prev) { prev.classList.remove("active"); prev.classList.add("done"); }
    const el = document.createElement("div");
    el.className = "pstep active";
    el.innerHTML = `<span class="mark">●</span><div class="body">${esc(text.replace(/^S\d(~S\d)?\s+/, ""))}</div>`;
    steps.appendChild(el);
  }
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

function finishProgress() {
  const last = $("pSteps") && $("pSteps").lastElementChild;
  if (last) { last.classList.remove("active"); last.classList.add("done"); }
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
      ? `흐름 ${esc(key.slice(5))}` : esc(screenName(key));
    const on = list.filter((c) => c.selected).length;
    return `<section class="group">
      <header>
        <h3>${title}</h3>
        <span class="n">${on}/${list.length}</span>
        <button class="btn ghost quiet" data-group="${esc(key)}" type="button">
          ${on === list.length ? "모두 끄기" : "모두 켜기"}</button>
      </header>
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
  return `<details class="how">
    <summary class="line">${head}</summary>
    <ol>${(c.steps || []).map((s) => `<li>${esc(s.replace(/^(준비 )?\d+\. /, "$1"))}</li>`).join("")}</ol>
    ${c.expected ? `<div class="expect"><b>기대</b> ${esc(c.expected)}</div>` : ""}
    ${(c.sources || []).map((s) => `<div class="expect src"><b>기획서</b> ${esc(s)}</div>`).join("")}
    <div class="expect src"><b>케이스 번호</b> ${esc(c.case_id)}</div>
  </details>`;
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
        stop.disabled = true;
        stop.textContent = "지금 항목이 끝나면 멈춥니다…";
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
        <a class="btn ghost" href="${esc(out.report_url)}" target="_blank" rel="noopener">리포트 파일 열기</a>
        ${state.plan ? `<button class="btn ghost" id="againBtn" type="button">다시 실행</button>` : ""}
      </div>
    </div>
    <div class="meter" aria-hidden="true"><i class="f" style="flex:${defects}"></i><i class="x" style="flex:${infra}"></i><i class="u" style="flex:${unv}"></i><i style="flex:${s.pass}"></i></div>
    <div class="tally">기획서와 다름 ${defects} · 실행 문제 ${infra}${unv ? ` · 확인 불가 ${unv}` : ""} · 통과 ${s.pass} · 통과율 ${s.pass_rate}%</div>
    ${notes.join("")}
    <div class="reportbox">
      <iframe id="reportFrame" src="${esc(out.report_url)}" title="검증 리포트" scrolling="no"
              allow="clipboard-write"></iframe>
    </div>`;
  // 같은 항목·같은 옵션으로 한 번 더 — 고친 뒤 확인할 때 1·2단계를 다시 밟지 않는다.
  const again = $("againBtn");
  if (again) again.addEventListener("click", startRun);
  fitFrame($("stage").querySelector("iframe"));
}

// ── 밝게 / 어둡게 ─────────────────────────────────────────────────────────
// 기본은 화면 설정(OS)을 따른다. 버튼을 누르면 그 선택을 기억한다 — 발표·시연 때
// PC 설정과 상관없이 한쪽으로 고정할 수 있게. 리포트(iframe)도 같이 바꾼다.
const THEME_KEY = "prova-theme";

function currentTheme() {
  const set = document.documentElement.getAttribute("data-theme");
  if (set === "light" || set === "dark") return set;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyThemeToReport() {
  const frame = $("reportFrame");
  try {
    if (frame && frame.contentDocument) {
      frame.contentDocument.documentElement.setAttribute("data-theme", currentTheme());
    }
  } catch (e) { /* 같은 출처가 아니면 리포트는 제 설정대로 둔다 */ }
}

function renderThemeBtn() {
  const dark = currentTheme() === "dark";
  // 버튼은 누르면 바뀔 쪽을 말한다.
  $("themeBtn").textContent = dark ? "밝게" : "어둡게";
  $("themeBtn").setAttribute("aria-label", dark ? "밝은 화면으로 바꾸기" : "어두운 화면으로 바꾸기");
}

$("themeBtn").addEventListener("click", () => {
  const next = currentTheme() === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem(THEME_KEY, next); } catch (e) { /* 저장 못 해도 이번 화면은 바뀐다 */ }
  renderThemeBtn();
  applyThemeToReport();
});
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", renderThemeBtn);
renderThemeBtn();

/**
 * 리포트 틀의 높이를 내용에 맞춘다 — 틀 안에 스크롤이 또 생기면 페이지 스크롤과 겹쳐
 * 어디를 굴려야 할지 헷갈린다. 펼침·접기로 높이가 바뀌어도 따라간다 (같은 출처라 읽을 수 있다).
 */
function fitFrame(frame) {
  frame.addEventListener("load", () => {
    const doc = frame.contentDocument;
    if (!doc) return;
    applyThemeToReport();  // 리포트도 고른 화면 모드로 연다
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
      <button class="run ${r.fail ? "has-fail" : ""}" type="button"
              data-run="${esc(r.run_id)}" title="${esc(r.run_id)} · ${esc(r.target)} · ${r.pass}/${r.total} 통과"
              aria-current="${r.run_id === shownId}">
        <i class="led"></i>
        <span class="who"><b>${esc(runLabel(r))}</b><span>${esc(
          [runTarget(r), r.round ? `${r.round}차` : "", runWhen(r)].filter(Boolean).join(" · "))}</span></span>
        ${runScore(r)}
      </button>`).join("")}${groups.get(key).length > RUNS_SHOWN ? "</details>" : ""}
    </details>`).join("");

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
    ? `＋ '${current}' 에 기획서 올리기` : "＋ PDF/JSON 올리기";
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
  btn.disabled = true; btn.textContent = "올리는 중…";
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
    btn.disabled = false; syncUploadLabel();
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
}

$("segGood").addEventListener("click", () => setVariant("good"));
$("segBad").addEventListener("click", () => setVariant("bad"));

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
