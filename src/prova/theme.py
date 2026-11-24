"""디자인 토큰 — 웹 UI 와 검증 리포트가 공유하는 단일 출처.

## 왜 한 곳에 두는가

리포트는 iframe 으로 웹 UI 안에 뜬다. 두 벌로 갈라져 있으면 같은 화면 안에서
파란색이 두 가지이고, 리포트만 다크모드가 아니어서 혼자 하얗게 빛난다. 실제로
그랬다 — UI 의 accent 는 `#2c4b8a`, 리포트는 `#2f6fed` 였다.

`server/` 밖에 두는 이유는 계층이다. S6 리포트 생성기가 웹 서버 모듈을 import 하면
"리포트를 만들려면 서버가 있어야 한다" 가 되는데, CLI 로 돌린 실행에는 서버가 없다.

## 소비 방법

    웹 UI    서버가 GET /static/tokens.css 로 제공 (동일 출처 — CDN 이 아니다)
    리포트   report_builder 가 _CSS 앞에 인라인 (자기완결 단일 HTML 이어야 한다)

## 세 층으로 쌓는다

    primitive   원시값. 여기서만 색을 '만든다'
    semantic    쓰임새 이름. 다크모드는 이 층에서만 갈린다
    component   컴포넌트 전용. 한 컴포넌트만 바꿀 때 여기만 본다

컴포넌트 규칙은 한 벌만 쓴다 — 다크모드용 규칙을 따로 쓰기 시작하면 두 벌이 되고,
한쪽이 반드시 뒤처진다.

## 레거시 별칭

리포트 CSS 는 `--bg`·`--line`·`--text` 같은 옛 이름을 쓴다. 그 이름을 새 semantic
토큰으로 이어 두었으므로 리포트 규칙은 손대지 않아도 색이 통일되고 다크모드가
따라온다. 별칭이 있는 한 두 벌로 갈라질 수 없다.
"""

_DARK = """    --bg-canvas:  var(--gray-950);
    --bg-surface: #171718;
    --bg-workspace: var(--gray-950);
    --bg-raised:  #1c1d1e;
    --bg-inset:   #0c0c0d;
    --bg-hover:   #222224;
    --bg-active:  #292a2c;

    --fg-default: #e8e9eb;
    --fg-muted:   var(--gray-350);
    --fg-subtle:  var(--gray-400);
    --fg-onaccent: var(--gray-950);

    --border-default: #2b2c2e;
    --border-subtle:  #222224;
    --border-strong:  #3a3a3c;

    --accent-fg:     #e8e9eb;
    --accent-solid:  #e8e9eb;
    --accent-hover:  var(--gray-0);
    --accent-bg:     #222224;
    --accent-border: #3a3a3c;

    --pass-fg: var(--green-400);
    --pass-bg: #12241b;
    --fail-fg: var(--red-400);
    --fail-bg: #2a1612;
    --warn-fg: var(--amber-400);
    --warn-bg: #261d0c;
    --info-fg: #e8e9eb;
    --info-bg: #1c1d1e;
    --note-fg: var(--violet-400);
    --note-bg: #1f1a2c;

    /* 황색↔적색의 색각 대비가 7.7 이라 이름표(범례)와 2px 틈을 함께 둔다 */
    --chart-pass:   #2f9467;
    --chart-weak:   #c08a1e;
    --chart-defect: #d0553f;
    --chart-infra:  #8b78c4;
    --chart-unv:    var(--gray-500);

    --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.4);
    --shadow-md: 0 2px 8px rgba(0, 0, 0, 0.45);
    --shadow-lg: 0 8px 28px rgba(0, 0, 0, 0.5);

    --focus-ring: 0 0 0 3px rgba(232, 233, 235, 0.30);"""

