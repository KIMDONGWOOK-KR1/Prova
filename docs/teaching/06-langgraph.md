# 06. LangGraph — 왜 나중에 붙였나

> 대상 파일: `src/prova/nodes.py`, `pipeline.py`, `graph.py`

---

## LangGraph란

여러 단계를 **상태 기계(state machine)** 로 연결하는 도구입니다. 이렇게 생겼습니다.

```python
graph = StateGraph(AgentState)
graph.add_node("extract_spec", extract_spec)          # 노드 등록
graph.add_node("generate_cases", generate_test_cases)
graph.add_edge("extract_spec", "generate_cases")      # 연결
```

**왜 그냥 함수를 순서대로 부르지 않고 이런 걸 쓰나?** 조건 분기와 반복이 있을 때 유용합니다.

우리 프로젝트의 2차 목표인 Self-Healing이 정확히 그런 구조입니다 (서비스명세서 §4-3).

```
ground_element ──탐지 성공──> execute_step
               ──탐지 실패──> self_heal
self_heal ──heal_count < max_heal──> ground_element   (다시 시도)
          ──한도 초과──────────> classify_failure     (포기)
```

"실패하면 다른 방법으로 재시도하고, 몇 번까지만 시도한다"를 그래프로 표현하면 흐름이
코드에 그대로 보입니다. `if`문과 `while`문으로 쓰면 중첩이 깊어져 읽기 어려워집니다.

---

## 그런데 1차에서는 쓰지 않았다

서비스명세서 §4는 LangGraph 설계를 상세히 규정합니다. 그런데 1차 관통은 LangGraph 없이
`pipeline.py`로 만들었습니다. 왜일까요?

**1차 파이프라인에는 분기가 없습니다.**

```
S1 → S2 → (S3+S4+S5) → S6
```

일직선입니다. Self-Healing이 2차 목표이므로 조건 분기가 아직 없습니다. 분기가 없는 흐름을
그래프로 만들면 **얻는 것 없이 복잡도만 늘어납니다.**

그리고 더 실질적인 이유가 있습니다.

### 혼자 개발할 때 디버깅 대상을 하나로 줄인다

버그가 났을 때 원인이 두 곳일 수 있습니다.

1. 파이프라인 로직 (S1이 잘못 뽑았나? S5가 잘못 판정했나?)
2. 그래프 배선 (엣지를 잘못 연결했나? 상태가 제대로 전달됐나?)

동시에 만들면 **둘을 구분하는 데 시간이 배로 듭니다.** 특히 처음 만드는 것이라 어느 쪽이
정상인지 감이 없을 때 그렇습니다.

그래서 순서를 정했습니다.

1. 순수 함수로 관통시켜 **파이프라인 로직을 검증**한다 (테스트 211개 통과)
2. 초록불이 된 뒤 **같은 함수를 그래프에 등록**한다
3. 두 실행 경로가 같은 결과를 내는지 대조한다

---

## 이식 비용을 0으로 만든 한 가지 조건

이 전략이 값싸게 성립하려면 조건이 하나 필요합니다.

**노드를 처음부터 `(state) -> state` 모양으로 쓰는 것.**

```python
# nodes.py
def extract_spec(state: AgentState) -> AgentState:
    """S1 — PDF 에서 ScreenSpec 을 추출한다.

    읽는 필드: pdf_path, llm
    쓰는 필드: spec
    """
    state.spec = extract_from_pdf(state.pdf_path, state.llm)
    return state
```

LangGraph의 노드가 정확히 이 모양입니다. 그래서 이식할 때 이렇게만 하면 끝입니다.

```python
# graph.py
graph.add_node("extract_spec", extract_spec)     # 함수를 그대로 등록
```

**함수 본문은 한 줄도 고치지 않았습니다.** 실제로 `pipeline.py`와 `graph.py`가 같은
`nodes.py`의 함수들을 씁니다.

```python
# pipeline.py — 순차 호출
state = extract_spec(state)
state = generate_test_cases(state)
state = run_cases(state)
state = build_final_report(state)

# graph.py — 그래프 등록
graph.add_node("extract_spec", extract_spec)
graph.add_node("generate_cases", generate_test_cases)
...
```

### 이 방식의 단점

함수 시그니처만 보면 **무엇을 읽고 쓰는지 알 수 없습니다.**

```python
def extract_spec(state: AgentState) -> AgentState:   # state 를 통째로 받는다
```

일반적인 함수라면 이렇게 쓰는 게 읽기 좋습니다.

```python
def extract_spec(pdf_path: str, llm: LLMClient) -> ScreenSpec:   # 명확하다
```

그래서 각 노드의 docstring에 **읽는 필드와 쓰는 필드를 명시**했습니다. 트레이드오프를
문서로 메우는 것입니다.

---

## 동일성을 테스트로 고정한 이유

`tests/test_graph_parity.py`가 두 경로의 결과를 비교합니다.

```python
def test_케이스별_판정과_근거가_같다(self, both_runs):
    pipe, graph = both_runs
    assert _comparable(pipe) == _comparable(graph)
```

**지금 이 테스트는 당연히 통과합니다.** 그래프가 일직선이니까요. 그럼 왜 쓰나요?

