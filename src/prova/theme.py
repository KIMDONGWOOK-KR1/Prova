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

import re

_DARK = """    --bg-canvas:  #000000;
    --bg-surface: #000000;
    --bg-workspace: #000000;
    --bg-sidebar: #16181c;
    --bg-raised:  #202327;
    --bg-inset:   #16181c;
    --bg-hover:   #1d1f23;
    --bg-active:  #2f3336;

    --fill-group:    rgba(231, 233, 234, 0.05);
    --fill-hover:    rgba(231, 233, 234, 0.07);
    --fill-selected: rgba(231, 233, 234, 0.12);
    --fill-track:    rgba(231, 233, 234, 0.08);
    --fill-row-alt:  rgba(231, 233, 234, 0.04);
    --sep:           rgba(231, 233, 234, 0.12);
    --control-line:  rgba(231, 233, 234, 0.14);

    --fg-default: #e7e9ea;
    --fg-muted:   #8b98a5;
    --fg-subtle:  #8b98a5;
    --fg-faint:   rgba(231, 233, 234, 0.25);
    --fg-onaccent: #ffffff;

    --border-default: #2f3336;
    --border-subtle:  #202327;
    --border-strong:  #536471;

    --accent-blue:   #1d9bf0;
    --accent-fg:     #1d9bf0;
    --accent-solid:  #0d77bf;
    --accent-hover:  #0c71b6;
    --accent-bg:     rgba(29, 155, 240, 0.18);
    --accent-border: #1d9bf0;

    --pass-fg: #37acb8;
    --pass-bg: #001a1d;
    --fail-fg: #fb726b;
    --fail-bg: #250e0d;
    --warn-fg: #c79536;
    --warn-bg: #1f1401;
    --info-fg: #e7e9ea;
    --info-bg: #16181c;
    --note-fg: #af8bec;
    --note-bg: #191125;
    --unv-fg:  #8fa0ab;
    --fg-onverdict: #000000;

    --chart-pass:   #37acb8;
    --chart-weak:   #c79536;
    --chart-defect: #fb726b;
    --chart-infra:  #af8bec;
    --chart-unv:    #8fa0ab;

    --bg-bar: rgba(0, 0, 0, 0.72);
    --shadow-control: 0 0 0 0.5px rgba(255, 255, 255, 0.10), 0 1px 2px rgba(0, 0, 0, 0.40);
    --shadow-window:  0 0 0 1px rgba(255, 255, 255, 0.16), 0 10px 40px rgba(0, 0, 0, 0.55);
    --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.4);
    --shadow-md: 0 2px 8px rgba(0, 0, 0, 0.45);
    --shadow-lg: 0 8px 28px rgba(0, 0, 0, 0.5);
    --scrim: rgba(0, 0, 0, 0.40);

    --focus-ring: 0 0 0 3px rgba(29, 155, 240, 0.55);"""

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
     시스템 글꼴이 없는 곳(윈도 등)에서는 함께 내주는 Pretendard Variable(/fonts, OFL)로 — Apple 글꼴은 라이선스상
     내보낼 수 없어 가장 비슷한 것을 쓴다(hh 11-25). 맥은 앞의 글꼴로 다 그려지므로 파일을 받지 않는다. */
  --font-sans: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Apple SD Gothic Neo", "Pretendard Variable", "Pretendard",
               "Segoe UI", "Malgun Gothic", system-ui, sans-serif;
  --font-mono: ui-monospace, "SF Mono", "Cascadia Mono", Menlo, Consolas,
               "D2Coding", monospace;
  /* 리포트(보고서 창·PDF) 글꼴 — Pretendard 를 리포트 폴더에 함께 둔다(fonts/, SIL OFL 1.1 이라 함께 보내도 된다).
     받는 사람이 윈도여도, 서버가 찍은 PDF 여도 같은 글꼴로 보인다. Apple SF·New York 은 라이선스가 Apple 기기
     화면 시안용이라 파일에 넣어 보낼 수 없다 — 맥에서는 Pretendard 가 없을 때만 시스템 글꼴(SF)로 넘어간다.
     (2026-11-25 hh) 웹 UI 는 시스템 글꼴 그대로(11-24 hh). */
  --font-doc: "Pretendard Variable", "Pretendard", -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo",
              "Segoe UI", "Malgun Gothic", system-ui, sans-serif;

  /* 4px 기준 간격 — 매직넘버를 쓰지 않기 위한 눈금 */
  --sp-1: 4px;  --sp-2: 8px;  --sp-3: 12px; --sp-4: 16px;
  --sp-5: 20px; --sp-6: 24px; --sp-8: 32px; --sp-10: 40px; --sp-12: 48px;

  /* 모서리 — 키트의 컨트롤 높이 16/20/24/28 에 4/5/6/7. 묶음 상자·사이드바 12, 창 16, 띄운 창 20.
     큰 버튼·도구 막대 버튼·꼬리표는 알약(r-full). */
  --r-sm: 4px; --r-md: 5px; --r-lg: 6px; --r-ctl-lg: 7px; --r-sel: 8px;
  --r-xl: 12px; --r-card: 12px; --r-window: 16px; --r-popover: 20px; --r-full: 999px;

  /* 컨트롤 높이 — 키트의 small 20 · regular 24 · large 28 · x-large 36 을 웹 데스크톱 눈금으로 한 칸씩
     올렸다(2026-11-24 hh '글자·카드 크기 최적화'). 손이 아니라 마우스로 누르지만, 키트 값 그대로면
     브라우저 안에서 입력 칸이 24px 로 작다. 입력·팝업·버튼 32, 큰 버튼 36. */
  --ctl-sm: 24px; --ctl-md: 28px; --ctl-lg: 32px; --ctl-xl: 36px;

  /* 글자 크기 — 키트의 글자 스타일 순서(Footnote · Subheadline · Callout · Body · Title 3 · 2 · 1 ·
     Large Title)는 그대로 두고, 값은 한글 웹 데스크톱에 맞춰 한 칸씩 올렸다(2026-11-24 hh).
     키트 본문 13px 은 맥 앱 기준이라 브라우저 속 한글로는 작다 — 한국 웹 서비스·개발 도구 웹앱
     (Mobbin·UIBowl 레퍼런스)이 쓰는 14px 를 본문으로, 메타 12px, 쪽 제목 24px, 숫자 칸 30px.
     2xs 11 · xs 12 · sm 13 · md 14 본문 · base 16 · lg 18 · xl 24 · 2xl 30 · 3xl 32.
     줄 높이: 12px 글 16, 13px 글 18, 본문 한 줄 20, 본문 문단 22, 16px 제목 22, 24px 제목 30. */
  --tx-2xs: 11px; --tx-xs: 12px; --tx-sm: 13px; --tx-md: 14px; --tx-base: 16px;
  --tx-lg: 18px; --tx-xl: 24px; --tx-2xl: 30px; --tx-3xl: 32px;
  --lh-xs: 16px; --lh-sm: 18px; --lh-row: 20px; --lh-para: 22px; --lh-title: 22px; --lh-xl: 30px;

  /* 움직임 — 상태가 바뀔 때만 쓴다(단계 이동·항목 완료·숫자 바뀜). 들어올 때 장식으로 쓰지 않는다.
     화면 설정에서 '동작 줄이기' 면 app.css 가 모두 끈다. */
  --dur-1: 150ms; --dur-2: 180ms; --dur-3: 250ms; --dur-4: 700ms;
  --ease-out: cubic-bezier(0.2, 0.7, 0.2, 1);
  --ease-roll: cubic-bezier(0.3, 0.5, 0.2, 1);
  /* 살짝 넘쳤다 돌아오는 끝 — 끌어 놓기 문서 카드가 벌어질 때만(21st.dev File Upload 의 spring) */
  --ease-spring: cubic-bezier(0.3, 1.35, 0.5, 1);

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
  --bg-sidebar: #f7f8f8;
  --bg-raised:  #ffffff;   /* 팝업·입력칸·버튼 같은 컨트롤 면 */
  --bg-inset:   #f7f9f9;   /* 묶음 상자(Group Box)와 같은 3% 회색을 불투명하게 */
  --bg-hover:   #eff3f4;
  --bg-active:  #e1e8ed;

  /* 키트의 채움(Fills)은 투명도다 — 어느 바탕 위에 놓여도 같은 깊이로 보인다. */
  --fill-group:    rgba(15, 20, 25, 0.03);
  --fill-hover:    rgba(15, 20, 25, 0.05);
  --fill-selected: rgba(15, 20, 25, 0.09);
  --fill-track:    rgba(15, 20, 25, 0.05);
  --fill-row-alt:  rgba(15, 20, 25, 0.025);
  --sep:           rgba(15, 20, 25, 0.08);
  --control-line:  rgba(15, 20, 25, 0.12);

  /* 글자 — 키트 라벨은 검정 85/50/25%. 50%(보조 라벨)는 흰 바탕에서 3.9:1 이라 #616161(6.2:1)로 올렸다.
     subtle 은 사이드바(#f0f0f2) 위에서도 4.6:1. faint(25%)는 글자가 아닌 곳(빈 체크·자리 표시)에만. */
  --fg-default: #0f1419;
  --fg-muted:   #536471;
  --fg-subtle:  #5b7083;
  --fg-faint:   rgba(15, 20, 25, 0.25);
  --fg-onaccent: #ffffff;

  --border-default: #e1e8ed;
  --border-subtle:  #eff3f4;
  --border-strong:  #cfd9de;

  /* 강조는 macOS 기본 파랑 하나다(키트 #0088ff). 진행 막대·선택 점처럼 글자가 아닌 곳은 그대로,
     흰 글자를 얹는 기본 버튼·선택 줄은 키트의 Selection Focused #0069f9(흰 글자 4.8:1),
     파란 글자(링크)는 사이드바 위에서도 4.7:1 이 되게 #0062e6. 주황은 쓰지 않는다. */
  --accent-blue:   #1d9bf0;
  --accent-fg:     #0c71b6;
  --accent-solid:  #0d77bf;
  --accent-hover:  #0c6aaa;
  --accent-bg:     rgba(29, 155, 240, 0.12);
  --accent-border: #1d9bf0;

  /* 판정 색 — 한 가족(hh 11-25: 통과는 초록 대신 청록, 나머지도 청록에 맞춰). 로고·강조 파랑(#1d9bf0, --accent-*)은 그대로.
     글자 색은 모두 같은 대비(흰 바탕 약 5.25:1, 곧 같은 밝기), 차트 색은 모두 OKLCh 밝기 0.62, 채도는 중간 — 어느 색도 튀지 않게.
     색상: 통과 청록 205° · 기획서와 다름 산호 빨강 25°(청록의 보색) · 실행 문제 보라 300°(강조 파랑과 55° 떨어짐) ·
     약한 통과 황토 80° · 확인 불가 슬레이트 240°. 판정에만 쓰고 늘 글자(통과·기획서와 다름…)와 함께 놓는다.
     --fg-onverdict 는 판정 색 동그라미 위 그림(✓ ✕ ! −) — 밝게 흰색, 어둡게 검정. */
  --pass-fg: #067782;
  --pass-bg: #e4f9fb;
  --fail-fg: #c83435;
  --fail-bg: #fef1f0;
  --warn-fg: #8d6411;
  --warn-bg: #fcf3e4;
  --info-fg: #0f1419;
  --info-bg: #f7f9f9;
  --note-fg: #7f58b9;
  --note-bg: #f6f2fe;
  --unv-fg:  #5f6e79;
  --fg-onverdict: #ffffff;

  /* 차트 색 — 면으로 칠하는 곳(진행 막대·도넛). 페이지와 카드 바탕에 3:1 이상. */
  --chart-pass:   #0d98a4;
  --chart-weak:   #ad7c0e;
  --chart-defect: #e64343;
  --chart-infra:  #976ad9;
  --chart-unv:    #798994;

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
  --focus-ring: 0 0 0 3px rgba(29, 155, 240, 0.45);
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


def light_value(name: str) -> str:
    """밝은 화면에서 토큰 하나의 값 (예: '--fail-fg' → '#d70015').

    CSS 변수를 읽지 못하는 곳 — 엑셀 셀 색(xlsx_export), PDF 쪽 꼬리말(pdf_export) — 도 색을 여기서만
    가져간다. 값을 그쪽에 다시 적으면 두 벌이 된다. 밝은 값이 다크 블록보다 먼저 적혀 있으므로 처음
    나오는 정의가 밝은 값이다.
    """
    m = re.search(rf"^\s*{re.escape(name)}:\s*([^;]+);", TOKENS_CSS, re.M)
    if not m:
        raise KeyError(name)
    return m.group(1).strip()
