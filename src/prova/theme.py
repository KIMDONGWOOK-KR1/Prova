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

TOKENS_CSS = """
/* ===========================================================================
   1. primitive — 원시값. 여기서만 색을 만든다.
   =========================================================================== */
:root {
  --gray-0:   #ffffff;
  --gray-25:  #fcfcfd;
  --gray-50:  #f7f8fa;
  --gray-100: #f1f3f6;
  --gray-150: #e8ebf0;
  --gray-200: #dde1e8;
  --gray-300: #c6ccd6;
  --gray-400: #97a0ae;
  --gray-500: #6c7482;
  --gray-600: #525a68;
  --gray-700: #3c434f;
  --gray-800: #272d37;
  --gray-900: #171b22;
  --gray-950: #0e1116;

  --indigo-100: #e8ebfb;
  --indigo-200: #ccd3f6;
  --indigo-400: #8b98e8;
  --indigo-500: #5b6ad6;
  --indigo-600: #4655c0;
  --indigo-700: #38449c;

  --green-100: #e3f3ea;
  --green-500: #16875c;
  --green-600: #0f6b48;
  --green-400: #4ec38a;

  --red-100: #fceceb;
  --red-500: #c33a30;
  --red-600: #a32d25;
  --red-400: #ef8b81;

  --amber-100: #fbf1dd;
  --amber-500: #96660c;
  --amber-400: #d9a441;

  --violet-100: #f0ecfa;
  --violet-500: #6a48ab;
  --violet-400: #ab92e0;

  --font-sans: "Pretendard", -apple-system, BlinkMacSystemFont, "Segoe UI",
               "Malgun Gothic", "Apple SD Gothic Neo", system-ui, sans-serif;
  --font-mono: "Cascadia Mono", "SF Mono", ui-monospace, Consolas,
               "D2Coding", "Menlo", monospace;

  /* 4px 기준 간격 — 매직넘버를 쓰지 않기 위한 눈금 */
  --sp-1: 4px;  --sp-2: 8px;  --sp-3: 12px; --sp-4: 16px;
  --sp-5: 20px; --sp-6: 24px; --sp-8: 32px; --sp-10: 40px; --sp-12: 48px;

  --r-sm: 4px; --r-md: 6px; --r-lg: 8px; --r-xl: 12px; --r-full: 999px;

  --tx-xs: 11px; --tx-sm: 12px; --tx-md: 13px; --tx-base: 14px;
  --tx-lg: 16px; --tx-xl: 20px; --tx-2xl: 26px;

  --lh-tight: 1.35; --lh-normal: 1.55; --lh-relaxed: 1.7;
}

/* ===========================================================================
   2. semantic — 쓰임새. 다크모드는 오직 이 층에서만 갈린다.
   =========================================================================== */
:root {
  --bg-canvas:  var(--gray-50);
  --bg-surface: var(--gray-0);
  --bg-raised:  var(--gray-0);
  --bg-inset:   var(--gray-100);
  --bg-hover:   var(--gray-100);
  --bg-active:  var(--gray-150);

  --fg-default: var(--gray-900);
  --fg-muted:   var(--gray-500);
  --fg-subtle:  var(--gray-400);
  --fg-onaccent: #ffffff;

  --border-default: var(--gray-200);
  --border-subtle:  var(--gray-150);
  --border-strong:  var(--gray-300);

  --accent-fg:     var(--indigo-600);
  --accent-solid:  var(--indigo-500);
  --accent-hover:  var(--indigo-600);
  --accent-bg:     var(--indigo-100);
  --accent-border: var(--indigo-200);

  --pass-fg: var(--green-500);
  --pass-bg: var(--green-100);
  --fail-fg: var(--red-500);
  --fail-bg: var(--red-100);
  --warn-fg: var(--amber-500);
  --warn-bg: var(--amber-100);
  --info-fg: var(--indigo-600);
  --info-bg: var(--indigo-100);
  --note-fg: var(--violet-500);
  --note-bg: var(--violet-100);

  --shadow-sm: 0 1px 2px rgba(16, 20, 28, 0.05);
  --shadow-md: 0 2px 8px rgba(16, 20, 28, 0.07);
  --shadow-lg: 0 8px 28px rgba(16, 20, 28, 0.10);

  --focus-ring: 0 0 0 3px rgba(91, 106, 214, 0.32);
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg-canvas:  var(--gray-950);
    --bg-surface: #14171d;
    --bg-raised:  #1a1e26;
    --bg-inset:   #0b0d11;
    --bg-hover:   #1e232c;
    --bg-active:  #262c37;

    --fg-default: #e7eaf0;
    --fg-muted:   var(--gray-400);
    --fg-subtle:  var(--gray-500);

    --border-default: #272d37;
    --border-subtle:  #1e232c;
    --border-strong:  #363d49;

    --accent-fg:     var(--indigo-400);
    --accent-solid:  var(--indigo-500);
    --accent-hover:  var(--indigo-400);
    --accent-bg:     #1b2140;
    --accent-border: #2c3462;

    --pass-fg: var(--green-400);
    --pass-bg: #0f2a1f;
    --fail-fg: var(--red-400);
    --fail-bg: #2c1614;
    --warn-fg: var(--amber-400);
    --warn-bg: #271e0e;
    --info-fg: var(--indigo-400);
    --info-bg: #1b2140;
    --note-fg: var(--violet-400);
    --note-bg: #221a35;

    --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.4);
    --shadow-md: 0 2px 8px rgba(0, 0, 0, 0.45);
    --shadow-lg: 0 8px 28px rgba(0, 0, 0, 0.5);

    --focus-ring: 0 0 0 3px rgba(139, 152, 232, 0.30);
  }
}

/* ===========================================================================
   3. 레거시 별칭 — 리포트 CSS 의 옛 이름을 새 semantic 으로 잇는다.
      이 별칭이 있는 한 UI 와 리포트의 색이 두 벌로 갈라질 수 없다.
   =========================================================================== */
:root {
  --bg:      var(--bg-canvas);
  --card:    var(--bg-surface);
  --line:    var(--border-default);
  --text:    var(--fg-default);
  --muted:   var(--fg-muted);
  --accent:  var(--accent-fg);
  --pass:    var(--pass-fg);
  --fail:    var(--fail-fg);
}
"""
