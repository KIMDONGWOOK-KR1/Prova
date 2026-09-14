# Prova 스터디 — 8주 커리큘럼 (2026-2학기)

> **대상** 인공지능학부 1학년 두 명 (파이썬 기초만, Windows) · **진행** 팀장 1인
> **시간** 주 1회 90분 · **시작** 2026-09-22(화), 정기회의 안 WE-Meet 슬롯
> **주 무대** Notion `Team. 소인배 > AI > AI 개발` DB. 이 파일은 그 원본이다.

CHEETAH GPU 를 반납해 개발이 멈춘 동안, 만들어 둔 것을 팀이 따라가며 이해하는 과정이다.

---

## 이 문서의 자리

| | |
|---|---|
| `docs/teaching/` 노트 24편 | **원본.** 개발하면서 쓴 글. 길고 순서가 개발 순서다 |
| 이 커리큘럼 | 그 24편을 **8회 90분으로 자른 읽는 순서.** 8편을 척추로 삼고 나머지는 "더 볼 것" 에 건다 |

노트를 대체하지 않는다. 매 회차의 팀장 선행학습이 곧 노트 읽기다.

## 설계 원칙 네 가지

1. **보이는 것에서 안쪽으로.** 파이프라인 순서(S1→S6)를 따르지 않는다. 1회차에
   도구를 돌려 리포트를 보고, 그다음 그 리포트가 어디서 나왔는지 거슬러 올라간다.
   S1(문서에서 규칙을 뽑는 단계)이 가장 추상적이라 6회차로 뺐다.
2. **매 회 손으로 돌리는 것 하나.** 실습 없는 회차는 만들지 않는다.
3. **GPU 없이 전부 돈다.** 모든 실습은 `--backend mock` 이다. CHEETAH 가 없어도
   파이프라인 전체가 끝까지 돈다 — 무엇이 mock 으로 대체되는지는 6회차에서 다룬다.
4. **끝에 만드는 것을 둔다.** 8회차에 기획서에 규칙을 하나 늘려, 도구가 그 규칙의
   누락을 실제로 짚어내는 것까지 손으로 확인한다.

---

## 8주 표

| 회 | 날짜 | 주제 | 한 줄 목표 | 팀장 선행학습 |
|---|---|---|---|---|
| 1 | 9/22 | 무엇을 만들었고 왜 만들었나 | 내 노트북에서 good/bad 리포트를 나란히 연다 | 노트 00 · `overview.html` |
| 2 | 9/29 | 6단계를 눈으로 따라간다 | 브라우저가 스스로 입력·클릭하는 것을 본다 | 노트 04 · `pipeline.py` |
| 3 | 10/6 | 데이터 계약 | 단계 사이에 흐르는 데이터의 모양을 안다 | 노트 01 · `models.py` |
| 4 | 10/13 | 규칙 하나당 케이스 하나 ⭐ | 이 프로젝트의 핵심 아이디어를 설명할 수 있다 | 노트 03 · `rule_expander.py` |
| 5 | 10/27 | 판정의 뒤집힌 논리 | 왜 에러가 떠야 PASS 인지 설명할 수 있다 | 노트 05 · `assertion_engine.py` |
| 6 | 11/3 | AI 를 어디에 쓰고 어디에 안 쓰는가 | mock 이 무엇을 대신하는지 안다 | 노트 02 · 03 |
| 7 | 11/10 | 도구가 스스로 틀리는 방식 ⭐ | 오탐을 직접 되살리고 없앤다 | 노트 15 · 12 |
| 8 | 11/17 | 화면에 규칙을 하나 늘린다 | 기획서 → 케이스 → 판정을 한 바퀴 돈다 | 노트 08 |

날짜는 화요일 기준 **잠정**이다. 중간고사 주(10/20 전후)를 한 주 비웠다 —
학사일정이 나오면 여기서 조정한다.

**한 주를 잃으면** 6회차를 7회차 앞머리 15분으로 줄여 붙인다. mock 설명은 7회차
실습에 어차피 필요하고, 6회차 실습(golden 비교)은 과제로 돌릴 수 있다.

---

## 1회차 — 무엇을 만들었고 왜 만들었나 (9/22)

