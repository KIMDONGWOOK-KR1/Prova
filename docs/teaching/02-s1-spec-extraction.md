# 02. S1 — PDF에서 기획서를 뽑기

> 대상 파일: `src/prova/s1_spec_extractor/pdf_parser.py`, `extractor.py`, `src/prova/text_utils.py`

---

## 이 단계가 하는 일

PDF 파일 하나를 받아서 `ScreenSpec` 객체를 만듭니다.

```
login_spec.pdf  →  ScreenSpec(screen_id="login", elements=[이메일, 비밀번호, 로그인버튼], ...)
```

**두 단계로 나눴습니다.**

| 단계 | 파일 | AI 사용 | 하는 일 |
|---|---|---|---|
| 1 | `pdf_parser.py` | 없음 | PDF에서 글자와 표를 뽑는다 |
| 2 | `extractor.py` | 사용 | 뽑은 글자를 JSON 형태로 정리한다 |

---

## 왜 두 단계로 나눴나

서비스명세서 §10-2는 PDF 추출을 "🔴 API 후보(강한 멀티모달 추론 필요)"로 분류했습니다.
즉 "이건 어려우니 Claude 같은 큰 모델을 써야 한다"는 판단이었습니다.

그 판단은 **이미지와 자유서술이 섞인 실무 기획서**를 전제한 것입니다. 우리가 지금 쓰는
기획서는 사정이 다릅니다 — 우리가 직접 만든 **텍스트 레이어가 있는 PDF**입니다.

`pdfplumber`라는 라이브러리가 이런 PDF에서 글자와 표를 **정확히** 뽑아냅니다. 그러면
AI에게 남는 일은 "이 글자를 JSON으로 정리해"뿐이고, 그건 로컬 7B 모델로 충분합니다.

실제로 확인했습니다 — `tests/test_s1_golden.py`가 **10/10 통과**했습니다. Claude API가
필요 없습니다.

**이렇게 나눠두면 이득이 세 개 있습니다.**

1. 1단계를 AI 없이 테스트할 수 있다 (`tests/test_pdf_parser.py`)
2. AI에게 넘기는 글자가 적어져 10GiB VRAM에서도 여유가 있다
3. 나중에 WITCHES 실물 PDF가 이미지 기반이면 **`pdf_parser.py`만 교체**하면 된다

3번이 특히 중요합니다. 변경의 영향 범위를 한 파일로 묶어둔 것입니다.

---

## 1단계: 표를 따로 뽑는 이유

`pdfplumber`에는 두 가지 함수가 있습니다.

- `extract_text()` — 페이지의 모든 글자
- `extract_tables()` — 표를 행·열 구조로

만약 `extract_text()`만 쓰면 표가 이렇게 뭉개집니다.

```
요소 ID 유형 라벨 필수 입력 검증 규칙 에러 메시지
email 입력 이메일 필수 이메일 형식(@ 포함) 올바른 이메일 형식을 입력하세요.
```

한 줄로 이어져서 **어느 값이 "검증 규칙" 열이고 어느 게 "에러 메시지" 열인지 알 수
없습니다.** AI에게 이걸 주면 헷갈립니다.

그래서 `pdf_parser.py`는 표를 **마크다운 표로 다시 조립**합니다.

```markdown
| 요소 ID | 유형 | 라벨 | 필수 | 입력 검증 규칙 | 에러 메시지 |
|---|---|---|---|---|---|
| email | 입력 | 이메일 | 필수 | 이메일 형식(@ 포함) | 올바른 이메일 형식을 입력하세요. |
```

이제 AI가 열 이름을 보고 값의 의미를 판단할 수 있습니다.

### 본문에서 표를 지우는 처리

`extract_text()`는 표 안 글자까지 포함하므로, 그냥 두면 같은 내용이 두 번 들어갑니다.
그래서 표가 있는 영역의 글자를 걸러냅니다.

```python
# pdf_parser.py 의 _extract_body_text()
table_boxes = [t.bbox for t in page.find_tables()]      # 표의 사각형 좌표

def outside_tables(obj) -> bool:
    cx = (obj["x0"] + obj["x1"]) / 2                     # 글자의 중심점
    cy = (obj["top"] + obj["bottom"]) / 2
    return not any(x0 <= cx <= x1 and top <= cy <= bottom
                   for x0, top, x1, bottom in table_boxes)

filtered = page.filter(outside_tables)                    # 표 밖 글자만
```

**`bbox`란?** bounding box, 즉 "이 표가 페이지의 어느 사각형 영역에 있는지"를 나타내는
네 숫자(왼쪽, 위, 오른쪽, 아래)입니다. 글자의 중심이 그 사각형 안에 있으면 표 안의 글자입니다.

---

## 함정 1: PDF는 원문을 그대로 복원하지 못한다

**이게 이 단계에서 가장 중요한 발견입니다.**

기획서 원문:
```
비밀번호는 8자 이상이며 대문자·특수문자를 각 1자 이상 포함해야 합니다.
```

PDF에서 뽑은 결과:
```python
'비밀번호는 8자\n이상이며 대문자·\n특수문자를 각\n1자 이상\n포함해야 합니다.'
```

`\n`은 줄바꿈입니다. 문제는 이렇습니다.

| 위치 | 원문 | `\n`을 어떻게 해야 하나 |
|---|---|---|
| `8자\n이상이며` | `8자 이상이며` (공백 있음) | **공백으로 바꿔야** 맞음 |
| `대문자·\n특수문자` | `대문자·특수문자` (공백 없음) | **지워야** 맞음 |

