# 코멘트 · 통합 기획서 조립을 코드로 옮기고 낡음을 테스트가 잡는다

> 커밋 `4b8313f` — 10 파일 / +300줄

---

## 이 변경이 답하는 질문

`fixtures/specs/multi_spec.md`(3화면 + 흐름 2개가 담긴 통합 기획서)를 **손으로 조립하고
있었습니다.** 화면별 기획서를 복사해 붙이고 앞머리와 흐름 절을 얹는 식입니다.

그러다 사고가 났습니다.

```
1. 화면별 기획서(login_spec.md)에 케이스를 늘리는 변경을 했다
2. PDF 를 다시 만들었다
3. multi_spec.md 를 다시 조립하는 것을 잊었다
```

통합 문서의 로그인 화면은 **케이스 9개** 인데 단일 문서는 10개였습니다. 그런데
**테스트가 통과했습니다** — 통합 테스트의 기대값이 낡은 숫자였으니까요.

> **손으로 조립한 픽스처는 조용히 낡는다.**

그리고 낡은 픽스처는 '통합 문서로 돌려도 화면별 결과가 유지된다' 는 이 프로젝트의 핵심
수용 기준을 무력화합니다. 유지되는지 확인하는 대상이 서로 다른 문서였으니까요.

## 무엇을 했나

**[`scripts/make_multi_spec.py`](../../scripts/make_multi_spec.py)** — 조각에서 통합 문서를 조립합니다.

```
fixtures/specs/_multi_front.md     앞머리 (문서 정보, 화면 목록)
fixtures/specs/login_spec.md   ┐
fixtures/specs/signup_spec.md  ├─ 화면별 기획서 (§ 번호를 다시 매긴다)
fixtures/specs/search_spec.md  ┘
fixtures/specs/_multi_flows.md     화면 사이 흐름 절
        -> multi_spec.md -> multi_spec.pdf
```

**[`tests/test_fixture_consistency.py`](../../tests/test_fixture_consistency.py)** — 낡으면 테스트가 실패합니다.

## 리뷰에서 봐 주면 좋은 판단 — `--check` 모드

처음 만든 테스트에 문제가 있었습니다.

```python
subprocess.run([python, "scripts/make_multi_spec.py"])   # <- 이게 문제
```

**테스트가 추적 중인 픽스처를 고쳤습니다.** 테스트를 돌리는 것만으로 워킹 트리가
더러워지고, 최악의 경우 테스트가 자기가 검사할 대상을 자기가 맞춰 놓고 통과합니다.

그래서 쓰기 없는 `--check` 모드를 만들고 테스트는 그것만 씁니다.

```python
result = subprocess.run([python, script, "--check"])
assert result.returncode == 0, "multi_spec.md 가 낡았습니다. 스크립트를 다시 실행하세요"
```

**테스트는 상태를 읽기만 해야 합니다.** 고치는 것은 사람이 명시적으로 할 일입니다.

## 왜 조각 파일 이름이 `_` 로 시작하나

`make_spec_pdf.py` 가 `fixtures/specs/*.md` 를 전부 PDF 로 만드는데, `_multi_front.md`
같은 조각만 담긴 PDF 를 만들면 **화면 개요도 요소 표도 없는 문서**가 됩니다. S1 이 요소
없는 빈 화면을 추출하고 리포트에 정체 불명의 항목이 늘어납니다.

그래서 `_` 로 시작하는 파일은 자동 변환에서 제외합니다. 다만 인자로 직접 주면 변환합니다 —
조각을 일부러 확인하고 싶을 수 있고, 그건 명시적 요청입니다.

## 물어보고 싶은 것

지금은 `--check` 실패 시 "스크립트를 다시 실행하세요" 라고만 알립니다. pre-commit 훅으로
자동 재생성하는 방법도 있는데, 그러면 **의도한 픽스처 변경과 실수를 구분할 수 없어질까**
싶어 하지 않았습니다. 팀 의견이 궁금합니다.
