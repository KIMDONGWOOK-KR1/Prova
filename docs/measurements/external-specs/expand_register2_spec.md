# 화면기획서 — 회원가입 (Expand Testing)

문서번호: EXT-EXP-001
작성일: 2026-09-23
작성자: 소인배 (사이트가 공개한 Register Test Cases 1~4 를 옮겨 적음)

## 1. 화면 개요

| 항목 | 내용 |
|---|---|
| 화면 ID | exp_register |
| 화면명 | 회원가입 |
| 화면 경로 | /register |
| 설명 | 사용자 이름과 비밀번호로 계정을 만드는 화면 |

## 2. UI 요소 정의

| 요소 ID | 유형 | 라벨 | 필수 | 입력 검증 규칙 | 안내 문구 | 에러 메시지 |
|---|---|---|---|---|---|---|
| username | 입력 | Username | 필수 | - | - | - |
| password | 입력 | Password | 필수 | - | - | - |
| confirm_password | 입력 | Confirm Password | 필수 | Password 와 같아야 함 | - | Passwords do not match. |
| register_btn | 버튼 | Register | - | - | - | - |

### 2-1. 입력 검증 규칙 상세

**Confirm Password**
- Password 와 같은 값이어야 한다. 다르면 "Passwords do not match." 를 노출한다.

## 3. 성공 조건

모든 값을 올바르게 입력하면 `/login` 으로 이동하고
"Successfully registered, you can log in now." 문구를 노출한다.

## 4. 실패 조건

| 상황 | 처리 |
|---|---|
| 필수 입력값이 비어 있음 | "All fields are required." 노출, 이동하지 않음 |
| 비밀번호 확인이 다름 | "Passwords do not match." 노출, 이동하지 않음 |

## 5. 입력 예시 데이터

| Username | Password | Confirm Password |
|---|---|---|
| prova-probe-0923b | Secret123! | Secret123! |
