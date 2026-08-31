# VLM 탐지 정확도 — Qwen2.5-VL-3B-Instruct-AWQ (2026-08-31)

`scripts/eval_vlm_iou.py` 의 출력을 그대로 옮긴 것이다. 보고에 쓰는 숫자는 이
파일이고, `runs/iou/` 의 연습 실행과 섞지 않는다. 해석은 `docs/teaching/13-vlm-fallback.md`.

시험지를 다시 굳힌 뒤의 채점이다(`8f3de91023aa` · 18화면 77항목). 08-28 채점은
주문조회·상품등록의 스크린샷이 낡아 있었다 — 그 문서 머리의 정정을 함께 보라.

- 데이터셋 `8f3de91023aa` · 화면 18장 · 항목 77개 (있음 63 · 없음 14)
- IoU 문턱값 0.5 · 신뢰도 문턱값 0.5

## 결과

| 지표 | 값 | 뜻 |
|---|---|---|
| 탐지 성공률 (IoU 기준) | 36/63 = 57.1% | 명세서 §9 가 요구한 지표 |
| 적중률 (중심이 요소 안) | 57/63 = 90.5% | 실제로 클릭이 되는 비율 |
| 오탐 (없는 것을 찾았다고 함) | 10/14 = 71.4% | 낮아야 한다 |
| 관문이 버린 정답 | 0개 | 크면 고칠 곳은 모델이 아니라 문턱값이다 |
| 호출 실패 | 0개 | 서버·응답 문제 |
| 평균 IoU | 0.504 | |
| 호출 시간 | 평균 839ms · 최대 2465ms | |

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
| product-empty | 3/4 = 75.0% | 2개 |
| product-error | 2/4 = 50.0% | 0개 |
| orders-list | 2/6 = 33.3% | 1개 |
| orders-empty | 3/4 = 75.0% | 0개 |
| table-orders | 5/5 = 100.0% | 0개 |

## 항목별

| 화면 | 요소 | 종류 | 결과 | IoU | 중심오차 | 신뢰도 |
|---|---|---|---|---|---|---|
| login-empty | 이메일 | input | 성공  IoU 0.50 | 0.50 | 0.16 | 0.90 |
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
| product-empty | 상품명 | input | 성공  IoU 0.76 | 0.76 | 0.12 | 0.99 |
| product-empty | 가격 | input | 성공  IoU 0.65 | 0.65 | 0.18 | 0.99 |
| product-empty | 재고수량 | input | 성공  IoU 0.62 | 0.62 | 0.21 | 0.90 |
| product-empty | 등록하기 | button | 적중만  IoU 0.35 | 0.35 | 0.24 | 0.90 |
| product-empty | 비밀번호 (없음) | input | 오탐 | - | - | 0.90 |
| product-empty | 검색어 (없음) | input | 오탐 | - | - | 0.90 |
| product-error | 상품명 | input | 적중만  IoU 0.49 | 0.49 | 0.15 | 0.80 |
| product-error | 가격 | input | 성공  IoU 0.64 | 0.64 | 0.19 | 0.90 |
| product-error | 재고수량 | input | 성공  IoU 0.51 | 0.51 | 0.14 | 0.90 |
| product-error | 등록하기 | button | 적중만  IoU 0.16 | 0.16 | 0.26 | 0.90 |
| orders-list | 시작일 | date | 성공  IoU 0.62 | 0.62 | 0.21 | 0.90 |
| orders-list | 종료일 | date | 적중만  IoU 0.50 | 0.50 | 0.33 | 0.90 |
| orders-list | 상태 | select | 성공  IoU 0.53 | 0.53 | 0.21 | 0.95 |
| orders-list | 조회 | button | 적중만  IoU 0.48 | 0.48 | 0.19 | 0.90 |
| orders-list | 주문 목록 | list | 실패  IoU 0.00 | 0.00 | 0.96 | 0.90 |
| orders-list | 합계 | text | 실패  IoU 0.00 | 0.00 | 4.31 | 0.90 |
| orders-list | 비밀번호 (없음) | input | 오탐 | - | - | 0.90 |
| orders-empty | 시작일 | date | 성공  IoU 0.58 | 0.58 | 0.14 | 0.90 |
| orders-empty | 종료일 | date | 성공  IoU 0.59 | 0.59 | 0.14 | 0.90 |
| orders-empty | 상태 | select | 성공  IoU 0.54 | 0.54 | 0.11 | 0.95 |
| orders-empty | 조회 | button | 적중만  IoU 0.47 | 0.47 | 0.18 | 0.90 |
| orders-empty | 비밀번호 (없음) | input | 없다고 답함 (정답) | - | - | 0.00 |
| table-orders | 시작일 | date | 성공  IoU 0.80 | 0.80 | 0.09 | 0.90 |
| table-orders | 종료일 | date | 성공  IoU 0.60 | 0.60 | 0.19 | 0.90 |
| table-orders | 상태 | select | 성공  IoU 0.62 | 0.62 | 0.05 | 0.95 |
| table-orders | 조회 | button | 성공  IoU 0.51 | 0.51 | 0.14 | 0.90 |
| table-orders | 주문 목록 | list | 성공  IoU 0.72 | 0.72 | 0.12 | 0.90 |

## 옛 화면과 새 화면을 나눠 보면

| 부분 | 탐지 성공 (IoU) | 적중 | 오탐 |
|---|---|---|---|
| 옛 13화면 (08-22 와 같은 항목) | 21/40 = 52.5% | 36/40 = 90.0% | 7/10 = 70.0% |
| 새 5화면 (product·orders·table) | 15/23 = 65.2% | 21/23 = 91.3% | 3/4 = 75.0% |

**옛 13화면은 세 번째 측정에서도 21/40 그대로다** — 08-22 · 08-28 · 08-31 이 한 자리도
다르지 않다. 채점이 재현된다는 뜻이고, 그래서 다른 숫자가 움직이면 원인을 다른
곳에서 찾을 수 있다.

새 5화면은 08-28 의 `7/20 = 35.0%` 에서 `15/23 = 65.2%` 로 올랐다. 모델이 좋아진 것이
아니라 **그때 그림이 낡아 정답 상자와 어긋나 있었다.** 다시 굳히니 제자리로 왔다.
"새로 넣은 화면이 어렵다" 던 08-28 의 해석은 절반이 계측 탓이었다.

## 새로 넣은 상태 select

| 화면 | IoU | 적중 |
|---|---|---|
| orders-list | 0.53 | O |
| orders-empty | 0.54 | O |
| table-orders | 0.62 | O |

셋 다 문턱을 넘었다. 시험지에 요소를 더하면 점수가 내려갈 것으로 봤는데 그렇지
않았다 — 회원가입의 '가입 경로' select 가 0.43 으로 못 넘는 것과 대비된다. 주문조회
쪽 select 가 더 크고 주변이 비어 있다.

## 여전히 문턱값 0.5 부근에 몰려 있다

적중률 90.5% 와 IoU 성공률 57.1% 의 간격이 그것이다. 중심은 요소 안인데 상자가
헐거워 문턱을 못 넘는 항목이 많다 — 클릭은 되고 점수는 실패인 자리다.
**그래도 문턱값을 낮추지 않는다.** 지표를 움직여 점수를 올리는 것은 측정이 아니다.
