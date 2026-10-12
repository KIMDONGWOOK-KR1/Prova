# 외부 사이트 기획서 16개 (2026-09-22 ~ 09-27 작성, 10-12 복원)

외부 사이트 측정 세 번([1차](../external-sites-2026-09-23.md) · [2차](../external-sites-2-2026-09-27.md) ·
[3차](../external-sites-3-2026-09-28.md))에 쓴 기획서 원문이다. 당시에는 세션 임시 폴더에만 두어
사라졌고, 2026-10-12 에 Claude Code 대화 기록에서 원문을 꺼내 **글자 그대로** 복원했다.
기록에 남은 것은 처음 쓴 원문과 그 뒤에 적용한 `sed` 치환이다. 그 치환을 그대로 다시 적용해 나머지 판을 만들었다.
PDF 는 `scripts/make_spec_pdf.py` 로 다시 만들었다. 지금 변환기로 만든 것이라 당시 PDF 와 바이트까지 같지는 않다.

09-28 모델 비교에서 쓴 "외부 기획서 16개"(`ext_all/*_spec.pdf`)가 바로 이 16개다.
**화면으로 세면 10개**다. 나머지 6개는 같은 화면을 고쳐 쓴 판이다.

## 목록

| 파일 | 사이트 · 화면 | 판 | 앞 판과 다른 점 | 케이스 수* |
|---|---|---|---|---|
| `pta_login_spec` | practicetestautomation.com `/practice-test-login/` | 1 | — | 2 |
| `pta_login2_spec` | 〃 | 2 | 계정·예시 표 머리글을 라벨(`Username \| Password`)과 맞춤 | 4 |
| `herokuapp_login_spec` | the-internet.herokuapp.com `/login` | 1 | — | 2 |
| `herokuapp_login2_spec` | 〃 | 2 | 위와 같음 | 4 |
| `saucedemo_login_spec` | www.saucedemo.com `/` | 1 | — | 5 |
| `saucedemo_login2_spec` | 〃 | 2 | 위와 같음 | 7 |
| `expand_register_spec` | practice.expandtesting.com `/register` | 1 | — | 6 |
| `expand_register2_spec` | 〃 | 2 | 예시 아이디 `prova_probe_0923a` → `prova-probe-0923b` (`_` 가 사이트 규칙에 걸림, 가입한 아이디는 다시 못 씀) | 6 |
| `parabank_register_spec` | parabank.parasoft.com `/parabank/register.htm` | 1 | — | 13 |
| `parabank_register3_spec` | 〃 | 3 | 예시 아이디만 `…0923c` (다시 가입하려고) | 13 |
| `parabank_register4_spec` | 〃 | 4 | 예시 아이디만 `…0923d` | 13 |
| `ae_search_spec` | automationexercise.com `/products` 검색 | 1 | — | 7 |
| `tables_spec` | the-internet `/tables` | 1 | — | 2 |
| `tables_orderhead_spec` | 〃 | 비교용 | 절 제목만 '테스트 데이터' → '테스트 주문 데이터' (당시 도구가 이 제목만 알아봤는지 확인) | 2 |
| `webtables_spec` | demoqa.com `/webtables` | 1 | — | 7 |
| `inventory_spec` | saucedemo `/inventory.html` (로그인 전제 포함 2화면) | 1 | — | 10 |

\* 09-28 Qwen2.5-7B 로 뽑은 케이스 수(그때 도구 기준). 지금 도구로는 다를 수 있다.
`parabank_register2` 는 만들지 않았다. 번호를 건너뛴 것이다.

## 기대값의 출처 — 직접 확인할 때

기대값을 우리가 지어내지 않는다는 원칙으로 썼다. 다만 출처는 두 종류다.

**① 사이트가 공개한 테스트 케이스·계정을 옮긴 것** (10-12 에 사이트를 다시 열어 아래 문구가 그대로임을 확인했다)

| 기획서 | 확인할 곳 | 사이트가 적어 둔 것 |
|---|---|---|
| pta_login | https://practicetestautomation.com/practice-test-login/ | 계정 student / Password123, 테스트 케이스 3개: 성공 시 `/logged-in-successfully/` + "Congratulations", "Your username is invalid!", "Your password is invalid!" |
| herokuapp_login | https://the-internet.herokuapp.com/login | 안내문 "Enter tomsmith for the username and SuperSecretPassword! for the password." |
| expand_register | https://practice.expandtesting.com/test-cases/register | 공개 TC 4개: 성공 시 `/login` + "Successfully registered, you can log in now.", 빈 칸 2건 "All fields are required.", "Passwords do not match." |
| saucedemo_login · inventory | https://www.saucedemo.com/ | 로그인 화면 아래에 쓸 수 있는 아이디 목록(standard_user, locked_out_user …)과 비밀번호 secret_sauce |

**② 공개 문서 없이, 사이트를 직접 조작해 본 결과를 옮긴 것**