**목표** 두 사람이 자기 노트북에서 `good` 과 `bad` 리포트를 열어 차이를 본다.

### 개념 (35분)

- 기획자가 "비밀번호는 8자 이상, 대문자 1자 이상" 이라 썼는데 개발자가 대문자
  검사를 빼먹었다. 지금 이걸 찾는 방법은 QA 담당자가 손으로 하나씩 넣어 보는 것뿐이다.
  화면 하나에 규칙 10개면 10번, 화면 20개면 200번, 코드가 바뀌면 처음부터 다시.
- Prova 는 기획서를 읽고 **규칙마다 그 규칙만 어기는 값**을 만들어, 진짜 크롬을 열어
  넣어 보고, 기획서가 지정한 에러가 뜨는지 본다.
- **`good` 과 `bad` 두 앱을 만든 이유.** 도구가 옳게 판정하는지 어떻게 아는가?
  결함을 심어 둔 앱과 안 심은 앱에 같은 기획서로 돌려, `good` 은 전부 통과하고
  `bad` 는 심어 둔 것만 짚는지 본다. **두 앱의 HTML 은 완전히 같고 검증 로직만 다르다** —
  변수를 하나만 두는 것.

`docs/teaching/overview.html` 을 브라우저로 열어 그림과 실행 GIF 를 함께 본다.

### 실습 (45분)

**사전 안내 (스터디 1주 전에 보낼 것)** — 아래 1·2번을 미리 끝내 오게 한다.
안 하면 90분이 설치로 다 간다. `playwright install chromium` 은 브라우저를
통째로 받으므로 회의실 와이파이에서 특히 오래 걸린다.

```powershell
# 1. 저장소 받기 (공개 저장소라 권한 신청 없이 clone 된다)
git clone https://github.com/KIMDONGWOOK-KR1/Prova.git
cd Prova

# 2. 의존성 + 브라우저 (여기까지 미리)
uv sync --extra dev
uv run playwright install chromium
```

```powershell
# 3. 기획서 PDF 생성 (md -> pdf)
uv run python scripts/make_spec_pdf.py

# 4. 테스트 대상 웹앱 띄우기 — 별도 터미널에서, 끄지 말 것
uv run uvicorn sut.app:app --port 8100 --reload --reload-dir sut

# 5. 브라우저로 http://localhost:8100 을 열어 good / bad 를 눈으로 먼저 본다

# 6. 같은 기획서로 두 앱을 검증한다
uv run prova run --pdf fixtures/specs/login_spec.pdf --url http://localhost:8100/good --backend mock
uv run prova run --pdf fixtures/specs/login_spec.pdf --url http://localhost:8100/bad  --backend mock

# 7. 리포트 두 개를 나란히 연다
start runs/<run-id>/report.html
```

### 🎯 체크포인트

- `good` 은 10건 전부 PASS, `bad` 는 3 PASS / 7 FAIL 이 나온다.
- FAIL 한 줄을 골라 읽고 **"개발자가 어느 검증을 빼먹었는지"** 를 말할 수 있는가?
- `bad` 의 FAIL 이 7건인데, `sut/app.py` 첫머리 표에 심어 둔 로그인 결함은 3개다.
  왜 숫자가 다른가? (한 결함이 여러 규칙 케이스를 무너뜨린다)

### 과제

노트 `docs/teaching/00-overview.md` 를 끝까지 읽고, **용어 사전에서 모르는 단어 3개**를
골라 온다. 다음 주 시작할 때 그것부터 푼다.

---

## 2회차 — 6단계를 눈으로 따라간다 (9/29)

**목표** S1~S6 가 무엇을 받아 무엇을 내놓는지, 그리고 AI 가 어디에만 있는지 안다.

### 개념 (30분)

```
S1 기획서 PDF  → ScreenSpec (화면과 규칙)        ← AI 가 관여하는 유일한 곳
S2 ScreenSpec  → TestCase[] (넣어 볼 값들)       ← 순수 함수, AI 없음
S3 라벨        → 화면의 실제 요소                ← selector 로 찾는다
S4 실제 브라우저 조작 + 증거 수집(스크린샷·DOM)
S5 PASS / FAIL 판정                              ← AI 없음
S6 JSON + HTML 리포트
```

