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
  blank: `<svg width="52" height="52" viewBox="0 0 52 52" fill="none" aria-hidden="true"><rect x="9" y="5" width="26" height="34" rx="3" stroke="var(--border-strong)" stroke-width="1.6"/><path d="M15 14h14M15 20h14M15 26h9" stroke="var(--border-strong)" stroke-width="1.6" stroke-linecap="round"/><circle cx="35" cy="35" r="11" fill="var(--bg-canvas)" stroke="var(--accent-solid)" stroke-width="1.6"/><path d="M30.5 35.2l3 3 6-6.4" stroke="var(--accent-solid)" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
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
  };
}

// ── 상단 · 칩 ──────────────────────────────────────────────────────────────

function renderChrome() {
  const f = form();
  const spec = (f.pdf || "").split("/").pop() || "기획서 없음";
  $("crumbs").innerHTML =
    `<b>${esc(spec)}</b><span class="sep">→</span><span>${esc(f.url || "대상 없음")}</span>`;

  $("chips").innerHTML =
    `<span class="chip ${state.busy ? "busy" : "ok"}"><i class="dot"></i>` +
    `${state.busy ? "실행 중" : "준비됨"}</span>` +
    `<span class="chip">${esc(f.backend)}</span>` +
    (f.figma ? `<span class="chip">병합 — 디자인 대조</span>` : "");
  renderOptState();
}

// 접힌 '실행 방식' 의 제목 줄에 지금 고른 것을 적는다. 판정을 바꾸는 선택이 켜져 있으면
// 굵게 — 접혀 있어서 켠 줄 모르고 돌리는 일이 없어야 한다.
function renderOptState() {
  const names = { mock: "연습용 응답", vllm: "실제 모델", replay: "저장된 응답" };
  const parts = [esc(names[$("backend").value] || $("backend").value)];
  if ($("figma").value) parts.push("디자인 병합");
  if ($("vlm").checked) parts.push("<b>화면 이미지로 찾기</b>");
  if ($("dryRun").checked) parts.push("<b>쓰기 요청 막기</b>");
  $("optState").innerHTML = parts.join(" · ");
}

for (const id of ["backend", "figma", "vlm", "dryRun"]) {
  $(id).addEventListener("change", renderOptState);
}

// ── 무대 (한 번에 한 상태만) ────────────────────────────────────────────────

function showBlank() {
  $("stageChips").innerHTML = "";
  $("stage").innerHTML = `
    <div class="blank">
      ${ICON.blank}
      <h2>기획서대로 만들어졌는지 확인합니다</h2>
      <p>설정에서 기획서와 대상 URL 을 고르고 계획을 만드세요.</p>
      <ol>
        <li><span>기획서에서 검증 규칙을 뽑아 <b>규칙 하나당 케이스 하나</b>를 만듭니다.</span></li>
        <li><span>실행 전에 <b>무엇을 테스트할지 보여드립니다.</b> 빠진 것이 있으면 그 자리에서 되돌릴 수 있습니다.</span></li>
        <li><span>진짜 브라우저로 조작하고, 어느 규칙이 구현되지 않았는지 리포트로 짚어 줍니다.</span></li>
      </ol>
    </div>`;
}

// 경과 시간. 몇 분 걸리는 실행에서 멈춘 것과 도는 것을 구별하게 한다.
let elapsedTimer = null;

function showProgress(title, lines) {
  $("stageChips").innerHTML = `<span class="chip busy"><i class="dot"></i>실행 중</span>`;
  $("stage").innerHTML = `
    <div class="head"><h1>${esc(title)}</h1><span class="spin" aria-hidden="true"></span>
      <span class="elapsed" id="pElapsed">0초</span></div>
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

  for (const raw of messages) {
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
    el.innerHTML = `<span class="mark">●</span><div class="body">${esc(text)}</div>`;
    steps.appendChild(el);
  }
}

function finishProgress() {
  const last = $("pSteps") && $("pSteps").lastElementChild;
  if (last) { last.classList.remove("active"); last.classList.add("done"); }
}

