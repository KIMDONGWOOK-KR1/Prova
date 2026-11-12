# 사용법

[README](../README.md) 의 '빨리 돌려보기' 를 넘어서는 실행 방법 전부.

## 실행

```powershell
# 1. 의존성
uv sync --extra dev
uv run playwright install chromium

# 2. 기획서 PDF 생성 (md -> pdf)
uv run python scripts/make_spec_pdf.py

# 3. 테스트 대상 웹앱 띄우기 (별 터미널)
uv run uvicorn sut.app:app --port 8100 --reload --reload-dir sut

# 4. 검증 — GPU 가 없으면 --backend mock (픽스처 기획서 전용 연습 모드).
#    GPU 서버가 있으면 --backend 를 빼고, 먼저 `uv run prova check` 로 연결을 확인한다
uv run prova run --pdf fixtures/specs/login_spec.pdf  --url http://localhost:8100/good --backend mock
uv run prova run --pdf fixtures/specs/login_spec.pdf  --url http://localhost:8100/bad  --backend mock
uv run prova run --pdf fixtures/specs/signup_spec.pdf --url http://localhost:8100/good --backend mock
uv run prova run --pdf fixtures/specs/signup_spec.pdf --url http://localhost:8100/bad  --backend mock
uv run prova run --pdf fixtures/specs/search_spec.pdf --url http://localhost:8100/good --backend mock
uv run prova run --pdf fixtures/specs/search_spec.pdf --url http://localhost:8100/bad  --backend mock

# 4-1. GPU 를 반납한 뒤(2026-11-13~) 실모델 결과를 다시 보려면 --backend replay.
#      mock(정답표)과 달리 그때 실모델이 실제로 낸 응답을 그대로 쓴다(fixtures/replay-cache).
#      픽스처·외부 기획서 26개와 시연 요청은 11-07 에 채워 두었다. 2차 경로(VLM)는 재생되지 않는다.
#      시연 순서와 리허설 결과는 docs/demo-offline.md
uv run prova run --pdf fixtures/specs/signup_spec.pdf --url http://localhost:8100/bad  --backend replay
#      개정판 비교 시연(11-09 응답): login_spec 의 v2 는 비밀번호 안내 문구와 로그인 버튼 이름이 다르다
uv run prova diff-spec --old fixtures/specs/login_spec.pdf --new fixtures/specs/revisions/login_spec_v2.pdf --backend replay
uv run prova run --pdf fixtures/specs/revisions/login_spec_v2.pdf --since fixtures/specs/login_spec.pdf --changed-only --url http://localhost:8100/good --backend replay

# 5. 리포트 열기 — 옆에 report.xlsx(요약·케이스·기획서와 다름 시트)도 생긴다
#    실패 카드는 넣은 값(단계 표 '값' 칸)과 기획서 근거(몇 쪽 어느 줄)를 함께 보여 준다 —
#    리포트만 보고 손으로 재현하고, 기획서에서 그 줄을 찾아 확인할 수 있다
start runs/<run-id>/report.html

# 5-1. 엑셀이 없는 예전 실행은 report.json 으로 다시 만든다
uv run prova export-xlsx runs/<run-id>

# 6. 기획서 개정판 — 무엇이 바뀌었나(사이트는 열지 않는다)
uv run prova diff-spec --old 기획서_v0.2.pdf --new 기획서_v0.3.pdf
#    바뀐 것이 사이트에 반영됐나 — 리포트·엑셀에 '바뀐 것' 상자와 케이스별 '개정' 표시.
#    --changed-only 를 붙이면 바뀐 것을 건드리는 케이스만 돈다
uv run prova run --pdf 기획서_v0.3.pdf --since 기획서_v0.2.pdf --url <대상> [--changed-only]

# 7. 실제 접수·가입이 일어나면 안 되는 사이트 — 쓰기 요청(POST·PUT·PATCH·DELETE)을 막고 실행.
#    막은 요청이 있는 케이스는 서버 응답을 못 봐 '확인 불가', 전제(로그인) 요청만 통과시킨다.
#    GET 으로 데이터를 바꾸는 주소와 웹소켓은 막지 못한다. 우리 SUT 로만 검증했다(tests/test_dry_run.py)
uv run prova run --pdf fixtures/specs/signup_spec.pdf --url http://localhost:8100/good --backend mock --dry-run

# 8. 휴대폰 화면 크기(390x844)로 — 리포트 머리말과 실행 이력에 기기가 남는다
uv run prova run --pdf fixtures/specs/login_spec.pdf --url http://localhost:8100/good --backend mock --device mobile
```