**판정에 AI 가 관여하는 곳은 없다.** 왜 그렇게 했는지가 4·5·6회차의 주제다.

### 실습 (50분)

```powershell
# 별도 터미널
uv run uvicorn sut.app:app --port 8100 --reload --reload-dir sut

# 브라우저 창을 띄우고 0.5초씩 늦춰, 케이스 하나만 실행한다
uv run prova run --pdf fixtures/specs/login_spec.pdf `
  --url http://localhost:8100/bad `
  --only require_uppercase --headed --slow 500

# --url 을 .../good 으로 바꿔 한 번 더. 같은 값을 넣었는데 뜨는 문구가 다르다
```

그다음 `runs/<run-id>/` 안을 직접 연다.

| 볼 것 | 무엇인가 |
|---|---|
| `report.json` 의 `summary` | 전체·통과·실패 수. 나중에 `settled` 도 여기서 본다 |
| 케이스 폴더 (`login-password-require_uppercase-006/`) | 스텝마다의 스크린샷과 DOM 스냅샷 |
| `report.html` | 위 둘을 사람이 읽게 조립한 것 |

### 🎯 체크포인트

- `--only` 가 아무 케이스도 못 고르면 실행이 **멈춘다**. 왜 빈 목록으로 진행하지
  않는가? (0건 실행 · 통과율 100% 리포트가 나온다 — 아무것도 검증하지 않은 초록불)

### 과제

`src/prova/pipeline.py` 를 열어 본다. 100줄 정도다. 위 6단계가 그대로 보이는지 확인.

---

## 3회차 — 데이터 계약 (10/6)

**목표** 단계 사이에 흐르는 데이터의 모양이 왜 미리 못 박혀 있는지 안다.

### 개념 (35분)

1학년에게 **클래스와 타입힌트가 첫 벽**이다. 여기에 시간을 넉넉히 쓴다.

- `src/prova/models.py` 가 파이프라인 전체의 "계약" 이다. S1 이 만들고 S2 가 받는
  것, S4 가 남기고 S5 가 읽는 것이 전부 여기 정의돼 있다.
- **pydantic** — 데이터 모양을 미리 정해 두고 어기면 바로 알려주는 도구.
- 가장 중요한 필드: `UIElement.constraints`. 기획서의 "8자 이상, 대문자 1자 이상"
  이 여기에 `{"min_length": 8, "require_uppercase": 1}` 로 들어온다.
  **다음 주 실습이 이 딕셔너리 하나에서 시작한다.**

### 실습 (45분)

```powershell
# 1. S1 이 만들어 내야 하는 '정답' 을 직접 본다
notepad fixtures\specs\login_spec.golden.json

# 2. 기획서 원문과 나란히 놓고 대응을 찾는다
notepad fixtures\specs\login_spec.md
```

```powershell
# 3. 계약을 어겨 본다 — 파이썬 대화형에서
uv run python
```

```python
from prova.models import UIElement
UIElement(element_id="email", type="input", label="이메일", required=True)   # OK
UIElement(element_id="email", type="없는유형", label="이메일", required=True) # ValidationError
```

### 🎯 체크포인트

- 기획서 md 의 비밀번호 규칙 4줄이 golden JSON 의 어느 부분이 되었는가?
- 이 검사가 없으면 무슨 일이 벌어지나? (AI 가 필드 이름을 멋대로 지어내도
  아무도 모른 채 다음 단계로 흘러간다)

### 과제

`models.py` 맨 위 docstring 을 읽는다. 코드보다 그 설명이 먼저다.

---

## 4회차 — 규칙 하나당 케이스 하나 ⭐ (10/13)

**목표** 이 프로젝트의 핵심 아이디어를 남에게 설명할 수 있다.

### 개념 (35분)

`src/prova/s2_case_generator/rule_expander.py` — **순수 함수다. AI 를 쓰지 않는다.**
규칙 하나를 받아 **그 규칙만 어기는 값** 하나를 만든다.

| 검사할 규칙 | 그 규칙만 어기는 값 | 기대 |
|---|---|---|
| 8자 이상 | `Aa1!aaa` (7자) | 에러가 떠야 함 |
| 대문자 포함 | `a1!aaaaa` (대문자만 없음) | 에러가 떠야 함 |
| 특수문자 포함 | `Aa1aaaaa` (특수문자만 없음) | 에러가 떠야 함 |

**왜 하나씩인가.** 최소 길이와 최대 길이를 한 케이스로 묶어 검사하면, 최소 쪽이
걸려 에러가 뜨고 **최대 검증이 없다는 사실이 가려진다.** 회원가입 `bad` 에 실제로
그 결함(닉네임 최소만 구현, 최대 없음)을 심어 뒀다.

### 실습 (45분)

```powershell
uv run pytest tests/test_rule_expander.py -v
```

테스트 이름이 한글이라 그대로 읽힌다. 어떤 규칙에서 어떤 값이 나오는지 목록으로 본다.

```powershell
uv run python
```

```python
from prova.s2_case_generator.rule_expander import violations_for_element
from prova.models import UIElement
e = UIElement(element_id="password", type="input", label="비밀번호", required=True,
              constraints={"min_length": 8, "require_uppercase": 1, "require_special": 1})
