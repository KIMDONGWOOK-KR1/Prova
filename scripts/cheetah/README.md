# CHEETAH 서버 부트스트랩 스크립트

GPU 파드 홈(`~`)에 두고 쓰는 두 스크립트의 사본이다. 원본은 CephFS 영구 볼륨에 있지만
**볼륨이 바뀌거나 비워지면 같이 사라지므로** 여기에 백업해 둔다.

    setup_vllm.sh    venv 재생성 + vLLM(cu129) 설치. pod 재시작마다 필요 (약 2분)
    serve_vllm.sh    Qwen2.5-7B-Instruct-AWQ 서빙, 포트 8000 (약 3분)

파드에 올리기:

    scp -i "$CHEETAH_KEY" -P "$CHEETAH_PORT" scripts/cheetah/*.sh \
        "$CHEETAH_USER@$CHEETAH_HOST:~/"

절차와 이 환경의 함정은 `docs/cheetah-setup.md`.

**주의 — 영구 볼륨 마운트 위치를 확인할 것.** 두 스크립트는 모델 가중치 위치를
`HF_HOME=$HOME/.cache/huggingface` 로 잡는다. 2026-08 파드는 CephFS 가 `/home/jovyan` 자체였지만,
파일 게이트웨이(SFTP 전용 포트)에서는 같은 볼륨이 `/home/jovyan/master` 에 붙는다.
새 파드에서 마운트가 `~/master` 라면 `HF_HOME=$HOME/master/.cache/huggingface` 로 넘겨야 한다 —
그러지 않으면 휘발성 overlay 에 5.2GB 를 다시 받고, 재시작하면 또 사라진다.

    mount | grep ceph          # 볼륨이 어디에 붙었는지 먼저 확인
