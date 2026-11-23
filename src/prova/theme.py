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
    --bg-raised:  #1c1d1e;
    --bg-inset:   #0c0c0d;
    --bg-hover:   #222224;
    --bg-active:  #292a2c;

    --fg-default: #e8e9eb;
    --fg-muted:   var(--gray-400);
    --fg-subtle:  var(--gray-500);
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
  --gray-400: #949597;
  --gray-500: #737375;
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

  --font-sans: "Pretendard", -apple-system, BlinkMacSystemFont, "Segoe UI",
               "Malgun Gothic", "Apple SD Gothic Neo", system-ui, sans-serif;
  --font-mono: "Cascadia Mono", "SF Mono", ui-monospace, Consolas,
               "D2Coding", "Menlo", monospace;

  /* 4px 기준 간격 — 매직넘버를 쓰지 않기 위한 눈금 */
  --sp-1: 4px;  --sp-2: 8px;  --sp-3: 12px; --sp-4: 16px;
  --sp-5: 20px; --sp-6: 24px; --sp-8: 32px; --sp-10: 40px; --sp-12: 48px;

  --r-sm: 2px; --r-md: 2px; --r-lg: 3px; --r-xl: 4px; --r-full: 999px;

  --tx-xs: 11px; --tx-sm: 12px; --tx-md: 13px; --tx-base: 15px;
  --tx-lg: 16px; --tx-xl: 20px; --tx-2xl: 26px;

  --lh-tight: 1.35; --lh-normal: 1.55; --lh-relaxed: 1.7;
}

/* ===========================================================================
   2. semantic — 쓰임새. 다크모드는 오직 이 층에서만 갈린다.
   =========================================================================== */
:root {
  --bg-canvas:  var(--gray-0);
  --bg-surface: var(--gray-0);
  --bg-raised:  var(--gray-0);
  --bg-inset:   var(--gray-50);
  --bg-hover:   var(--gray-100);
  --bg-active:  var(--gray-150);

  --fg-default: var(--gray-900);
  --fg-muted:   var(--gray-500);
  --fg-subtle:  var(--gray-400);
  --fg-onaccent: var(--gray-0);

  --border-default: var(--gray-200);
  --border-subtle:  var(--gray-150);
  --border-strong:  var(--gray-300);

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

TOKENS_CSS = _TOKENS_TEMPLATE.replace("__DARK__", _DARK)