for v in violations_for_element(e):
    print(v)
# constraints 에서 규칙을 하나 빼고 다시 → 케이스가 하나 준다
```

**나오는 것 (실측)** — 규칙 3개인데 케이스는 **4개**다. `required`(비워 두기)가
하나 더 붙기 때문이다. `require_special` 을 지우고 다시 돌리면 3개가 된다.

```
Violation(rule='required',          value='')
Violation(rule='min_length',        value='Aa1!aaa')
Violation(rule='require_uppercase', value='a1!aaaaa')
Violation(rule='require_special',   value='Aa1aaaaa')
```

### 🎯 체크포인트

- 규칙을 하나 지우면 케이스가 정확히 하나 주는가?
- 이걸 AI 에게 시키면 안 되는 이유는? (같은 입력에 매번 다른 값이 나오면
  어제의 초록불과 오늘의 초록불이 같은 뜻이 아니게 된다)

### 과제

노트 03(`03-llm-vs-code.md`)을 읽는다. 이 프로젝트에서 가장 중요한 판단이다.

---

## 5회차 — 판정의 뒤집힌 논리 (10/27)

**목표** 왜 에러가 **떠야** PASS 인지, 그리고 오탐이 왜 가장 위험한지 설명할 수 있다.

### 개념 (35분)

- negative 케이스는 **일부러 규칙을 어기는 값**을 넣는다. 그러니 에러가 뜨는 것이
  정상이다 → **에러가 뜨면 PASS**, 안 뜨면 FAIL(검증이 빠졌다).
  처음 보면 반드시 헷갈린다. 여기서 시간을 쓴다.
- **오탐(false positive)** — 문제가 없는데 문제라고 보고하는 것.
  QA 도구에서 가장 위험하다. 한 번 거짓 경보를 내면 그다음 진짜 경보도 안 믿는다.
- **미탐(false negative)** — 문제가 있는데 놓치는 것.

### 실습 (45분)

```powershell
uv run pytest tests/test_assertion_engine.py -v
```

그리고 `report.html` 의 FAIL 한 줄을 골라, 그 문장이 어떻게 조립됐는지 코드에서 찾는다.

```
FAIL [require_uppercase] 비밀번호 대문자 포함 규칙 위반 (입력값 'a1!aaaaa') — 규칙 강제 여부 확인
     기획서에 적힌 'password' 의 'require_uppercase' 검증 규칙이 구현에서
     확인되지 않았습니다. (다른 문구가 노출됨: '로그인 정보를 확인해주세요.')
