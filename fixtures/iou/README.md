# 탐지 정확도 시험지 (`fixtures/iou`)

명세서 §9 의 **'탐지 성공률 ≥90%(IoU 기준)'** 에 답하기 위한 데이터셋이다.
시험지는 완성됐고 실물 VL 로 두 번 채점했다 — 08-22 에 13화면 50항목
(`vlm-iou-qwen-vl-2026-08-22.md`), 넓힌 뒤 **08-28 에 18화면 74항목**
(`docs/measurements/vlm-iou-qwen-vl-2026-08-28.md`, 지금 쓰는 숫자).
이 문서는 다시 채점할 때의 절차다.

만든 이유와 설계 근거는 두 스크립트의 docstring 에 길게 적혀 있다. 여기 적는 것은
**절차**다.

## 시험지는 '어느 앱의 화면인가' 를 들고 다닌다 (2026-08-28)

`dataset.json` 에 `sut_build` — 굳힐 때 그 앱의 빌드 도장(`GET /__build__`)이 함께
적힌다. 라이브 화면을 만지는 채점(`eval_selector_speed` · `eval_identity_guard`)은
재기 전에 지금 도장과 대조하고, 어긋나거나 표시가 없으면 **멈춘다**.

저장된 그림만 보는 채점(`eval_vlm_iou`)은 대조하지 않는다 — 앱 상태와 무관하고,
거기서 막으면 GPU 서버만 있으면 도는 그 스크립트의 성질이 깨진다.

굳히는 쪽도 확인한다. 앱이 자기 소스보다 낡았으면 시험지를 만들지 않는다 —
낡은 화면으로 정답을 굳히면 그 정답이 **처음부터 틀린다**.

왜 필요했는지: 08-27 20:31 에 시험지를 굳혔는데 21:49 에 주문조회에 상태 select 가
붙어 `조회` 버튼이 밀렸다. 저장된 좌표를 재생한 관문 측정이 오차단 3건을 냈고,
하마터면 관문을 고칠 뻔했다 (`docs/measurements/identity-guard-replay-2026-08-28.md`).

`dataset_id` 는 이 문제를 못 잡는다 — 그건 '두 점수가 같은 시험지인가' 이고,
이건 '그 시험지가 아직 이 앱의 화면인가' 다.

## 지금 상태 (2026-08-27)

    시험지        화면 18장 · 항목 74개 (있음 60 · 없음 14)   dataset_id=3dd2243cb229
    채점 경로     GPU 없이 배관 확인 완료 (--backend oracle)
    1차 경로      selector — 58/60 (96.7%) · 오탐 0/14 · 평균 16.4ms  ← 새 시험지
    2차 경로      Qwen2.5-VL-3B-AWQ — **옛 시험지(536392d2154b)의 점수다**
                  IoU 21/40 (52.5%) · 적중 36/40 (90%) · 오탐 7/10

**2차 경로는 새 시험지로 다시 채점해야 한다.** VL 서버를 올려야 하므로(7B 를
내려야 한다) 다음 GPU 작업 때 함께 한다. `eval_selector_speed.py` 는 두 점수의
`dataset_id` 가 다르면 비교표를 만들지 않는다 — 항목 id 는 열거 순서라서 집합이
같아도 같은 id 가 다른 항목을 가리킬 수 있기 때문이다.

굳혀 둔 것이라 **다시 만들 필요가 없다.** `tests/test_iou_dataset.py` 는 정답
파일이 **손으로 고쳐졌는지**만 잡는다(자기 내용의 해시를 자기 id 와 대조한다) —
`sut/templates` 가 바뀐 것은 잡지 못한다. 화면을 고쳤으면 아래 '시험지를 고쳐야
하는 경우' 대로 다시 만든다.

**범위: 6화면 전부다** (2026-08-27 에 상품등록·주문조회를 더했다). 주문조회는 반복
행 + aria-label 목록 + 날짜 입력이라 2차 경로가 가장 어려운 모양인데 빠져 있었고,
순수 `<table>` 마크업도 함께 넣었다 — 모델은 픽셀만 보므로 그림이 실제로 다른 것만
넣는다는 기준(`hashed`·`native`·`spa` 제외)은 그대로다.

상품등록·주문조회는 **로그인 뒤 화면**이다. 항목마다 `login` 표시를 싣고 채점하는
쪽이 그것을 쓴다 — 세션 없이 열면 화면이 통째로 로그인으로 리다이렉트되고, 거기
있는 '비밀번호' 가 **오탐으로 집계된다**(실제로 겪었다). 도구 결함이 탐지 실패로
둔갑하는 모양이라 시험지가 들고 다닌다.

보고에 쓰는 숫자는 `docs/measurements/` 에 옮긴 것 하나다. `runs/iou/` 의 연습 실행과
섞지 않는다.

## 이어서 하는 절차

### 1. 검증 대상을 띄운다 (채점에는 필요 없다)

이미 굳은 PNG 로 채점하므로 **SUT 는 필요 없다.** 시험지를 다시 만들 때만 필요하다.

    uv run uvicorn sut.app:app --port 8100 --reload --reload-dir sut
    uv run python scripts/build_iou_dataset.py       # dataset_id 가 같아야 정상

