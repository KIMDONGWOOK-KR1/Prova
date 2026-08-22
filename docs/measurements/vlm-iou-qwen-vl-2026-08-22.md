# VLM 탐지 정확도 — Qwen2.5-VL-3B-Instruct-AWQ (2026-08-22)

`scripts/eval_vlm_iou.py` 의 출력을 그대로 옮긴 것이다. 보고에 쓰는 숫자는 이 파일이고,
`runs/iou/` 의 연습 실행과 섞지 않는다. 해석은 `docs/teaching/13-vlm-fallback.md`.

- 데이터셋 `536392d2154b` · 화면 13장 · 항목 50개 (있음 40 · 없음 10)
- IoU 문턱값 0.5 · 신뢰도 문턱값 0.5

## 결과

| 지표 | 값 | 뜻 |
|---|---|---|
| 탐지 성공률 (IoU 기준) | 21/40 = 52.5% | 명세서 §9 가 요구한 지표 |
| 적중률 (중심이 요소 안) | 36/40 = 90.0% | 실제로 클릭이 되는 비율 |
| 오탐 (없는 것을 찾았다고 함) | 7/10 = 70.0% | 낮아야 한다 |
| 관문이 버린 정답 | 0개 | 크면 고칠 곳은 모델이 아니라 문턱값이다 |
| 호출 실패 | 0개 | 서버·응답 문제 |
| 평균 IoU | 0.502 | |
| 호출 시간 | 평균 737ms · 최대 1678ms | |

## 화면별

| 화면 | 탐지 성공 (IoU) | 오탐 |
|---|---|---|
| login-empty | 2/3 = 66.7% | 2개 |
| login-filled | 2/3 = 66.7% | 0개 |
| login-error | 1/3 = 33.3% | 0개 |
| signup-empty | 1/7 = 14.3% | 0개 |
| signup-error | 1/7 = 14.3% | 0개 |
| signup-welcome | 0/1 = 0.0% | 2개 |
| search-empty | 2/2 = 100.0% | 2개 |
| search-results | 3/3 = 100.0% | 0개 |
| search-none | 2/2 = 100.0% | 0개 |
| nolabel-empty | 2/2 = 100.0% | 0개 |
| nolabel-results | 3/3 = 100.0% | 0개 |
| find-empty | 2/2 = 100.0% | 1개 |
| find-sent | 0/2 = 0.0% | 0개 |

## 항목별