```

### 🎯 체크포인트

- 위 문장에서 **기획서가 말한 것 / 화면이 실제로 한 것** 을 각각 짚을 수 있는가?
- 개발자가 이 한 줄만 보고 어느 코드를 고쳐야 하는지 알 수 있는가?

### 과제

`bad` 리포트에서 PASS 3건이 왜 PASS 인지 각각 설명해 온다.

---

## 6회차 — AI 를 어디에 쓰고 어디에 안 쓰는가 (11/3)

**목표** `--backend mock` 이 무엇을 대신하고 있는지 정확히 안다.

### 개념 (35분)

- S1 은 두 단계다. **결정적 추출**(`pdf_parser.py`, pdfplumber, AI 없음)로 글자와
  표를 뽑고, 그다음 **LLM 구조화**로 그것을 `ScreenSpec` 모양에 맞춘다.
- **표는 코드가 읽는다.** 표에 적힌 사실(테스트 계정, 시드 데이터)을 AI 에게 맡기면
  값을 지어낸다. 실제로 겪었다(노트 09·14).
- **mock 이 대신하는 것.** GPU 가 없으니 `--backend mock` 을 쓰는데, 이건
  "LLM 이 완벽하게 동작했을 때" 를 흉내 내는 것이다 — PDF 이름 옆의
  `*_spec.golden.json` 을 그대로 돌려준다. **즉 지금까지 실습에서 S1 은 사실상
  건너뛰고 있었다.** 이게 8회차에서 golden 도 함께 고쳐야 하는 이유다.
- mock 은 fallback 이 아니다. vLLM 이 죽었을 때 조용히 mock 으로 넘어가면 리포트는
  초록불인데 아무 추론도 하지 않은 상태가 된다. 그래서 **명시적으로 지정할 때만** 쓰인다.

### 실습 (45분)

```powershell
uv run pytest tests/test_s1_golden.py -v
```

`fixtures/specs/` 에서 세 벌을 나란히 놓고 대응을 찾는다.

| 파일 | 무엇인가 |
|---|---|
| `login_spec.md` | 사람이 쓴 기획서 원문 |
| `login_spec.pdf` | 위를 PDF 로 만든 것 — S1 의 실제 입력 |
| `login_spec.golden.json` | S1 이 내놓아야 하는 정답 — mock 이 돌려주는 것 |

### 🎯 체크포인트

- 리포트 머리말의 `추출 백엔드: mock` 을 찾을 수 있는가? 왜 이걸 남기는가?
- GPU 가 돌아온다면 어느 명령이 어떻게 바뀌는가? (`--backend mock` 을 뺀다)

### 과제

없음. 다음 주가 무겁다.

---

## 7회차 — 도구가 스스로 틀리는 방식 ⭐ (11/10)

**목표** 오탐을 직접 되살리고, 무엇이 그것을 막고 있었는지 확인한다.

이 회차가 커리큘럼의 정점이다. 지금까지는 도구가 결함을 잡는 것을 봤고,
여기서는 **도구가 없는 결함을 만들어 내는 것**을 본다.

### 개념 (30분)

- 실물 웹앱은 제출 결과를 **나중에** 렌더한다. 기다리지 않고 DOM 을 보면
  "기획서가 지정한 에러가 안 뜬다" 로 판정한다 — **올바른 구현이 FAIL 이 되는 오탐.**
- `sut/` 에 `/slow` 변형을 만들어 그 상황을 재현했다. 검증 로직·문구·마크업이
  `good` 과 **완전히 같고**, 결과를 400ms 늦게 렌더하는 것 하나만 다르다.
- 고친 방법: **판정이 통과할 때까지, 상한까지 기다린다**(`settle_timeout_ms`).
  "DOM 이 안정될 때까지" 로는 안 됐다 — 그 이유가 노트 15 에 있다.

### 실습 (50분) — 실측으로 확인된 순서다

```powershell
# 별도 터미널
uv run uvicorn sut.app:app --port 8100 --reload --reload-dir sut

# [A] 기본 설정. /slow 는 good 과 판정이 같아야 한다
uv run prova run --pdf fixtures/specs/login_spec.pdf --url http://localhost:8100/slow --backend mock
```

→ **10 PASS / 0 FAIL.** `report.json` 의 `summary.settled` 가 **7** 이다 —
7개 케이스가 기다림 덕분에 살았다는 뜻이다.

```powershell
# [B] 기다림을 끄고 같은 것을 돌린다
Copy-Item configs\default.yaml configs\no-wait.yaml
# no-wait.yaml 을 열어 settle_timeout_ms: 2000  ->  0 으로 고친다

uv run prova run --pdf fixtures/specs/login_spec.pdf --url http://localhost:8100/slow `
  --backend mock --config configs\no-wait.yaml
