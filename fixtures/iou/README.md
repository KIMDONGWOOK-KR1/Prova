# 탐지 정확도 시험지 (`fixtures/iou`)

명세서 §9 의 **'탐지 성공률 ≥90%(IoU 기준)'** 에 답하기 위한 데이터셋이다.
시험지는 완성됐고 **실물 VL 모델 채점만 남았다.** 이 문서는 그 채점을 나중에 이어서
할 수 있게 남긴 것이다.

만든 이유와 설계 근거는 두 스크립트의 docstring 에 길게 적혀 있다. 여기 적는 것은
**절차**다.

## 지금 상태 (2026-08-18)

    시험지        화면 13장 · 항목 50개 (있음 40 · 없음 10)   dataset_id=536392d2154b
    채점 경로     GPU 없이 배관 확인 완료 (--backend oracle)
    실물 측정     아직 안 했다  <-- 남은 일

굳혀 둔 것이라 **다시 만들 필요가 없다.** 시험지가 화면과 어긋나면
`tests/test_iou_dataset.py` 가 잡는다(정답 좌표의 해시를 검사한다).

이전 측정값(요소 4개, 4/4 적중)은 `docs/teaching/13-vlm-fallback.md` 와 README 에
남아 있다. 이 시험지로 다시 재면 그 표를 갈아 끼운다.

## 이어서 하는 절차

### 1. 검증 대상을 띄운다 (채점에는 필요 없다)

이미 굳은 PNG 로 채점하므로 **SUT 는 필요 없다.** 시험지를 다시 만들 때만 필요하다.

    uv run uvicorn sut.app:app --port 8100
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

50개를 다 돌린 뒤에 응답 형식 문제를 발견하면 시간을 두 번 쓴다. 모델 이름이 어긋나면
`/models` 는 200 인데 `chat/completions` 가 404 다 — `health()` 가 그것을 잡아 준다.
서빙 이름이 다르면 `--vlm-model` 로 맞춘다.

### 4. 전체를 돌린다 (50개, 5~8분 예상)

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

## 채점 결과를 받은 뒤에 할 일

1. **노트 13 과 README 의 4행 표를 이 시험지 결과로 교체한다.**
2. **`scripts/probe_vlm.py` 를 지운다.** 같은 숫자를 만드는 도구가 둘이면 한쪽만
   고쳐지고 두 값이 달라진 사실이 숨는다. 지금 남겨 둔 이유는 노트 13 의 현재 숫자를
   만든 도구라서다 — 새 숫자가 그 표를 대체하는 순간 지운다.
3. **명세서 §9 에 어느 기준으로 답할지 정한다** (팀장 판단이 필요하다).
   IoU 와 적중은 다른 것을 잰다. 납작한 입력란을 라벨까지 포함해 잡으면 **적중인데
   IoU 는 문턱값 아래**다 — 클릭은 되는데 명세서 기준으로는 실패로 세어진다.
   선택지는 (a) IoU 수치를 그대로 보고한다 (b) 적중률을 함께 적고 실제 성패 기준이
   무엇인지 밝힌다. 어느 쪽이든 **한 숫자로 합치지 않는다.**

## 시험지를 고쳐야 하는 경우

화면(`sut/templates`)이 바뀌면 정답 좌표가 실제와 어긋난다. 그 상태로 채점하면
**'시험지가 낡았다' 가 '모델이 틀렸다' 로 보인다.** 다시 만들고, `dataset_id` 가
바뀐 사실을 결과와 함께 남긴다 — 다른 시험지의 점수는 비교 대상이 아니다.

항목을 더할 때는 `scripts/build_iou_dataset.py` 의 `STATES` 표에 한 줄을 더한다.
정답 selector 는 **손으로 쓴다** — `dom_locator` 로 찾으면 도구가 이미 찾을 수 있는
요소만 시험지에 들어가고, 2차 경로가 필요한 어려운 요소가 조용히 빠진다.
