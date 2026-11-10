# 오프라인 시연 순서 (GPU 없이)

> GPU 반납(2026-11-13) 뒤 시연용. 모델 서버 없이 `--backend replay` 로 그때 실모델이 낸 응답을
> 다시 쓴다(`fixtures/replay-cache`). 2026-11-10 에 이 순서 그대로 리허설해 아래 결과를 확인했다.

## 준비

```powershell
uv sync --extra dev
uv run uvicorn sut.app:app --port 8100 --reload --reload-dir sut   # 별 터미널
```

8100 이 `WinError 10013` 으로 안 열리면 Windows 예약 포트다
(`netsh interface ipv4 show excludedportrange protocol=tcp`). 다른 포트(예: 18100)로 띄우고
아래 `--url` 의 포트만 바꾼다.

**2차 경로(화면 이미지로 찾기)는 끈다** — VLM 응답은 재생되지 않는다.

## 순서

| # | 보여 줄 것 | 명령 | 리허설 결과 (11-10) |
|---|---|---|---|
| 1 | 기획서와 다른 구현을 잡는다 | `uv run prova run --pdf fixtures/specs/login_spec.pdf --url http://localhost:8100/bad --backend replay` | 4 PASS · 6 FAIL(전부 기획서와 다름) |
| 2 | 웹 UI — 자연어 요청 → 계획 승인 → 실행 | `uv run prova serve` → 백엔드 '실제 모델의 저장된 응답', 요청 "비밀번호 규칙이 제대로 걸리는지 확인해줘", 대상 `/bad` | 비밀번호 케이스 4개 선택 · 1 PASS · 3 FAIL |
| 3 | 리포트 · 엑셀 | 1번 결과의 `runs/<id>/report.html` → '엑셀로 받기' | `report.xlsx` 생성 |
| 4 | 기획서 개정판 — 무엇이 바뀌었나 | `uv run prova diff-spec --old fixtures/specs/login_spec.pdf --new fixtures/specs/revisions/login_spec_v2.pdf --backend replay` | 바뀐 것 2건(비밀번호 안내 문구, 로그인 버튼 이름) |
| 5 | 바뀐 것이 사이트에 반영됐나 | `uv run prova run --pdf fixtures/specs/revisions/login_spec_v2.pdf --since fixtures/specs/login_spec.pdf --changed-only --url http://localhost:8100/good --backend replay` | 10 FAIL — 사이트는 옛 판이라 '로그인하기' 버튼을 못 찾음 8 · 기획서와 다름 2 |
| 6 | 실제 접수가 일어나면 안 되는 사이트 | `uv run prova run --pdf fixtures/specs/signup_spec.pdf --url http://localhost:8100/good --backend replay --dry-run` | 3 PASS · 14 확인 불가(쓰기 요청 막음) |
| 7 | 휴대폰 화면 크기 | `uv run prova run --pdf fixtures/specs/login_spec.pdf --url http://localhost:8100/good --backend replay --device mobile` | 10/10 PASS |

## 말할 때 조심할 것

- **6번의 콘솔 요약은 '실패 14 · 통과율 17.6%'** 로 나온다. 확인 불가도 실패 칸에 세기
  때문이다. 리포트·엑셀의 dry-run 경고 상자를 같이 보여 주고 "구현 결함이 아니라 서버 응답을
  못 본 것" 이라고 말한다. 우리 SUT 는 서버에서 검증하므로 제출 케이스 대부분이 확인 불가인 것이
  정상이다.
- 5번의 '요소 미탐지' 8개는 기획서는 바뀌었는데 사이트가 안 바뀐 결과다 — 시연 의도대로다.
- 같은 기획서·대상으로 여러 번 돌리면 리포트가 '차수' 를 올리고 지난 실행과 비교한다.
  깨끗하게 보이려면 `--run-id` 를 새로 주거나 `runs/` 의 리허설 폴더를 지운다.
- replay 는 저장된 질문에만 답한다. 위 표에 없는 기획서·요청을 쓰면 "저장된 응답이 없다" 로
  실패한다 — 즉석 요청 문구를 바꾸지 않는다.
- 실물 기획서·실물 사이트는 시연에 쓰지 않는다(비공개).