```

→ **3 PASS / 7 FAIL, `settled: 0`.** **오탐 7건이 되살아난다.**
`/slow` 는 검증을 하나도 빠뜨리지 않았는데 도구가 7개를 "빠졌다" 고 보고한다.

```powershell
Remove-Item configs\no-wait.yaml   # 정리
```

### 🎯 체크포인트

- FAIL 사유를 읽어 보면 "에러가 전혀 노출되지 않음 — 구현이 이 규칙을 강제하지
  않는다" 라고 **자신 있게** 말한다. 이게 왜 무서운가?
- `settle_timeout_ms` 를 크게 하면 안전해지는데, 왜 무한정 늘리지 않는가?
- 이 오탐과 4회차의 "규칙을 묶으면 검증이 가려진다" 는 어떻게 다른가?
  (하나는 없는 결함을 만들고, 하나는 있는 결함을 덮는다)

### 과제

노트 15 의 "시도했다가 버린 설계" 절을 읽는다. 왜 'DOM 이 안정될 때까지' 가
답이 아니었는지.

---

## 8회차 — 화면에 규칙을 하나 늘린다 (11/17)

**목표** 기획서 → 케이스 → 판정을 한 바퀴 직접 돈다. 졸업 과제.

### 개념 (15분)

지금까지 본 것을 거꾸로 밟는다. **기획서에 규칙을 하나 더 적으면 무슨 일이 일어나는가?**

### 실습 (70분) — 세 단계 전부 실측으로 확인됐다

**⚠ 시작 전:** `git switch -c study-week8` 로 가지를 하나 만든다.
끝나면 `git checkout -- fixtures/specs sut/app.py` 로 되돌린다.

**1단계 — 기획서에 규칙을 적는다**

`fixtures/specs/login_spec.md` 의 비밀번호 절에 한 줄 추가:

```
- 최대 길이는 20자다.
```

표의 입력 검증 규칙 칸도 `8자 이상 20자 이하, ...` 로 고친다.

```powershell
uv run python scripts/make_spec_pdf.py
```

**2단계 — golden 에도 같은 규칙 (6회차에서 배운 것)**

`--backend mock` 은 golden 을 읽으므로 md 만 고치면 **아무 일도 일어나지 않는다.**
`fixtures/specs/login_spec.golden.json` 의 password `constraints` 에 추가:

```json
"max_length": 20
```

**3단계 — 돌린다**

```powershell
uv run uvicorn sut.app:app --port 8100 --reload --reload-dir sut   # 별도 터미널
uv run prova run --pdf fixtures/specs/login_spec.pdf --url http://localhost:8100/good --backend mock
```

→ **케이스 10개 → 11개.** 그리고 `good` 인데 **FAIL 1건**이 난다.

```
FAIL [max_length] 비밀번호 최대 길이 규칙 위반 (입력값 'Aa1!aaaaaaaaaaaaaaaaa')
```

**기획서에 규칙을 넣었는데 구현이 따라오지 않은 것을 도구가 즉시 짚었다.**
이 프로젝트가 증명하려는 명제 그 자체다.

**4단계 — 구현을 채운다**

`sut/app.py` 의 `check_password_rules` 에 한 줄:

```python
and len(pw) <= 20
```

다시 돌리면 **11/11 PASS.**

### 🎯 체크포인트

- 규칙 하나를 적었을 뿐인데 케이스가 정확히 하나 늘었다. 4회차의 그 원리다.
- 3단계에서 `good` 이 FAIL 한 것은 도구의 오류인가 아닌가?
- `--reload` 로 띄웠는데 4단계 후에도 결과가 안 바뀌면? → **아래 함정 참고**

### 마무리

8주를 돌아본다. 다루지 않은 것은 "더 볼 것" 표에 있다.

---

## 진행자가 미리 알아 둘 함정

실측하면서 실제로 밟은 것들이다.

| 함정 | 증상 | 대응 |
|---|---|---|
| **SUT 가 옛 코드를 서빙한다** | `sut/` 를 고쳤는데 결과가 그대로 | `curl http://localhost:8100/__build__` 로 `stale` 확인. `true` 면 `prova run` 이 아예 시작을 거부한다 |
| **좀비 소켓** | 프로세스를 죽였는데 포트가 살아 있고 옛 응답이 온다 | 포트를 바꾼다(8101, 8102…). 리로드 감시자가 죽어도 일꾼이 소켓을 물고 남는다 |
| **`make_spec_pdf.py` 가 PDF 전부를 다시 쓴다** | `git status` 에 안 건드린 PDF 까지 뜬다 | 정상이다. `git checkout -- fixtures/specs` 로 통째 되돌린다 |
| **fixtures 를 고치면 테스트가 깨진다** | `test_fixture_consistency` · `test_s1_golden` 실패 | 8회차 실습은 가지에서 하고 끝나면 되돌린다 |
| **1회차 설치가 90분을 먹는다** | `playwright install chromium` 이 브라우저를 통째로 받는다 | **반드시 1주 전에 미리 받아 오게 한다** |
| **mock 백엔드 경고** | `'CaseTitles' 응답이 등록되지 않았습니다` | 정상이다. 케이스 제목 다듬기만 건너뛴다 |

