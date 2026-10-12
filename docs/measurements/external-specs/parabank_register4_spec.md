# 화면기획서 — 회원가입 (ParaBank)

문서번호: EXT-PB-001
작성일: 2026-09-23
작성자: 소인배 (사이트가 실제로 보이는 문구를 옮겨 적음 — 공개 문서 없음)

## 1. 화면 개요

| 항목 | 내용 |
|---|---|
| 화면 ID | pb_register |
| 화면명 | 회원가입 |
| 화면 경로 | /parabank/register.htm |
| 설명 | 고객 정보와 계정을 입력해 은행 계정을 여는 화면 |

## 2. UI 요소 정의

| 요소 ID | 유형 | 라벨 | 필수 | 입력 검증 규칙 | 안내 문구 | 에러 메시지 |
|---|---|---|---|---|---|---|
| first_name | 입력 | First Name | 필수 | - | - | First name is required. |
| last_name | 입력 | Last Name | 필수 | - | - | Last name is required. |
| address | 입력 | Address | 필수 | - | - | Address is required. |
| city | 입력 | City | 필수 | - | - | City is required. |
| state | 입력 | State | 필수 | - | - | State is required. |
| zip | 입력 | Zip Code | 필수 | - | - | Zip Code is required. |
| phone | 입력 | Phone # | - | - | - | - |
| ssn | 입력 | SSN | 필수 | - | - | Social Security Number is required. |
| username | 입력 | Username | 필수 | - | - | Username is required. |
| password | 입력 | Password | 필수 | - | - | Password is required. |
| confirm | 입력 | Confirm | 필수 | Password 와 같아야 함 | - | Passwords did not match. |
| register_btn | 버튼 | Register | - | - | - | - |

### 2-1. 입력 검증 규칙 상세

**Confirm**
- 필수 입력이다. 비어 있으면 "Password confirmation is required." 를 노출한다.
- Password 와 같은 값이어야 한다. 다르면 "Passwords did not match." 를 노출한다.

## 3. 성공 조건

모든 필수 값을 올바르게 입력하면
"Your account was created successfully. You are now logged in." 문구를 노출한다.

## 4. 실패 조건

| 상황 | 처리 |
|---|---|
| 필수 입력값이 비어 있음 | 해당 칸 옆에 칸별 에러 메시지 노출 |
| 비밀번호 확인이 다름 | "Passwords did not match." 노출 |

## 5. 입력 예시 데이터

| First Name | Last Name | Address | City | State | Zip Code | SSN | Username | Password | Confirm |
|---|---|---|---|---|---|---|---|---|---|
| Prova | Probe | 1 Test St | Gwangju | GJ | 61186 | 123-45-6789 | prova_probe_0923d | Secret123 | Secret123 |