### 2. VL 서버로 교체한다 ← 사람이 해야 한다

MIG 파티션 9.50 GiB 에서 7B 가 8.30 GiB 를 쓴다. **VL 3.17 GiB 와 동시 적재는
불가능하다.** LLM(S1)과 VLM(S3)이 동시에 필요한 시점이 없어 시간분할로 쓴다.

원격 서비스 기동·중지는 Claude 의 권한 분류기가 막으므로 사람이 실행한다:

    cd /c/dev/prova && set -a && . ./.env && set +a && \
      ssh -i "$CHEETAH_KEY" -p "$CHEETAH_PORT" "$CHEETAH_USER@$CHEETAH_HOST" \
        'tmux kill-session -t =vllm; \
         tmux new -d -s qwenvl "bash /tmp/serve_vl.sh > /tmp/vl.log 2>&1"; \
         sleep 3; tmux ls'

    nohup ssh -N -L 8001:localhost:8001 -o ServerAliveInterval=30 \
      -i "$CHEETAH_KEY" -p "$CHEETAH_PORT" "$CHEETAH_USER@$CHEETAH_HOST" &

`-t =vllm` 의 `=` 는 **정확 매칭 강제**다. 없으면 접두어 매칭으로 엉뚱한 세션이 죽는다
(실제로 `-t vl` 이 `vllm` 을 죽인 적이 있다). 세션 이름을 `qwenvl` 로 둔 것도 같은 이유다.

로딩에 80초~3분. 확인:

    curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8001/v1/models   # 200

`/tmp` 가 비어 있으면(pod 재시작) 가중치와 venv 가 사라진 것이다 —
`docs/CHEETAH_SETUP.md` 의 복구 절차를 먼저 밟는다. `huggingface_hub` 는 이 노드에서
큰 파일을 조용히 못 받으므로 `curl -C -` 로 받는다.

### 3. 형식부터 확인한다 (6개)

    uv run python scripts/eval_vlm_iou.py --limit 6

74개를 다 돌린 뒤에 응답 형식 문제를 발견하면 시간을 두 번 쓴다. 모델 이름이 어긋나면
`/models` 는 200 인데 `chat/completions` 가 404 다 — `health()` 가 그것을 잡아 준다.
서빙 이름이 다르면 `--vlm-model` 로 맞춘다.

### 4. 전체를 돌린다 (74개, 8~12분 예상)

    uv run python scripts/eval_vlm_iou.py

결과는 `runs/iou/result-<모델>.{md,json}` 에 쓰인다(gitignore). 보고에 쓸 것만
사람이 `docs/` 로 옮긴다 — 연습 실행 파일이 저장소에 섞이면 나중에 어느 것이 보고에
쓴 숫자인지 알 수 없다.

### 5. 7B 를 되돌린다 ← 잊으면 다음 작업이 조용히 반쪽이 된다

VL 을 띄워 둔 채로 두면 S1 골든 대조 **69개가 자동 skip** 된다. 통과처럼 보이지만
추출 정확도를 아무것도 확인하지 않은 상태다.

    ssh ... 'tmux kill-session -t =qwenvl; \
             tmux new -d -s vllm "bash ~/serve_vllm.sh > /tmp/vllm.log 2>&1"'
    nohup ssh -N -L 8000:localhost:8000 -o ServerAliveInterval=30 -i ... &

## 채점 뒤에 한 일과 남은 것 (2026-08-22)

- 노트 13 과 README 의 4행 표를 50개 결과로 교체했다. `probe_vlm.py` 는 지웠다.
- 명세서 §9 에 대한 답은 **(b) IoU 와 적중률을 병기**하고 실제 성패 기준(적중)을
  밝히는 쪽으로 **README 와 노트 13 에** 적었다. 실측이 예상대로 "적중인데 IoU
  미달"(15/40) 이었기 때문이다. 명세서 파일 자체(v1.0)는 고정 기준이라 고치지 않는다.
- **오탐 7/10 이 남은 일이다.** 신뢰도 관문이 하나도 못 걸렀다. 이 시험지는 PNG 만
  굳혀서 `_require_actionable` 이 그 7개를 막았을지는 모른다 — 다음 채점 전에
  DOM 스냅샷(또는 조작 가능 영역 목록)을 함께 굳혀 그 통과율을 잰다.

## 시험지를 고쳐야 하는 경우

화면(`sut/templates`)이 바뀌면 정답 좌표가 실제와 어긋난다. 그 상태로 채점하면
**'시험지가 낡았다' 가 '모델이 틀렸다' 로 보인다.** 다시 만들고, `dataset_id` 가
바뀐 사실을 결과와 함께 남긴다 — 다른 시험지의 점수는 비교 대상이 아니다.

항목을 더할 때는 `scripts/build_iou_dataset.py` 의 `STATES` 표에 한 줄을 더한다.
정답 selector 는 **손으로 쓴다** — `dom_locator` 로 찾으면 도구가 이미 찾을 수 있는
요소만 시험지에 들어가고, 2차 경로가 필요한 어려운 요소가 조용히 빠진다.