SUT 는 `--reload` 로 띄운다. **`sut/` 를 고치고 재시작을 잊으면 옛 코드를 상대로
재게 되고, 그 결과가 도구의 오탐처럼 보인다** — 실제로 겪었다(2026-08-26, 기간 역전을
구현한 직후 `good` 에서 없는 FAIL 을 쫓았다). 감시 범위를 `sut` 으로 좁히는 이유는
저장소 전체를 폴링하지 않기 위해서다(`runs/`·`.venv` 가 크다). `watchfiles` 가 없으면
uvicorn 이 `StatReload` 로 떨어지므로 의존성은 늘지 않는다.

**`--reload` 만으로는 부족하다.** 그것은 프로세스를 둘로 만든다 — 부모(감시자)가
파일을 보고 자식(일꾼)이 응답하는데, 부모가 죽으면 자식은 소켓을 물고 남는다.
포트는 열려 있고 응답도 정상인데 아무도 파일을 보지 않는 상태다(2026-08-27 에
두 번 속았다). 그래서 SUT 가 `GET /__build__` 로 자기 소스보다 낡았는지 스스로
답하고, `prova run` 이 실행 전에 물어 어긋나면 **시작하지 않는다**. 결과는
리포트 머리말에 `대상 빌드 일치` 로 남는다. 도장이 없는 대상(=실물 웹앱)에는
아무 말도 하지 않고 그대로 진행한다 — 자세한 이유는 티칭 노트 20 참고.

한 가지 알아 둘 것: 가입한 계정(`REGISTERED`)은 **프로세스 상태**라 리로드되면
지워진다. 실행 도중 `sut/` 를 고치면 '가입한 계정으로 로그인' 을 밟는 흐름 케이스가
그 영향을 받을 수 있다. 판정을 재는 중이라면 고치지 말고, 고쳤으면 다시 돌린다.

자연어로 무엇을 볼지 좁힐 수 있다. 무엇을 뺐는지는 리포트에 남는다.

```powershell
uv run prova run --pdf fixtures/specs/login_spec.pdf --url http://localhost:8100/bad                  --request "비밀번호 규칙이 제대로 걸리는지 확인해줘"
```

화면으로 쓰려면 웹 UI 를 연다. 요청을 쓰면 **실행 전에 무엇을 테스트할지 보여주고
승인을 받는다.**

```powershell
uv run prova serve      # http://127.0.0.1:7007
```

계획 화면의 **'기획서에서 읽은 내용'** 에서 추출 결과(요소·규칙·문구)를 직접 보고,
틀린 값을 고친 뒤 그 문서로 케이스를 다시 만들어 실행할 수 있다. 모델이 잘못 읽은 값이
그대로 판정 기준이 되는 것을 사람이 실행 전에 막는 자리다. 사람이 고친 값은 리포트
상자에 남는다(`summary["spec_edits"]`).

