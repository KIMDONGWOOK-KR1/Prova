# 화면기획서 — 로그인 (the-internet)

문서번호: EXT-HRK-001
작성일: 2026-09-23
작성자: 소인배 (사이트 안내 문구와 동작을 옮겨 적음)

## 1. 화면 개요

| 항목 | 내용 |
|---|---|
| 화면 ID | hrk_login |
| 화면명 | 로그인 |
| 화면 경로 | /login |
| 설명 | 사용자 이름과 비밀번호로 보안 영역에 들어가는 화면 |

## 2. UI 요소 정의

| 요소 ID | 유형 | 라벨 | 필수 | 입력 검증 규칙 | 안내 문구 | 에러 메시지 |
|---|---|---|---|---|---|---|
| username | 입력 | Username | - | - | - | - |
| password | 입력 | Password | - | - | - | - |
| login_btn | 버튼 | Login | - | - | - | - |

## 3. 성공 조건

등록된 사용자 이름과 비밀번호를 입력하면 `/secure` 로 이동하고
"You logged into a secure area!" 문구를 노출한다.

## 4. 실패 조건

| 상황 | 처리 |
|---|---|
| 등록되지 않은 사용자 이름 | "Your username is invalid!" 노출, 이동하지 않음 |
| 비밀번호가 틀림 | "Your password is invalid!" 노출, 이동하지 않음 |

## 5. 테스트 계정

| 사용자 이름 | 비밀번호 |
|---|---|
| tomsmith | SuperSecretPassword! |

## 6. 예시 동작

| 사용자 이름 | 비밀번호 | 노출돼야 하는 문구 |
|---|---|---|
| wronguser | SuperSecretPassword! | Your username is invalid! |
| tomsmith | wrongpassword | Your password is invalid! |
