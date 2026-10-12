# 화면기획서 — 연습용 로그인 (Practice Test Automation)

문서번호: EXT-PTA-001
작성일: 2026-09-23
작성자: 소인배 (사이트가 공개한 테스트 케이스를 옮겨 적음)

## 1. 화면 개요

| 항목 | 내용 |
|---|---|
| 화면 ID | pta_login |
| 화면명 | 연습용 로그인 |
| 화면 경로 | /practice-test-login/ |
| 설명 | 사용자 이름과 비밀번호로 로그인하는 연습용 화면 |

## 2. UI 요소 정의

| 요소 ID | 유형 | 라벨 | 필수 | 입력 검증 규칙 | 안내 문구 | 에러 메시지 |
|---|---|---|---|---|---|---|
| username | 입력 | Username | - | - | - | - |
| password | 입력 | Password | - | - | - | - |
| submit | 버튼 | Submit | - | - | - | - |

## 3. 성공 조건

등록된 사용자 이름과 비밀번호를 입력하면 `/logged-in-successfully/` 로 이동하고
"Congratulations" 문구를 노출한다.

## 4. 실패 조건

| 상황 | 처리 |
|---|---|
| 등록되지 않은 사용자 이름 | "Your username is invalid!" 노출, 이동하지 않음 |
| 비밀번호가 틀림 | "Your password is invalid!" 노출, 이동하지 않음 |

## 5. 테스트 계정

| 사용자 이름 | 비밀번호 |
|---|---|
| student | Password123 |

## 6. 예시 동작

| 사용자 이름 | 비밀번호 | 노출돼야 하는 문구 |
|---|---|---|
| incorrectUser | Password123 | Your username is invalid! |
| student | incorrectPassword | Your password is invalid! |