| 화면 | 요소 | 종류 | 결과 | IoU | 중심오차 | 신뢰도 |
|---|---|---|---|---|---|---|
| login-empty | 이메일 | input | 성공  IoU 0.53 | 0.53 | 0.15 | 0.80 |
| login-empty | 비밀번호 | input | 성공  IoU 0.61 | 0.61 | 0.18 | 0.90 |
| login-empty | 로그인 | button | 적중만  IoU 0.33 | 0.33 | 0.15 | 0.90 |
| login-empty | 검색어 (없음) | input | 오탐 | - | - | 0.90 |
| login-empty | 약관 동의 (없음) | checkbox | 오탐 | - | - | 0.80 |
| login-filled | 이메일 | input | 성공  IoU 0.52 | 0.52 | 0.15 | 0.80 |
| login-filled | 비밀번호 | input | 성공  IoU 0.65 | 0.65 | 0.20 | 0.90 |
| login-filled | 로그인 | button | 적중만  IoU 0.44 | 0.44 | 0.21 | 0.80 |
| login-error | 이메일 | input | 실패  IoU 0.00 | 0.00 | 0.74 | 0.90 |
| login-error | 비밀번호 | input | 성공  IoU 0.67 | 0.67 | 0.18 | 0.90 |
| login-error | 로그인 | button | 적중만  IoU 0.26 | 0.26 | 0.16 | 0.90 |
| signup-empty | 이메일 | input | 성공  IoU 0.54 | 0.54 | 0.15 | 0.90 |
| signup-empty | 비밀번호 | input | 적중만  IoU 0.49 | 0.49 | 0.15 | 0.90 |
| signup-empty | 비밀번호 확인 | input | 적중만  IoU 0.49 | 0.49 | 0.17 | 0.90 |
| signup-empty | 닉네임 | input | 적중만  IoU 0.48 | 0.48 | 0.17 | 0.90 |
| signup-empty | 가입 경로 | select | 적중만  IoU 0.43 | 0.43 | 0.22 | 0.90 |
| signup-empty | 약관 동의 | checkbox | 실패  IoU 0.09 | 0.09 | 0.77 | 0.00 |
| signup-empty | 가입하기 | button | 적중만  IoU 0.11 | 0.11 | 0.24 | 0.90 |
| signup-empty | 로그인하러 가기 (없음) | link | 없다고 답함 (정답) | - | - | 0.00 |
| signup-error | 이메일 | input | 성공  IoU 0.56 | 0.56 | 0.15 | 0.90 |
| signup-error | 비밀번호 | input | 적중만  IoU 0.43 | 0.43 | 0.18 | 0.90 |
| signup-error | 비밀번호 확인 | input | 적중만  IoU 0.47 | 0.47 | 0.16 | 0.90 |
| signup-error | 닉네임 | input | 실패  IoU 0.00 | 0.00 | 0.73 | 0.80 |
| signup-error | 가입 경로 | select | 적중만  IoU 0.41 | 0.41 | 0.23 | 0.90 |
| signup-error | 약관 동의 | checkbox | 실패  IoU 0.16 | 0.16 | 0.71 | 0.00 |
| signup-error | 가입하기 | button | 적중만  IoU 0.28 | 0.28 | 0.35 | 0.90 |
| signup-welcome | 로그인하러 가기 | link | 적중만  IoU 0.45 | 0.45 | 0.39 | 0.80 |
| signup-welcome | 가입하기 (없음) | button | 오탐 | - | - | 0.80 |
| signup-welcome | 비밀번호 (없음) | input | 오탐 | - | - | 0.90 |
| search-empty | 검색어 | input | 성공  IoU 0.68 | 0.68 | 0.16 | 0.90 |
| search-empty | 검색 | button | 성공  IoU 0.81 | 0.81 | 0.10 | 0.90 |
| search-empty | 검색 결과 목록 (없음) | list | 오탐 | - | - | 0.80 |
| search-empty | 비밀번호 (없음) | input | 오탐 | - | - | 0.90 |
| search-results | 검색어 | input | 성공  IoU 0.81 | 0.81 | 0.09 | 0.90 |
| search-results | 검색 | button | 성공  IoU 0.58 | 0.58 | 0.13 | 0.90 |
| search-results | 검색 결과 목록 | list | 성공  IoU 0.65 | 0.65 | 0.11 | 0.90 |
| search-none | 검색어 | input | 성공  IoU 0.78 | 0.78 | 0.11 | 0.90 |
| search-none | 검색 | button | 성공  IoU 0.60 | 0.60 | 0.13 | 0.90 |
| search-none | 검색 결과 목록 (없음) | list | 없다고 답함 (정답) | - | - | 0.00 |
| nolabel-empty | 검색어 | input | 성공  IoU 0.68 | 0.68 | 0.16 | 0.90 |
| nolabel-empty | 검색 | button | 성공  IoU 0.82 | 0.82 | 0.09 | 0.90 |
| nolabel-empty | 검색 결과 목록 (없음) | list | 없다고 답함 (정답) | - | - | 0.00 |
| nolabel-results | 검색어 | input | 성공  IoU 0.63 | 0.63 | 0.22 | 0.90 |
| nolabel-results | 검색 | button | 성공  IoU 0.82 | 0.82 | 0.09 | 0.90 |
| nolabel-results | 검색 결과 목록 | list | 성공  IoU 0.66 | 0.66 | 0.11 | 0.90 |
| find-empty | 이메일 | input | 성공  IoU 0.54 | 0.54 | 0.15 | 0.95 |
| find-empty | 재설정 메일 받기 | button | 성공  IoU 0.65 | 0.65 | 0.19 | 0.90 |
| find-empty | 비밀번호 (없음) | input | 오탐 | - | - | 0.80 |
| find-sent | 이메일 | input | 적중만  IoU 0.48 | 0.48 | 0.18 | 0.90 |
| find-sent | 재설정 메일 받기 | button | 적중만  IoU 0.45 | 0.45 | 0.21 | 0.90 |