function showError(title, message) {
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
  const p = state.plan;
  $("stageChips").innerHTML =
    `<span class="chip">생성 ${p.total_generated}건</span>`;

  $("stage").innerHTML = `
    <div class="head">
      <h1>이렇게 이해했습니다</h1>
      <div class="sub">${p.request
        ? `요청 — ${esc(p.request)}`
        : "요청이 없어 전체 케이스를 골랐습니다"}</div>
    </div>
    <div id="planNotes"></div>
    <details class="spec" id="specPanel"></details>
    <div class="toolbar">
      <div class="count" id="count"></div>
      <button class="btn ghost quiet" id="allBtn" type="button">전체</button>
      <button class="btn ghost quiet" id="invBtn" type="button">반전</button>
      <button class="btn ghost quiet" id="offBtn" type="button" aria-pressed="false">제외만</button>
      <label class="search">
        ${ICON.search}
        <span class="sr">케이스 검색</span>
        <input type="text" id="q" placeholder="케이스 검색" spellcheck="false">
      </label>
    </div>
    <div id="groups"></div>
    <div class="runbar">
      <button class="btn primary" id="runBtn" type="button">이대로 실행</button>
      <button class="btn ghost" id="backBtn" type="button">요청 고치기</button>
      <span class="hint" id="runHint"></span>
    </div>`;

  $("q").addEventListener("input", (e) => {
    state.filter = e.target.value;
    renderGroups();
  });
  $("allBtn").addEventListener("click", () => {
    p.cases.forEach((c) => { c.selected = true; });
    renderPlanBody();
  });
  $("invBtn").addEventListener("click", () => {
    const shown = new Set(visibleCases().map((c) => c.case_id));
    p.cases.forEach((c) => { if (shown.has(c.case_id)) c.selected = !c.selected; });
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
  ["label", "라벨"], ["required", "필수"], ["placeholder", "안내 문구"],
  ["error_message", "오류 문구"], ["required_message", "빈 칸 문구"], ["options", "선택 항목"],
];
const SCREEN_FIELDS = [
  ["url_path", "경로"], ["success_condition", "성공 조건"], ["required_message", "필수 공통 문구"],
];
// 빈 칸으로 두면 '없음'(null) 이 되는 칸. 라벨·경로·성공 조건은 빈 글자 그대로 둔다.
const NULLABLE = new Set(["placeholder", "error_message", "required_message"]);
const CHOICE_TYPES = new Set(["select", "radio", "checkbox"]);

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
      : "틀린 칸이 있으면 고친 뒤 [다시 만들기] — 기획서 문구 그대로 적어 주세요"}</span></summary>`;
  const screens = d.screens.map((sc, si) => {
    const meta = SCREEN_FIELDS.map(([k, name]) =>
      `<label class="spec-meta"><span>${name}</span>${specInput(`s${si}`, k, sc[k])}</label>`).join("");
    const rows = sc.elements.map((e, ei) => {
      // 선택 항목은 고를 수 있는 요소에만 있다 — 입력칸·버튼에 빈 상자를 두면 표가 어수선하다.
      const cells = EL_FIELDS.map(([k]) => k === "options" && !CHOICE_TYPES.has(e.type)
        ? `<td class="id">—</td>`
        : `<td>${specInput(`s${si}.e${ei}`, k, e[k])}</td>`).join("");
      return `<tr class="${e._removed ? "off" : ""}"><td class="id">${esc(e.type)}<br>${esc(e.element_id)}</td>${cells}
        <td><label class="check"><input type="checkbox" data-remove="s${si}.e${ei}"
            ${e._removed ? "checked" : ""}> 뺌</label></td></tr>`;
    }).join("");
    return `<section class="group spec-screen">
      <header><h3>${esc(sc.screen_name)}</h3></header>
      <div class="spec-metas">${meta}</div>
      <div class="spec-scroll"><table class="spec-table">
        <thead><tr><th>요소</th>${EL_FIELDS.map(([, n]) => `<th>${n}</th>`).join("")}<th></th></tr></thead>
        <tbody>${rows}</tbody></table></div>
    </section>`;
  }).join("");
  const list = edits.length
    ? `<ul class="spec-edits">${edits.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>` : "";
  $("specPanel").innerHTML = head + list + screens + `
    <div class="runbar"><button class="btn ghost" id="replanBtn" type="button" disabled>
      고친 내용으로 케이스 다시 만들기</button>
      <span class="hint" id="specHint"></span></div>`;
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
  $("specHint").textContent = "고친 내용은 [다시 만들기] 를 눌러야 케이스에 반영됩니다";
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
      ${list.map(caseRow).join("")}
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
    row.addEventListener("click", (e) => {
      // '절차·기대' 를 펼치는 클릭은 선택을 바꾸지 않는다 — 읽으려고 눌렀다가 케이스가 꺼지면 안 된다.
      if (e.target.closest(".how")) return;
      const box = row.querySelector("input");
      if (e.target !== box) box.checked = !box.checked;
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

function groupCount(row) {
  const rows = [...row.closest(".group").querySelectorAll(".case")];
  const on = rows.filter((r) => r.querySelector("input").checked).length;
  return `${on}/${rows.length}`;
}

// 사람이 읽는 제목을 먼저, 내부 id 는 작게 뒤로. 스크린 리더도 제목을 읽는다.
function caseRow(c) {
  return `<div class="case ${c.selected ? "" : "off"}" data-id="${esc(c.case_id)}">
    <input type="checkbox" ${c.selected ? "checked" : ""}
           aria-label="${esc(c.title)} 실행">
    <div>
      <div class="desc">${esc(c.title)}</div>
      <div class="id">${esc(c.case_id)}</div>
      ${caseHow(c)}
    </div>
    <div class="marks">
      ${c.violates ? `<span class="tag rule" title="${esc(c.violates)}">${
        esc([c.target_label, c.rule_label || c.violates].filter(Boolean).join(" · "))}</span>` : ""}
      ${c.flow_id ? `<span class="tag flow">흐름</span>` : ""}
    </div>
  </div>`;
}

// 무슨 값을 넣고 무엇을 기대하는지. 제목만 보고 승인하지 않게 한다 (prova/wording.py).
function caseHow(c) {
  if (!(c.steps || []).length && !c.expected) return "";
  return `<details class="how">
    <summary>절차·기대 보기</summary>
    <ol>${(c.steps || []).map((s) => `<li>${esc(s.replace(/^(준비 )?\d+\. /, "$1"))}</li>`).join("")}</ol>
    ${c.expected ? `<div class="expect"><b>기대</b> ${esc(c.expected)}</div>` : ""}
    ${(c.sources || []).map((s) => `<div class="expect src"><b>기획서</b> ${esc(s)}</div>`).join("")}
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
    } else {
      showError("실행 실패", err.message);
    }
  } finally {
    state.busy = false;
    renderChrome();
  }
}

