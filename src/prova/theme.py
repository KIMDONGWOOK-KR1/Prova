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

_DARK = """    --bg-canvas:  #1e1e1e;
    --bg-surface: #1e1e1e;
    --bg-workspace: #1e1e1e;
    --bg-sidebar: #262628;
    --bg-raised:  #3a3a3c;
    --bg-inset:   #252525;
    --bg-hover:   #2a2a2b;
    --bg-active:  #353536;

    --fill-group:    rgba(255, 255, 255, 0.04);
    --fill-hover:    rgba(255, 255, 255, 0.06);
    --fill-selected: rgba(255, 255, 255, 0.10);
    --fill-track:    rgba(255, 255, 255, 0.07);
    --fill-row-alt:  rgba(255, 255, 255, 0.04);
    --sep:           rgba(255, 255, 255, 0.08);
    --control-line:  rgba(255, 255, 255, 0.10);

    --fg-default: #dddddd;
    --fg-muted:   #a3a3a8;
    --fg-subtle:  #98989d;
    --fg-faint:   rgba(255, 255, 255, 0.25);
    --fg-onaccent: #ffffff;

    --border-default: #383839;
    --border-subtle:  #2e2e2f;
    --border-strong:  #4d4d4f;

    --accent-blue:   #0a84ff;
    --accent-fg:     #4ea1ff;
    --accent-solid:  #0a6fe0;
    --accent-hover:  #0a62c8;
    --accent-bg:     rgba(10, 132, 255, 0.20);
    --accent-border: #0a84ff;

    --pass-fg: #32d74b;
    --pass-bg: #183520;
    --fail-fg: #ff6961;
    --fail-bg: #43231f;
    --warn-fg: #e3ad4a;
    --warn-bg: #33280f;
    --info-fg: #dddddd;
    --info-bg: #252525;
    --note-fg: #d48eff;
    --note-bg: #33233d;
    --unv-fg:  #98989d;

    --chart-pass:   #32d74b;
    --chart-weak:   #d9a441;
    --chart-defect: #ff6961;
    --chart-infra:  #bf8ee8;
    --chart-unv:    #8e8e93;

    --bg-bar: rgba(44, 44, 46, 0.78);
    --shadow-control: 0 0 0 0.5px rgba(255, 255, 255, 0.10), 0 1px 2px rgba(0, 0, 0, 0.40);
    --shadow-window:  0 0 0 1px rgba(255, 255, 255, 0.16), 0 10px 40px rgba(0, 0, 0, 0.55);
    --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.4);
    --shadow-md: 0 2px 8px rgba(0, 0, 0, 0.45);
    --shadow-lg: 0 8px 28px rgba(0, 0, 0, 0.5);
    --scrim: rgba(0, 0, 0, 0.40);

    --focus-ring: 0 0 0 3px rgba(10, 132, 255, 0.55);"""