| 기획서 | 이렇게 확인했다 |
|---|---|
| herokuapp_login 의 오류 문구 · 성공 문구 | 틀린 값으로 로그인해 본 화면 ("Your username is invalid!", "You logged into a secure area!") |
| saucedemo_login 의 "Epic sadface: …" 문구 네 개 | 빈 칸·틀린 비밀번호·잠긴 계정으로 로그인해 본 화면 |
| parabank_register | 빈 폼을 제출해 본 칸별 필수 문구 10개, 비밀번호 불일치 문구, 가입 성공 문구 |
| ae_search | 검색해 본 결과 건수 (jeans 3, dress 9) |
| tables · webtables · inventory | 화면에 보이는 표 내용·상품 6개·가격·정렬 선택지 |

② 는 "사이트가 그렇게 동작했다" 는 관찰이지 사이트가 약속한 명세가 아니다. 사이트가 바뀌면
기대값도 바뀐다(데모용 데이터를 바꾸는 사이트도 있다).

## 왜 이 사이트들인가

출발점은 **도구와 대상을 같은 사람이 만들었다**는 문제였다. 그때까지 검증 대상은 전부 우리가 만든
SUT 였고, 같은 사람이 만들면 도구가 못 다루는 마크업은 애초에 SUT 에 들어가지 않는다. 실물 기획서를
기다리는 동안 대상 쪽만이라도 남이 만든 것으로 바꿔 보려고 골랐다. 고른 기준은 다음과 같다.

1. **자동화 테스트 연습용으로 공개된 사이트다.** 자동 실행·가입·로그인을 반복해도 되는 곳이라 허락
   문제가 없다. 요청도 사이트당 수십 번 이내였다.
2. **정답을 우리가 정하지 않아도 된다.** 테스트 계정과 기대 문구를 사이트가 공개한 곳을 먼저 골랐다(①).
   공개 문서가 없는 곳(②)은 실제 동작을 한 번 확인해서 적었고, 측정 기록에도 그렇게 밝혔다.
3. **우리 SUT 에 없던 마크업을 하나씩 가져온다.** 같은 모양을 여러 번 재지 않도록 했다.

| 차수 | 사이트 · 화면 | 이 화면을 고른 이유 (우리 SUT 에 없던 모양) |
|---|---|---|
| 1차 로그인 | practicetestautomation | 기대 문구가 늘 화면에 공개되어 있고, 오류 칸이 문구를 담은 채 숨어 있다 → 숨은 글자로 통과시키는지 |
| | the-internet | 서버 렌더링, 버튼 글자 앞에 아이콘 글꼴(`<i class="fa">`) |
| | saucedemo | React SPA, `<label>` 없이 placeholder·`data-test` 만 있음 |
| 2차 로그인 밖 | expandtesting 가입 | 공개 TC 4개, 오류가 `div.alert-danger`, 한 번 쓴 아이디는 다시 못 씀(1회성 데이터) |
| | parabank 가입 | `<label>` 없이 표 칸의 굵은 글씨로 이름이 붙은 11칸 폼, 오류가 `span.error` |
| | automationexercise 검색 | 글자 없는 아이콘 검색 버튼, 광고 스크립트의 콘솔 오류, 다른 목록 마크업에서 건수 세기 |
| 3차 표를 보여 주는 화면 | the-internet 표 | 같은 머리글의 이름 없는 `<table>` 두 개 |
| | demoqa 표 | 검색어를 치는 즉시 거르는 표 — 조회 버튼이 없음 |
| | saucedemo 상품 목록 | 로그인 전제, `div` 카드 목록, 정렬 select, 정상 화면인데 HTTP 404 |

차수마다 앞 차수의 한계에서 다음 대상을 정했다. 1차가 "로그인 화면만 봤다" 를 남겨 2차에서 가입·검색을 쟀고,
2차가 "표를 보여 주는 화면은 아직" 을 남겨 3차에서 표를 쟀다. 3차는 처음에 automationexercise 상품 목록을
후보로 냈다. 실제로는 로그인 전제와 정렬까지 볼 수 있는 saucedemo 상품 목록을 썼다.

## 실행

```
uv run prova run --pdf docs/measurements/external-specs/pta_login2_spec.pdf --url https://practicetestautomation.com
```

- 대상 URL 은 사이트 주소까지만 넣는다. 화면 경로는 기획서에 있다.
- 실물 모델(vLLM)이 필요하다. 이 기획서들에는 골든 정답이 없어 mock 으로는 못 돌린다.
- 가입 기획서(expand·parabank)를 다시 돌리려면 예시 아이디를 새 값으로 바꾸거나 `{고유}` 를 쓴다
  (예: `prova-{고유}` — 실행할 때마다 새 값으로 바뀐다).
- 결과는 `runs/` 가 아닌 곳(`--runs-root`)에 두기를 권한다. 외부 사이트는 바뀌기 때문이다.