실행 설정 맨 위의 **프로젝트** 는 기획서와 실행을 묶는 이름이다(납품 건·외주사 등). 새 이름을
적으면 그 프로젝트가 만들어진다. 이름을 적은 채로 기획서를 올리면 `uploads/<프로젝트>/` 에
들어가 기획서 목록에서 그 프로젝트 묶음으로 보이고, 같은 이름으로 다시 돌리면 대상 주소가
바뀌어도 리포트가 차수(1차·2차…)를 잇는다. 아래 **실행 기록** 은 프로젝트별로 접혀 있고,
지금 고른 프로젝트가 펼쳐진다. 프로젝트의 이름 바꾸기·지우기·기획서 옮기기는 화면에 없다 —
`uploads/` 의 폴더를 직접 고친다. 계정·권한은 없다(혼자 띄워 쓰는 도구다).

웹 UI 에서도 **화면 이미지로 찾기(2차 경로)** 를 켤 수 있다 — 실행 설정의 체크박스이고
기본은 꺼져 있다. 켜면 `configs/default.yaml` 의 `llm.base_url`·`llm.model` 서버에 붙고,
서버가 없으면 실행을 시작하지 않는다. 켰는지 여부는 리포트 머리말에 남는다(CLI 도 같다).

**쓰기 요청 막기(dry-run)** 체크박스도 있다 — CLI `--dry-run` 과 같은 장치로, 실제 접수·가입이
일어나면 안 되는 사이트에서 켠다. 기본은 꺼져 있고 저장하지 않는다. dry-run 실행은 일반 실행과
다른 이력 줄기로 센다(막은 케이스가 '새로 깨진 것' 으로 읽히지 않게).

2026-09-28 부터는 Qwen3.5-4B 한 모델이 추출과 탐지를 함께 맡아, 2차 경로도 같은
서버로 켠다(`--vlm http://localhost:8000/v1`). 근거는
[모델 비교 측정](measurements/model-compare-qwen35-4b-2026-09-28.md) —
탐지 성공률 57→81%, 없는 요소를 있다고 한 비율 71→7%.

그 전처럼 추출 모델(7B)과 탐지 모델(VL)을 한 GPU 에서 시간분할로 쓸 때는 실행을 둘로
자른다 — 계획을 저장하고, 서버를 교체한 뒤, LLM 없이 이어 돈다(설계 판단 18).

```powershell
uv run prova run --pdf 기획서.pdf --url http://... --run-id two-model --plan-only
# (tmux 에서 7B 를 내리고 VL 을 올린다)
uv run prova run --resume runs/two-model --vlm http://localhost:8001/v1 --vlm-model Qwen2.5-VL-3B-AWQ --vlm-coords pixel
```

2026-08-26 에 실물 7B(추출) → 실물 VL(탐지)로 관통시켰다. `nolabel` 에서 2차
경로 없이 재개하면 1 PASS / 9 FAIL, 실물 VL 로 재개하면 **9 PASS / 1 FAIL**
(이미지로 찾아 진행 8건)이고, 남은 FAIL 1건은 심어 둔 라벨 결함 그대로다.
리포트는 재개 실행에 LLM 이 없는데도 추출 백엔드를 7B 로 기록한다 (노트 23).

납품 차수마다 같은 기획서를 돌릴 때는 `--project` 로 묶는다. 리포트가 몇 차인지와 직전
실행 대비 새로 실패·해결된 케이스를 보여 주고, 진행 로그는 `runs/<id>/run.log` 에 남는다.
대상 서버가 동시 접속에 안전하면 `--workers 4` 로 브라우저를 여럿 띄운다(판단 26 — 새
대상은 순차와 한 번 대조한 뒤). 같은 기획서를 다시 돌리면 저장된 모델 응답을 쓰고(리포트가
건수를 말한다), `--no-cache` 로 새로 묻는다.

```powershell
uv run prova run --pdf 기획서.pdf --url http://staging/... --project "A사 2차 납품" --workers 4
uv run python scripts/score_truth.py --template D:/private/truth.yaml   # 기획서만 보고 채운다
uv run python scripts/score_truth.py --pdf uploads/기획서.pdf --truth D:/private/truth.yaml
```