function showResult(out) {
  const s = out.summary;

  $("stageChips").innerHTML =
    `<span class="chip ${s.fail ? "warn" : "ok"}"><i class="dot"></i>` +
    `${s.fail ? `실패 ${s.fail}건` : "전부 통과"}</span>`;

  // 숫자와 알림은 리포트가 말한다. 여기서 한 번 더 그리면 같은 숫자 네 칸과 같은 알림이
  // 위아래로 두 번 보였다 — 리포트는 파일로 따로 나가는 문서라 거기 있는 쪽이 원본이다.
  // 그래서 이 화면은 리포트를 칸에 가두지 않고 그대로 펼쳐 보여 주기만 한다.
  $("stage").innerHTML = `
    <div class="head">
      <h1>실행 결과</h1>
      <div class="sub"><code>${esc(out.run_id)}</code>
        <a class="btn ghost quiet" href="${esc(out.report_url)}" target="_blank"
           rel="noopener">리포트만 새 탭에서 열기 ↗</a></div>
    </div>
    <iframe class="report" id="reportFrame" src="${esc(out.report_url)}"
            title="검증 리포트" scrolling="no"></iframe>`;

  fitReport($("reportFrame"));
}

// 리포트의 길이에 맞춰 틀의 높이를 늘린다 — 안쪽 스크롤이 따로 생기면 바깥 스크롤과
// 겹쳐 휠이 어디를 움직이는지 헷갈린다. 카드를 펼치면 길이가 바뀌므로 계속 지켜본다.
function fitReport(frame) {
  const fit = () => {
    try {
      const doc = frame.contentDocument;
      if (doc && doc.body) {
        frame.style.height = `${doc.body.offsetHeight}px`;
      }
    } catch (e) { /* 같은 출처가 아니면 기본 높이로 둔다 */ }
  };
  frame.addEventListener("load", () => {
    fit();
    try {
      const doc = frame.contentDocument;
      new ResizeObserver(fit).observe(doc.body);
      doc.addEventListener("toggle", fit, true);
    } catch (e) { /* 위와 같다 */ }
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
  const spec = (r.spec || "").replace(/_spec\.pdf$/, "").replace(/\.pdf$/, "");
  const variant = (/\/(good|bad)(\/|$)/.exec(r.target || "") || [])[1];
  return variant ? `${spec} · ${variant}` : (spec || r.run_id);
}

/** 언제 돌렸는지. 같은 대상을 여러 번 돌리면 이것만이 구분점이 된다. */
function runWhen(r) {
  const t = r.created_at || "";
  const m = /(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(t);
  return m ? `${m[2]}-${m[3]} ${m[4]}:${m[5]}` : r.run_id;
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
      ${groups.get(key).map((r) => `
      <button class="run ${r.fail ? "has-fail" : ""}" type="button"
              data-run="${esc(r.run_id)}" title="${esc(r.run_id)} · ${esc(r.target)}"
              aria-current="${r.run_id === shownId}">
        <i class="led"></i>
        <span class="who"><b>${esc(runLabel(r))}</b><span>${esc(
          [r.round ? `${r.round}차` : "", runWhen(r)].filter(Boolean).join(" · "))}</span></span>
        <span class="score">${r.pass}/${r.total}</span>
      </button>`).join("")}
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

// 프로젝트는 목록에서 고른다. 이름 칸(#project)은 값을 담는 자리로 그대로 두고,
// '새 프로젝트 만들기' 를 골랐을 때만 보여 준다 — 자동완성 목록은 고를 수 있다는 것이
// 눈에 안 띄고, 이미 적힌 글자와 맞는 것만 걸러 보여 다른 프로젝트로 바꾸기 어려웠다.
// 이름에 쓸 수 없는 글자(:)를 넣어 실제 프로젝트 이름과 겹치지 않게 한다.
const NEW_PROJECT = "::new";

function renderProjects(names) {
  if (names) state.projects = names;
  const known = state.projects || [];
  const current = $("project").value.trim();
  const pick = $("projectPick");
  // 목록에 없는 이름이 적혀 있으면 아직 만드는 중이다.
  const making = !known.includes(current) && (current !== "" || pick.value === NEW_PROJECT);
  pick.innerHTML = `<option value="">프로젝트 없음</option>` +
    known.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("") +
    `<option value="${NEW_PROJECT}">＋ 새 프로젝트 만들기…</option>`;
  pick.value = making ? NEW_PROJECT : current;
  $("project").hidden = !making;
}

$("projectPick").addEventListener("change", () => {
  const picked = $("projectPick").value;
  const input = $("project");
  input.value = picked === NEW_PROJECT ? "" : picked;
  input.hidden = picked !== NEW_PROJECT;
  // 값이 바뀐 것은 이름 칸의 일이다 — 거기 달린 처리(올릴 자리·묶음·저장)를 그대로 태운다.
  input.dispatchEvent(new Event("input"));
  input.dispatchEvent(new Event("change"));
  if (picked === NEW_PROJECT) input.focus();
});

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
}

$("segGood").addEventListener("click", () => setVariant("good"));
$("segBad").addEventListener("click", () => setVariant("bad"));

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
    if (saved.project) { $("project").value = saved.project; renderProjects(); }
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
    if (saved.backend && saved.backend !== st.backend) {
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
