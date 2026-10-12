# 화면기획서 — 로그인 (Swag Labs)

문서번호: EXT-SAU-001
작성일: 2026-09-23
작성자: 소인배 (사이트의 공개 계정·문구를 옮겨 적음)

## 1. 화면 개요

| 항목 | 내용 |
|---|---|
| 화면 ID | sauce_login |
| 화면명 | 로그인 |
| 화면 경로 | / |
| 설명 | 사용자 이름과 비밀번호로 쇼핑몰에 로그인하는 화면 |

## 2. UI 요소 정의

| 요소 ID | 유형 | 라벨 | 필수 | 입력 검증 규칙 | 안내 문구 | 에러 메시지 |
|---|---|---|---|---|---|---|
| username | 입력 | Username | 필수 | - | Username | Epic sadface: Username is required |
| password | 입력 | Password | 필수 | - | Password | Epic sadface: Password is required |
| login_btn | 버튼 | Login | - | - | - | - |

### 2-1. 입력 검증 규칙 상세

**Username**
- 필수 입력이다. 비어 있으면 "Epic sadface: Username is required" 를 노출한다.

**Password**
- 필수 입력이다. 비어 있으면 "Epic sadface: Password is required" 를 노출한다.

## 3. 성공 조건

등록된 사용자 이름과 비밀번호를 입력하면 `/inventory.html` 로 이동하고
"Products" 문구를 노출한다.

## 4. 실패 조건

| 상황 | 처리 |
|---|---|
| 사용자 이름이 비어 있음 | "Epic sadface: Username is required" 노출, 이동하지 않음 |
| 비밀번호가 비어 있음 | "Epic sadface: Password is required" 노출, 이동하지 않음 |
| 계정 정보가 일치하지 않음 | "Epic sadface: Username and password do not match any user in this service" 노출, 이동하지 않음 |
| 잠긴 계정 | "Epic sadface: Sorry, this user has been locked out." 노출, 이동하지 않음 |

## 5. 테스트 계정

| Username | Password |
|---|---|
| standard_user | secret_sauce |

## 6. 예시 동작

| Username | Password | 노출돼야 하는 문구 |
|---|---|---|
| standard_user | wrong_password | Epic sadface: Username and password do not match any user in this service |
| locked_out_user | secret_sauce | Epic sadface: Sorry, this user has been locked out. |