실제 로컬 LLM으로 돌리려면 [docs/cheetah-setup.md](cheetah-setup.md)를 따라
CHEETAH에 vLLM을 올리고 `--backend` 없이 실행한다.

```powershell
uv run prova check     # vLLM 연결 + 정형 출력 동작 확인
uv run pytest          # 전체 스위트 (vLLM 없으면 실모델 측정은 자동 skip)
```

## 측정 스크립트

측정 스크립트는 `scripts/` 에 있다. 도구를 재는 것과 도구 자체를 구분해 두려고
`prova` 패키지 안에 넣지 않았다.

| 스크립트 | 하는 일 | GPU |
|---|---|---|
| `probe_s1_robustness.py` | 기획서가 훼손됐을 때 추출이 어떻게 깨지는가 (6종) | 필요 |
| `probe_request_selection.py` | 자연어 요청 해석 재현율 — 튜닝 세트 / `heldout` | 필요 |
| `build_iou_dataset.py` | — 탐지 시험지를 굳힌다 (`fixtures/iou`) | 불필요 |
| `eval_vlm_iou.py` | 화면 이미지에서 요소를 찾는 정확도 (IoU·적중·오탐·속도) | 필요 |
| `eval_selector_speed.py` | 같은 시험지를 1차 경로로 — §9 의 selector vs VLM 비교 | 불필요 (SUT 만) |
| `score_truth.py` | 실물 기획서 추출 정확도 — 사람이 옮겨 적은 정답표와 대조(놓친 것·추출에만 있는 것). 정답표는 저장소 밖에만 둔다 | 필요 |
| `mutation_test.py` | 변이 시험 — 기획서 문구·라벨·선택지·예시 값을 하나씩 바꿔 정답 있는 차이를 만들고 잡는지 잰다(외부 5곳 32변이) | 필요 (replay 로 재생 가능) |
| `score_verdicts.py` | PASS/FAIL 판단 정확도 — `dump_verdicts.py` 결과를 SUT 에 심은 결함에서 만든 정답 라벨과 대조(일치율·혼동행렬). 2026-11-10 98.5% | 불필요 (mock) |
| `score_report_completeness.py` | 리포트 완결성 — 실패 케이스마다 계획서의 다섯 칸(실행 로그·입력 데이터·기대 결과·실제 결과·실패 원인)이 `report.json` 에 찼는지 센다. 2026-11-11 실패 1,525건 전부 100% (`docs/measurements/report-completeness-2026-11-11.md`) |
| `dump_cases.py` · `dump_verdicts.py` | 코드 변경의 안전망 — 픽스처 케이스 전부·SUT 판정 전부를 한 줄씩 떠서 고치기 전후 `diff` | 불필요 (mock) |
| `make_spec_pdf.py` · `make_multi_spec.py` | 픽스처 기획서 md → PDF, 통합 문서 조립 | 불필요 |
| `make_comparison.py` · `make_demo_gif.py` · `embed_media.py` | 티칭 페이지 자료(비교 이미지·GIF) 생성과 인라인 — 결과물은 `docs/teaching/media/` 에 이미 있다 | 불필요 |

## 저장소에 있는 다른 도구

`scripts/legacy/extract_auth_search_json.py`는 이 파이프라인보다 먼저 만들어진 독립
추출 도구다. **HWPX 파싱과 OCR**을 지원하는데 이 파이프라인에는 없는 능력이라 그대로
둔다. 이 도구만 쓰는 의존성은 `scripts/legacy/requirements.txt` 에 따로 뒀다 — easyocr 가
torch 를 끌고 오는데, 아무도 설치하지 않는 것을 프로젝트 락 파일이 들고 다닐 이유가 없다.

`feature/figma-extractor` 브랜치에는 Figma 추출기가 있다.
자세한 내용은 [docs/reference/legacy-extractors.md](reference/legacy-extractors.md).