**2차에서 Self-Healing 분기를 추가할 때를 위한 것입니다.** 그때 리포트가 달라지면 원인이
두 가지일 수 있습니다.

1. 의도한 분기 때문 (self-heal이 성공해서 PASS로 바뀜 — 정상)
2. 배선 실수 때문 (엣지를 잘못 연결해서 단계를 건너뜀 — 버그)

지금 동일성을 고정해두면, 나중에 차이가 생겼을 때 **그 차이가 의도한 것인지 판별**할 수
있습니다. 기준선이 없으면 "원래 이랬나?"를 알 수 없습니다.

### 허위 통과를 막는 장치

두 경로가 **똑같이 0건**이어도 "같다"는 성립합니다. 그래서 실제로 검증을 수행했는지도
확인합니다.

```python
def test_그래프도_실제로_검증을_수행했다(self, both_runs):
    """양쪽이 똑같이 0건이어도 '같다' 는 성립한다. 그 허위 통과를 막는다."""
    _, graph = both_runs
    assert graph.summary["total"] == 7
    assert graph.summary["fail"] == 4
```

테스트를 쓸 때 자주 놓치는 부분입니다 — **"아무것도 하지 않아도 통과하는 테스트"**가 되지
않게 해야 합니다.

---

## 비교에서 제외한 값

```python
def _comparable(report):
    return [{
        "case_id": v.case_id,
        "verdict": v.verdict,
        "failure_category": v.failure_category,
        ...
    } for v in report.cases]
```

`run_id`, `created_at`, 소요 시간, 스크린샷 경로는 비교하지 않습니다. **실행마다 달라지는
것이 정상**인 값들입니다. 이런 걸 비교에 넣으면 테스트가 이유 없이 실패합니다.

---

## 브라우저 수명은 누가 관리하나

`pipeline.py`와 `graph.py`가 관리하고, 노드는 이미 열린 `Page`를 받습니다.

```python
# pipeline.py
with sync_playwright() as p:
    browser = p.chromium.launch(headless=headless)
    context = browser.new_context(viewport=...)
    state.page = context.new_page()
    try:
        state = run_cases(state)
    finally:
        context.close()      # 판정이 실패해도 반드시 닫는다
        browser.close()
```

**노드가 브라우저를 직접 열면** 두 가지 문제가 생깁니다.

1. 케이스마다 브라우저가 뜨고 지면 느립니다 (한 번 띄우는 데 1초 이상)
2. 테스트에서 노드만 떼어 호출하기 어렵습니다

`try/finally`가 중요합니다. 판정 중 예외가 나도 브라우저를 닫아야 **크롬 프로세스가 남지
않습니다.** 안 닫으면 개발 중에 크롬이 수십 개 쌓입니다.

---

## 2차에서 여기에 붙을 것

`graph.py`의 docstring에 적어둔 계획입니다.

```
ground_element --조건--> execute_step        (탐지 성공)
               --조건--> self_heal           (탐지 실패)
self_heal      --조건--> ground_element      (heal_count < max_heal)
               --조건--> classify_failure    (한도 초과)
```

그때 `run_cases` 노드가 케이스·스텝 단위 루프로 쪼개집니다. 지금 한 노드에 담아둔 이유는
1차에 분기가 없어 쪼갤 이득이 없기 때문입니다.

`AgentState`에 `heal_count`, `max_heal`을 미리 둔 것이 이 확장을 위한 것입니다.

```python
@dataclass
class AgentState:
    ...
    heal_count: int = 0      # 2차 self-healing 용
    max_heal: int = 2
```

**상태 구조를 나중에 바꾸면** 이미 작성한 노드들의 시그니처가 함께 흔들립니다. 자리를 미리
잡아두면 값을 채우기만 하면 됩니다.

---

## 확인해보기

```powershell
# 두 경로가 같은 결과를 내는지
uv run pytest tests/test_graph_parity.py -v

# 직접 비교
uv run prova run --pdf fixtures/specs/login_spec.pdf --url http://localhost:8100/bad --engine pipeline
uv run prova run --pdf fixtures/specs/login_spec.pdf --url http://localhost:8100/bad --engine graph

# 그래프 구조 보기
uv run python -c "
from prova.graph import build_graph
g = build_graph().get_graph()
print('노드:', list(g.nodes))
for e in g.edges:
    print(f'  {e.source} -> {e.target}')
"
```

출력:

```
노드: ['__start__', 'extract_spec', 'generate_cases', 'run_cases', 'build_report', '__end__']
  __start__ -> extract_spec
  extract_spec -> generate_cases
  generate_cases -> run_cases
  run_cases -> build_report
  build_report -> __end__
```

일직선입니다. 2차에서 Self-Healing을 붙이면 `run_cases`가 여러 노드로 쪼개지고 조건 엣지가
생깁니다.

그림으로 보려면 mermaid 코드를 뽑아 [mermaid.live](https://mermaid.live)에 붙여넣습니다.

```powershell
uv run python -c "from prova.graph import build_graph; print(build_graph().get_graph().draw_mermaid())"
```

---

다음: [07-cheetah-cuda.md](07-cheetah-cuda.md) — GPU 서버에서 실제로 막힌 세 지점