**텍스트만 보고는 어느 쪽인지 알 수 없습니다.** 한글은 영어와 달리 단어 경계가 아닌
글자 단위로도 줄바꿈되기 때문입니다.

### 왜 이게 심각한가

에러 문구 비교가 이 프로젝트의 **판정 근거**입니다. 기획서에서 뽑은 문구와 브라우저 화면에서
읽은 문구를 대조해서 PASS/FAIL을 정합니다. 공백 하나가 달라서 FAIL이 나면 **오탐**입니다.

### 해결: 복원을 포기하고, 비교를 정규형에서 한다

`src/prova/text_utils.py`가 이 일을 합니다.

```python
def loosen(text: str) -> str:
    """공백을 전부 제거한 비교용 형태."""
    return re.sub(r"\s+", "", text)
```

양쪽에서 공백을 다 지우고 비교하면 줄바꿈 위치가 어떻든 같은 문구는 같아집니다.

```python
loosen("비밀번호는 8자\n이상이며 대문자·\n특수문자를...")  # 비밀번호는8자이상이며대문자·특수문자를...
loosen("비밀번호는 8자 이상이며 대문자·특수문자를...")      # 비밀번호는8자이상이며대문자·특수문자를...
# → 같다
```

**하지만 무시하는 것은 공백뿐입니다.** 문구 자체가 다르면 반드시 달라야 합니다.

```python
loosen("이메일 또는 비밀번호가 올바르지 않습니다.")   # 기획서
loosen("로그인 정보를 확인해주세요.")                  # 구현
# → 다르다 → FAIL (이게 우리가 잡아야 하는 불일치)
```

조사나 어미까지 관대하게 비교하고 싶은 유혹이 생기는데, 그러면 진짜 불일치를 놓칩니다.

---

## 함정 2: 폰트 글리프가 없으면 `(cid:127)`이 나온다

PDF를 만들 때 불릿(`•`)이 폰트에 없으면 이렇게 추출됩니다.

```
(cid:127) 필수 입력이다. 비어 있으면 에러 메시지를 노출한다.
```

`cid`는 character ID로, "이 위치에 글자가 있는데 어떤 글자인지 모른다"는 뜻입니다.
AI 프롬프트에 이런 게 섞이면 노이즈가 됩니다.

양쪽을 다 고쳤습니다.

1. **PDF 생성 쪽** (`scripts/make_spec_pdf.py`) — 불릿을 본문 한글 폰트로 찍는다
2. **파서 쪽** (`text_utils.strip_cid`) — `(cid:숫자)` 패턴을 제거한다

2번도 필요한 이유: **실무 PDF는 우리가 만드는 게 아닙니다.** WITCHES가 준 PDF에 폰트
임베딩 문제가 있으면 파서가 견뎌야 합니다.

---

## 2단계: AI에게 형식을 강제하기

`extractor.py`의 프롬프트에 **매핑 표를 못 박아** 두었습니다.

```
| 기획서 표현 | constraints 키 | 값 |
|---|---|---|
| 이메일 형식 | format | "email" |
| N자 이상 / 최소 길이 N자 | min_length | N (정수) |
| 대문자 N자 이상 포함 | require_uppercase | N (정수) |
| 특수문자 N자 이상 포함 | require_special | N (정수) |

키 이름을 바꾸거나 새로 만들지 마세요.
```

**왜 이렇게 강하게 지시하나?** AI가 자유롭게 판단하면 `min_len`, `minLength`, `length_min`
같이 매번 다른 이름을 씁니다. 그러면 S2의 `rule_expander`가 그 규칙을 알아보지 못해서
**검증이 조용히 사라집니다.**

여기에 더해 `response_format`으로 형식 자체를 강제합니다. 다음 노트와
[07-cheetah-cuda.md](07-cheetah-cuda.md)에서 자세히 다룹니다.

### 조용한 실패를 막는 장치

```python
# extractor.py 의 extract_screen_spec()
if not any(e.constraints for e in spec.elements):
    spec.warnings.append(
        "입력 검증 규칙(constraints)이 하나도 추출되지 않았습니다. ..."
    )
```

규칙이 하나도 안 나왔으면 거의 확실히 추출 실패입니다. 그냥 넘어가면 위반 케이스가 아예
생성되지 않아 리포트가 **근거 없이 초록불**이 됩니다. 그래서 경고를 남기고, 그 경고가
리포트 상단에 노란 상자로 표시됩니다.

---

## 확인해보기

```powershell
# PDF에서 뽑은 결과를 직접 보기
uv run python -c "
from prova.s1_spec_extractor.pdf_parser import parse_pdf
doc = parse_pdf('fixtures/specs/login_spec.pdf')
print(doc.to_llm_text()[:1500])
"

# 공백 정규화가 어떻게 동작하는지
uv run python -c "
from prova.text_utils import loosen
a = '비밀번호는 8자\n이상이며 대문자·\n특수문자를 각 1자 이상\n포함해야 합니다.'
b = '비밀번호는 8자 이상이며 대문자·특수문자를 각 1자 이상 포함해야 합니다.'
print('같은가?', loosen(a) == loosen(b))
"

# 테스트
uv run pytest tests/test_pdf_parser.py tests/test_text_utils.py -v
```

---

다음: [03-llm-vs-code.md](03-llm-vs-code.md) — AI에 맡길 일과 코드로 짤 일의 경계