_TOKENS_TEMPLATE = """
/* ===========================================================================
   1. primitive — 원시값. 여기서만 색을 만든다.
   =========================================================================== */
:root {
  /* 회색은 중성이다. 노란 기가 도는 따뜻한 회색(#f3f1ec 등)은 넓게 깔리면 크림색 바탕처럼
     보여서, 밝기(CIELAB L*)는 그대로 두고 색기만 뺐다 — 글자 대비는 전과 같다. */
  --gray-0:   #ffffff;
  --gray-25:  #fbfcfe;
  --gray-50:  #f5f6f8;
  --gray-100: #f0f1f3;
  --gray-150: #e6e7e9;
  --gray-200: #d4d5d7;
  --gray-300: #bcbdbf;
  --gray-350: #a7a8aa;
  --gray-400: #949597;
  --gray-500: #737375;
  --gray-550: #6a6a6c;  /* 회색 일하는 면(gray-50) 위에서도 흐린 글자가 4.5:1 을 넘게 */
  --gray-600: #565658;
  --gray-700: #464749;
  --gray-800: #2b2c2e;
  --gray-900: #1a1b1c;
  --gray-950: #111112;

  --indigo-100: #e8ebfb;
  --indigo-200: #ccd3f6;
  --indigo-400: #8b98e8;
  --indigo-500: #5b6ad6;
  --indigo-600: #4655c0;
  --indigo-700: #38449c;

  --green-100: #edf4ef;
  --green-500: #1d6b48;
  --green-600: #155237;
  --green-400: #5fb98a;

  --red-100: #fbf3f1;
  --red-500: #a8321f;
  --red-600: #8c2817;
  --red-400: #e58a78;

  --amber-100: #f8f0dc;
  --amber-500: #8a5d0a;
  --amber-400: #d9a441;

  --violet-100: #f1eef7;
  --violet-500: #5d4a8c;
  --violet-400: #ab92e0;

  /* Apple HIG(Typography): 시스템 글꼴을 먼저 쓴다 — 맥에서는 SF Pro + Apple SD Gothic Neo 가 잡히고
     글자 간격도 크기마다 시스템이 맞춘다. 시스템 글꼴이 없는 곳(윈도)에서만 다음 글꼴로 넘어간다. */
  --font-sans: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Pretendard",
               "Segoe UI", "Malgun Gothic", system-ui, sans-serif;
  --font-mono: "Cascadia Mono", "SF Mono", ui-monospace, Consolas,
               "D2Coding", "Menlo", monospace;

  /* 4px 기준 간격 — 매직넘버를 쓰지 않기 위한 눈금 */
  --sp-1: 4px;  --sp-2: 8px;  --sp-3: 12px; --sp-4: 16px;
  --sp-5: 20px; --sp-6: 24px; --sp-8: 32px; --sp-10: 40px; --sp-12: 48px;

  /* 모서리는 둘만 눈에 띈다 — 버튼·입력칸 6px(r-lg), 묶음 상자 8px(r-xl). 알약(r-full)은 점·꼬리표에만. */
  --r-sm: 3px; --r-md: 4px; --r-lg: 6px; --r-xl: 8px; --r-card: 10px; --r-full: 999px;

  /* 글자 크기 — Apple HIG 의 macOS 글자 스타일에 맞춘다. xs 11 Subheadline · sm 12 Callout ·
     md 13 Body · base 15 Title 3 · lg 17 Title 2 · xl 22 Title 1 · 2xl/3xl 26 Large Title.
     본문은 한글 가독성 때문에 base(15)를 그대로 쓴다 — HIG 는 기본보다 큰 것은 막지 않는다. */
  --tx-xs: 11px; --tx-sm: 12px; --tx-md: 13px; --tx-base: 15px;
  --tx-lg: 17px; --tx-xl: 22px; --tx-2xl: 26px; --tx-3xl: 26px;

  /* 움직임 — 상태가 바뀔 때만 쓴다(단계 이동·항목 완료·숫자 바뀜·호버 위치).
     들어올 때 장식으로 쓰지 않는다. 화면 설정에서 '동작 줄이기' 면 app.css 가 모두 끈다. */
  --dur-1: 150ms; --dur-2: 180ms; --dur-3: 260ms; --dur-4: 700ms;
  --ease-out: cubic-bezier(0.2, 0.7, 0.2, 1);
  --ease-roll: cubic-bezier(0.3, 0.5, 0.2, 1);

  --lh-tight: 1.35; --lh-normal: 1.55; --lh-relaxed: 1.7;
}

/* ===========================================================================
   2. semantic — 쓰임새. 다크모드는 오직 이 층에서만 갈린다.
   =========================================================================== */
:root {
  --bg-canvas:  var(--gray-0);
  --bg-surface: var(--gray-0);
  /* 웹 화면의 일하는 면 — 옅은 회색 위에 흰 카드를 올린다(21st.dev Themes 미리보기에서).
     리포트 파일은 이 토큰을 쓰지 않는다 — 리포트는 흰 종이 한 장이다. */
  --bg-workspace: var(--gray-50);
  --bg-raised:  var(--gray-0);
  --bg-inset:   var(--gray-50);
  --bg-hover:   var(--gray-100);
  --bg-active:  var(--gray-150);

  /* 글자 대비 — Apple HIG: 4.5:1 아래로 내려가지 않고, 작은 글자는 7:1 을 노린다.
     muted 는 흰 바탕에서 7.3:1, subtle 은 5.4:1 — 회색 일하는 면(gray-50) 위에서도 6.7:1 · 5.0:1
     (어둡게: 7.5:1 · 5.6:1). */
  --fg-default: var(--gray-900);
  --fg-muted:   var(--gray-600);
  --fg-subtle:  var(--gray-550);
  --fg-onaccent: var(--gray-0);

  --border-default: var(--gray-200);
  --border-subtle:  var(--gray-150);
  --border-strong:  var(--gray-300);

  /* 컨트롤 층(위쪽 바·도구 줄)의 반투명 재질 — Apple HIG Materials: 재질은 내용 위에 뜬 컨트롤에만,
     내용 층에는 쓰지 않는다. '투명도 줄이기'·'대비 높이기' 에서는 불투명으로 바뀐다(아래). */
  --bg-bar: color-mix(in srgb, var(--bg-surface) 82%, transparent);

  /* 강조는 먹색이다 — 색은 판정(통과·기획서와 다름·실행 문제)과 알림에만 쓴다. */
  --accent-fg:     var(--gray-900);
  --accent-solid:  var(--gray-900);
  --accent-hover:  var(--gray-700);
  --accent-bg:     var(--gray-100);
  --accent-border: var(--gray-300);

  --pass-fg: var(--green-500);
  --pass-bg: var(--green-100);
  --fail-fg: var(--red-500);
  --fail-bg: var(--red-100);
  --warn-fg: var(--amber-500);
  --warn-bg: var(--amber-100);
  --info-fg: var(--gray-900);
  --info-bg: var(--gray-50);
  --note-fg: var(--violet-500);
  --note-bg: var(--violet-100);

  /* 리포트·웹 UI 의 비율 막대(처음에는 원형차트였다). 글자색(--pass-fg 등)을 그대로 쓰지 않는다 — 면으로 칠할 때의
     명도·색각 대비는 글자일 때와 다르다. dataviz validate_palette 로 양쪽 모드 확인. */
  --chart-pass:   #1d6b48;
  --chart-weak:   #b07d14;
  --chart-defect: #a8321f;
  --chart-infra:  #5d4a8c;
  --chart-unv:    var(--gray-400);

  --shadow-sm: 0 1px 2px rgba(16, 20, 28, 0.05);
  --shadow-md: 0 2px 8px rgba(16, 20, 28, 0.07);
  --shadow-lg: 0 8px 28px rgba(16, 20, 28, 0.10);

  --focus-ring: 0 0 0 3px rgba(26, 27, 28, 0.28);
}

/* 화면 설정(OS)을 따르되, 사람이 고른 값(data-theme)이 있으면 그쪽이 이긴다.
   다크 값은 _DARK 한 곳에만 적는다 — 두 번 적으면 한쪽이 뒤처진다. */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
__DARK__
  }
}

:root[data-theme="dark"] {
__DARK__
}

/* 입력 칸·스크롤 막대 같은 브라우저 기본 부품도 고른 쪽을 따른다 */
:root[data-theme="light"] { color-scheme: light; }
:root[data-theme="dark"]  { color-scheme: dark; }

/* 대비 높이기(OS 설정) — Apple HIG Color: 밝게·어둡게·대비 높임 세 경우 모두에서 읽혀야 한다.
   흐린 글자와 선을 한 단계씩 진하게 하고, 반투명 바는 불투명으로 바꾼다. */
@media (prefers-contrast: more) {
  :root {
__MORE_LIGHT__
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
__MORE_DARK__
    }
  }
  :root[data-theme="dark"] {
__MORE_DARK__
  }
}

/* 투명도 줄이기(OS 설정) — 반투명 재질을 불투명으로 */
@media (prefers-reduced-transparency: reduce) {
  :root { --bg-bar: var(--bg-surface); }
}

/* ===========================================================================
   3. 레거시 별칭 — 리포트 CSS 의 옛 이름을 새 semantic 으로 잇는다.
      이 별칭이 있는 한 UI 와 리포트의 색이 두 벌로 갈라질 수 없다.
   =========================================================================== */
:root {
  --bg:      var(--bg-surface);
  --card:    var(--bg-surface);
  --line:    var(--border-default);
  --text:    var(--fg-default);
  --muted:   var(--fg-muted);
  --accent:  var(--accent-fg);
  --pass:    var(--pass-fg);
  --fail:    var(--fail-fg);
}
"""

_MORE_LIGHT = """    --fg-muted:   var(--gray-700);
    --fg-subtle:  var(--gray-600);
    --border-default: var(--gray-400);
    --border-subtle:  var(--gray-300);
    --border-strong:  var(--gray-600);
    --bg-bar: var(--bg-surface);"""

_MORE_DARK = """    --fg-muted:   var(--gray-300);
    --fg-subtle:  var(--gray-350);
    --border-default: var(--gray-600);
    --border-subtle:  var(--gray-700);
    --border-strong:  var(--gray-500);
    --bg-bar: var(--bg-surface);"""

TOKENS_CSS = (_TOKENS_TEMPLATE.replace("__DARK__", _DARK)
              .replace("__MORE_LIGHT__", _MORE_LIGHT).replace("__MORE_DARK__", _MORE_DARK))
