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
  if (!res.ok) throw new ApiError(body.detail || `${res.status} ${res.statusText}`, res.status);
  return body;
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
};

const LS = "prova.settings.v1";

function saveSettings() {
  try {
    localStorage.setItem(LS, JSON.stringify({
      pdf: $("pdf").value, url: $("url").value, backend: $("backend").value,
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
    `<span class="chip">${esc(f.backend)}</span>`;
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

function showProgress(title, lines) {
  $("stageChips").innerHTML = `<span class="chip busy"><i class="dot"></i>실행 중</span>`;
  $("stage").innerHTML = `
    <div class="head"><h1>${esc(title)}</h1><span class="spin" aria-hidden="true"></span></div>
    <div class="steps" id="pSteps"></div>
    <details class="raw"><summary>진행 로그 전체</summary>
      <pre class="log" id="pLog" role="log" aria-live="polite"></pre></details>`;
  pushProgress(lines || []);
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

  renderPlanBody();
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

function caseRow(c) {
  return `<div class="case ${c.selected ? "" : "off"}" data-id="${esc(c.case_id)}">
    <input type="checkbox" ${c.selected ? "checked" : ""}
           aria-label="${esc(c.case_id)} 실행">
    <div>
      <div class="id">${esc(c.case_id)}</div>
      <div class="desc">${esc(c.title)}</div>
    </div>
    <div class="marks">
      ${c.violates ? `<span class="tag rule">${esc(c.violates)}</span>` : ""}
      ${c.flow_id ? `<span class="tag flow">흐름</span>` : ""}
    </div>
  </div>`;
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
  run.disabled = n === 0;
  $("runHint").textContent = n === 0
    ? "0건은 실행할 수 없습니다 — 통과율 100% 리포트가 됩니다" : "";
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
      body: JSON.stringify({ ...form(), case_ids: ids, reason: state.plan.reason || "" }),
    });
    const out = await follow(job_id, pushProgress);
    finishProgress();
    state.result = out;
    showResult(out);
    loadRuns();
  } catch (err) {
    if (err.status === 409) {
      showError("이미 실행 중입니다",
        "브라우저와 GPU 를 두 작업이 함께 쓰면 판정 타이밍이 흔들리므로 " +
        "한 번에 하나만 실행합니다. 지금 도는 작업이 끝난 뒤 다시 눌러 주세요.");
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
  const planned = state.plan ? state.plan.cases.length : s.total;
  const off = planned - s.total;

  $("stageChips").innerHTML =
    `<span class="chip ${s.fail ? "warn" : "ok"}"><i class="dot"></i>` +
    `${s.fail ? `실패 ${s.fail}건` : "전부 통과"}</span>`;

  const notes = [];
  if (off > 0) {
    notes.push(alertBox("info", "이 통과율은 전체 상태가 아닙니다",
      `생성된 ${planned}건 중 ${s.total}건만 실행했습니다. 나머지 ${off}건은 ` +
      `<b>통과한 것이 아니라 확인하지 않은 것</b>입니다.`));
  }
  if (s.llm_backend === "mock") {
    notes.push(alertBox("warn", "mock 백엔드로 실행한 결과입니다",
      "설계 문서 추출에 실제 모델을 쓰지 않았습니다. 실제 검증 결과로 쓰지 마세요."));
  }

  $("stage").innerHTML = `
    <div class="head">
      <h1>실행 결과</h1>
      <div class="sub"><code>${esc(out.run_id)}</code></div>
    </div>
    <div class="stats">
      <div class="stat"><div class="n">${s.total}</div><div class="k">실행</div></div>
      <div class="stat pass"><div class="n">${s.pass}</div><div class="k">통과</div></div>
      <div class="stat fail"><div class="n">${s.fail}</div><div class="k">실패</div></div>
      <div class="stat"><div class="n">${s.pass_rate}%</div><div class="k">통과율</div></div>
    </div>
    <div class="meter"><i style="width:${s.pass_rate}%"></i></div>
    ${notes.join("")}
    <div class="reportbox" id="reportBox">
      <header>
        <span class="t">검증 리포트</span>
        <button class="btn ghost quiet" id="tallBtn" type="button">크게 보기</button>
        <a class="btn ghost quiet" href="${esc(out.report_url)}" target="_blank"
           rel="noopener">새 탭에서 열기 ↗</a>
      </header>
      <iframe src="${esc(out.report_url)}" title="검증 리포트"></iframe>
    </div>`;

  $("tallBtn").addEventListener("click", (e) => {
    const box = $("reportBox");
    box.classList.toggle("tall");
    e.currentTarget.textContent = box.classList.contains("tall") ? "작게 보기" : "크게 보기";
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
  let runs;
  // 비어 있는 것과 아직 안 온 것을 구분해 준다. 빈 칸만 보이면 사람은
  // 기록이 없는 줄 안다.
  if (!$("runs").children.length) {
    $("runs").innerHTML = `<div class="empty-line">불러오는 중…</div>`;
  }
  try {
    runs = (await api("/api/runs")).runs;
  } catch (e) {
    $("runs").innerHTML = `<div class="empty-line">기록을 불러오지 못했습니다.</div>`;
    return;
  }
  if (!runs.length) {
    $("runs").innerHTML = `<div class="empty-line">아직 실행한 기록이 없습니다.</div>`;
    return;
  }
  $("runs").innerHTML = runs.map((r) => `
    <button class="run ${r.fail ? "has-fail" : ""}" type="button"
            data-run="${esc(r.run_id)}" title="${esc(r.run_id)} · ${esc(r.target)}">
      <i class="led"></i>
      <span class="who"><b>${esc(runLabel(r))}</b><span>${esc(runWhen(r))}</span></span>
      <span class="score">${r.pass}/${r.total}</span>
    </button>`).join("");

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

// ── 사이드바 조작 ──────────────────────────────────────────────────────────

$("uploadBtn").addEventListener("click", () => $("upload").click());

$("upload").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const btn = $("uploadBtn");
  const label = btn.textContent;
  btn.disabled = true; btn.textContent = "올리는 중…";
  try {
    const form = new FormData();
    form.append("file", file);
    const out = await api("/api/upload", { method: "POST", body: form });
    if (![...$("pdf").options].some((o) => o.value === out.path)) {
      const opt = document.createElement("option");
      opt.value = out.path; opt.textContent = out.path;
      $("pdf").appendChild(opt);
    }
    $("pdf").value = out.path;
    saveSettings();
    renderChrome();
  } catch (err) {
    // 조용히 사라지면 사용자는 올라간 줄 안다.
    $("stage").insertAdjacentHTML("afterbegin",
      alertBox("fail", "업로드 실패", esc(err.message)));
  } finally {
    btn.disabled = false; btn.textContent = label;
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

["pdf", "url", "backend"].forEach((id) =>
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
    $("pdf").innerHTML = st.specs.map((p) =>
      `<option value="${esc(p)}">${esc(p)}</option>`).join("");
    $("backend").value = st.backend;

    const saved = loadSettings();
    if (saved.pdf && [...$("pdf").options].some((o) => o.value === saved.pdf)) {
      $("pdf").value = saved.pdf;
    }
    if (saved.url) $("url").value = saved.url;
    if (saved.backend) $("backend").value = saved.backend;
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