_TOKENS_TEMPLATE = """
/* ===========================================================================
   1. primitive — 원시값. 여기서만 '모양' 을 만든다.
      값은 Apple macOS 27 UI Kit(Figma, 2026-11-24 hh 가 준 .fig)에서 읽었다. 웹에서 글자 대비
      4.5:1 을 못 넘는 키트 값은 Apple 의 '대비 높임' 색으로 바꿨다(아래 semantic 층에 적었다).
   =========================================================================== */
:root {
  /* 회색은 중성이다 — 키트의 라벨·채움은 검정/흰색의 투명도라 색기가 없다. */
  --gray-0:   #ffffff;
  --gray-25:  #fbfbfb;
  --gray-50:  #f7f7f7;
  --gray-100: #f0f0f2;
  --gray-150: #e5e5e5;
  --gray-200: #d6d6d6;
  --gray-300: #bfbfbf;
  --gray-350: #a3a3a8;
  --gray-400: #8e8e93;
  --gray-500: #6b6b6b;
  --gray-550: #6b6b6b;
  --gray-600: #616161;
  --gray-700: #474747;
  --gray-800: #333333;
  --gray-900: #262626;
  --gray-950: #1e1e1e;

  /* Apple HIG(Typography): 시스템 글꼴 — 맥에서는 SF Pro + Apple SD Gothic Neo. 키트도 SF Pro 다.
     시스템 글꼴이 없는 곳(윈도)에서만 다음 글꼴로 넘어간다. */
  --font-sans: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Apple SD Gothic Neo", "Pretendard",
               "Segoe UI", "Malgun Gothic", system-ui, sans-serif;
  --font-mono: ui-monospace, "SF Mono", "Cascadia Mono", Menlo, Consolas,
               "D2Coding", monospace;

  /* 4px 기준 간격 — 매직넘버를 쓰지 않기 위한 눈금 */
  --sp-1: 4px;  --sp-2: 8px;  --sp-3: 12px; --sp-4: 16px;
  --sp-5: 20px; --sp-6: 24px; --sp-8: 32px; --sp-10: 40px; --sp-12: 48px;

  /* 모서리 — 키트의 컨트롤 높이 16/20/24/28 에 4/5/6/7. 묶음 상자·사이드바 12, 창 16, 띄운 창 20.
     큰 버튼·도구 막대 버튼·꼬리표는 알약(r-full). */
  --r-sm: 4px; --r-md: 5px; --r-lg: 6px; --r-ctl-lg: 7px; --r-sel: 8px;
  --r-xl: 12px; --r-card: 12px; --r-window: 16px; --r-popover: 20px; --r-full: 999px;

  /* 컨트롤 높이 — 키트 mini 16 · small 20 · regular 24 · large 28 · x-large 36 */
  --ctl-sm: 20px; --ctl-md: 24px; --ctl-lg: 28px; --ctl-xl: 36px;

  /* 글자 크기 — 키트의 글자 스타일. 2xs 10 Footnote · xs 11 Subheadline · sm 12 Callout ·
     md 13 Body(본문) · base 15 Title 3 · lg 17 Title 2 · xl 22 Title 1 · 2xl/3xl 26 Large Title.
     본문은 키트 그대로 13px(2026-11-24 hh). 한 줄짜리는 16px 줄 높이, 여러 줄 문단은 18px. */
  --tx-2xs: 10px; --tx-xs: 11px; --tx-sm: 12px; --tx-md: 13px; --tx-base: 15px;
  --tx-lg: 17px; --tx-xl: 22px; --tx-2xl: 26px; --tx-3xl: 26px;
  --lh-row: 16px; --lh-para: 18px;

  /* 움직임 — 상태가 바뀔 때만 쓴다(단계 이동·항목 완료·숫자 바뀜). 들어올 때 장식으로 쓰지 않는다.
     화면 설정에서 '동작 줄이기' 면 app.css 가 모두 끈다. */
  --dur-1: 150ms; --dur-2: 180ms; --dur-3: 250ms; --dur-4: 700ms;
  --ease-out: cubic-bezier(0.2, 0.7, 0.2, 1);
  --ease-roll: cubic-bezier(0.3, 0.5, 0.2, 1);

  --lh-tight: 1.35; --lh-normal: 1.5; --lh-relaxed: 1.65;
}

/* ===========================================================================
   2. semantic — 쓰임새. 다크모드는 오직 이 층에서만 갈린다.
   =========================================================================== */
:root {
  /* 창 바탕(Window Background)은 흰색, 띄운 사이드바는 그보다 한 단계 어둡다. */
  --bg-canvas:  #ffffff;
  --bg-surface: #ffffff;
  --bg-workspace: #ffffff;
  --bg-sidebar: #f0f0f2;
  --bg-raised:  #ffffff;   /* 팝업·입력칸·버튼 같은 컨트롤 면 */
  --bg-inset:   #f7f7f7;   /* 묶음 상자(Group Box)와 같은 3% 회색을 불투명하게 */
  --bg-hover:   #f2f2f2;
  --bg-active:  #e6e6e6;

  /* 키트의 채움(Fills)은 투명도다 — 어느 바탕 위에 놓여도 같은 깊이로 보인다. */
  --fill-group:    rgba(0, 0, 0, 0.03);
  --fill-hover:    rgba(0, 0, 0, 0.05);
  --fill-selected: rgba(0, 0, 0, 0.10);
  --fill-track:    rgba(0, 0, 0, 0.05);
  --fill-row-alt:  rgba(0, 0, 0, 0.03);
  --sep:           rgba(0, 0, 0, 0.08);
  --control-line:  rgba(0, 0, 0, 0.12);

  /* 글자 — 키트 라벨은 검정 85/50/25%. 50%(보조 라벨)는 흰 바탕에서 3.9:1 이라 #616161(6.2:1)로 올렸다.
     subtle 은 사이드바(#f0f0f2) 위에서도 4.6:1. faint(25%)는 글자가 아닌 곳(빈 체크·자리 표시)에만. */
  --fg-default: #262626;
  --fg-muted:   #616161;
  --fg-subtle:  #6b6b6b;
  --fg-faint:   rgba(0, 0, 0, 0.25);
  --fg-onaccent: #ffffff;

  --border-default: #e5e5e5;
  --border-subtle:  #ededed;
  --border-strong:  #c7c7c7;

  /* 강조는 macOS 기본 파랑 하나다(키트 #0088ff). 진행 막대·선택 점처럼 글자가 아닌 곳은 그대로,
     흰 글자를 얹는 기본 버튼·선택 줄은 키트의 Selection Focused #0069f9(흰 글자 4.8:1),
     파란 글자(링크)는 사이드바 위에서도 4.7:1 이 되게 #0062e6. 주황은 쓰지 않는다. */
  --accent-blue:   #0088ff;
  --accent-fg:     #0062e6;
  --accent-solid:  #0069f9;
  --accent-hover:  #005ce0;
  --accent-bg:     rgba(0, 136, 255, 0.12);
  --accent-border: #0088ff;

  /* 판정 색 — Apple 시스템 색의 '대비 높임' 값. 초록만 키트 값(#248a3d, 4.4:1)을 한 단계 더 눌렀다.
     색은 판정에만 쓰고 늘 글자(통과·기획서와 다름…)와 함께 놓는다. */
  --pass-fg: #1f7a36;
  --pass-bg: #e9f5ec;
  --fail-fg: #d70015;
  --fail-bg: #ffebea;
  --warn-fg: #8a5d0a;
  --warn-bg: #fbf3e0;
  --info-fg: #262626;
  --info-bg: #f7f7f7;
  --note-fg: #8944ab;
  --note-bg: #f5eefa;
  --unv-fg:  #6b6b70;

  /* 비율 막대·리포트 도넛. 면으로 칠하는 색이라 바탕과 3:1 이상(확인 불가 회색만 3.3:1). */
  --chart-pass:   #248a3d;
  --chart-weak:   #b07d14;
  --chart-defect: #d70015;
  --chart-infra:  #8944ab;
  --chart-unv:    #8e8e93;

  /* 컨트롤 층(도구 막대)의 반투명 재질 — Apple HIG Materials: 재질은 내용 위에 뜬 컨트롤에만.
     '투명도 줄이기'·'대비 높이기' 에서는 불투명으로 바뀐다(아래). */
  --bg-bar: rgba(255, 255, 255, 0.78);

  /* 그림자는 컨트롤의 얇은 테두리와 띄운 창(경고창·팝오버)에만 — 키트와 같다. 카드에는 없다. */
  --shadow-control: 0 0 0 0.5px rgba(0, 0, 0, 0.14), 0 1px 2px rgba(0, 0, 0, 0.10);
  --shadow-window:  0 0 0 0.5px rgba(0, 0, 0, 0.18), 0 10px 40px rgba(0, 0, 0, 0.22);
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.06);
  --shadow-md: 0 2px 8px rgba(0, 0, 0, 0.08);
  --shadow-lg: 0 8px 28px rgba(0, 0, 0, 0.12);
  --scrim: rgba(0, 0, 0, 0.18);

  /* macOS 키보드 초점 고리 — 강조 파랑 3px */
  --focus-ring: 0 0 0 3px rgba(0, 136, 255, 0.45);
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

_MORE_LIGHT = """    --fg-muted:   #474747;
    --fg-subtle:  #555555;
    --sep: rgba(0, 0, 0, 0.22);
    --control-line: rgba(0, 0, 0, 0.35);
    --border-default: #8e8e93;
    --border-subtle:  #bfbfbf;
    --border-strong:  #616161;
    --bg-bar: var(--bg-surface);"""

_MORE_DARK = """    --fg-muted:   #c7c7cc;
    --fg-subtle:  #b5b5ba;
    --sep: rgba(255, 255, 255, 0.24);
    --control-line: rgba(255, 255, 255, 0.35);
    --border-default: #6b6b6b;
    --border-subtle:  #474747;
    --border-strong:  #8e8e93;
    --bg-bar: var(--bg-surface);"""

TOKENS_CSS = (_TOKENS_TEMPLATE.replace("__DARK__", _DARK)
              .replace("__MORE_LIGHT__", _MORE_LIGHT).replace("__MORE_DARK__", _MORE_DARK))