---

## 더 볼 것 — 커리큘럼에 넣지 않은 노트

버린 게 아니라 8회에 안 들어간 것이다. 관심 있는 주제로 바로 가면 된다.

| 노트 | 주제 |
|---|---|
| `06-langgraph.md` | LangGraph 를 관통 이후로 미룬 판단 |
| `07-cheetah-cuda.md` | GPU 서버에서 실제로 막힌 세 지점 (반납했으므로 읽기만) |
| `09-search-scenarios.md` | 규칙으로 표현할 수 없는 검증 (검색) |
| `10-counting-dom.md` | 화면이 말해 주지 않는 것을 확인하기 |
| `11-multi-screen-flows.md` | 한 문서 여러 화면 + 화면 사이 흐름 |
| `12-coverage-gaps.md` | 기획서에 적혀 있는데 아무도 확인하지 않는 것 |
| `13-vlm-fallback.md` | 화면 이미지로 요소 찾기 (GPU 필요) |
| `14-real-spec-robustness.md` | 기획서가 훼손됐을 때 — 모델이 요구사항을 발명한다 |
| `16-forbidden-text.md` | 없어야 할 것이 없는가 |
| `17-audit.md` | 각각은 옳은데 함께 두면 구멍이 난다 |
| `18-natural-language-request.md` | 자연어로 요청받기 + 로컬 웹 UI |
| `19-preconditions-self-consistency.md` | 전제가 있는 화면, 자기일관 판정 |
| `20-date-filter.md` | 조작한 뒤의 화면을 검증한다 |
| `21-figma-path.md` · `22-figma-merge.md` | 디자인을 검증 계약으로 읽는다 |
| `23-two-stage-run.md` | 한 GPU 로 두 모델을 쓴다 |

설계 판단 14건은 [`../design-decisions.md`](../design-decisions.md),
아직 안 한 것은 [`../roadmap.md`](../roadmap.md).

---

## 회차 페이지 템플릿 (Notion)

`Team. 소인배 > AI > AI 개발` DB 에 회차마다 한 행. 1학기 NumPy 스터디와 같은 꼴이다.

- `날짜` (제목): `9/22(화)`
- `주제`: `1주차 Prova 스터디 — 무엇을 만들었고 왜 만들었나`

본문 구조:

```
> **대상**: 1학년 · **시간**: 1시간~1시간 30분 · **목표**: …

## 0. 시작하기 전에 (5분)     왜 이걸 배우나 / 오늘 배울 것 / 준비
## 1..4  본문                  절마다 (n분), 코드 블록, > 💡 핵심,
                               <details> 접힌 설명, 🎯 체크포인트
## 5. 마무리 (5분)             오늘 외워야 할 것 / 다음 주 예고 / 과제

## 부록: 치트시트
# 📅 발표 진행 타임라인 (90분 기준)   표
## 60분으로 줄여야 한다면?
## 진행자 체크리스트
## 학생들이 자주 막히는 포인트
# 💻 실습 코드                        복사해서 바로 돌아가는 전문
```

**회차 자료는 그 주에 만든다.** 미리 여덟 개를 다 써 두면, 앞 회차에서 두 사람이
어디서 막혔는지를 반영할 수 없다.
