# 화면기획서 — 상품 목록 (saucedemo, 로그인 전제)

문서번호: EXT-SD-INVENTORY
작성일: 2026-09-27
작성자: 소인배 (사이트가 실제로 보이는 내용을 옮겨 적음)

이 문서는 상품 목록 화면과 그 전제인 로그인 화면을 한 문서에 담는다.

## 1. 화면 개요

| 항목 | 내용 |
|---|---|
| 화면 ID | sd_login |
| 화면명 | 로그인 |
| 화면 경로 | / |
| 설명 | 사용자 이름과 비밀번호로 로그인하는 화면 |

## 2. UI 요소 정의

| 요소 ID | 유형 | 라벨 | 필수 | 입력 검증 규칙 | 안내 문구 | 에러 메시지 |
|---|---|---|---|---|---|---|
| username | 입력 | Username | 필수 | - | Username | - |
| password | 입력 | Password | 필수 | - | Password | - |
| login_btn | 버튼 | Login | - | - | - | - |

## 3. 성공 조건

등록된 계정으로 로그인하면 `/inventory.html` 로 이동하고 "Products" 문구를 노출한다.

## 4. 실패 조건

| 상황 | 처리 |
|---|---|
| 사용자 이름이 비어 있음 | "Epic sadface: Username is required" 노출 |

## 5. 테스트 계정

| Username | Password |
|---|---|
| standard_user | secret_sauce |

<!-- page -->

## 1. 화면 개요

| 항목 | 내용 |
|---|---|
| 화면 ID | sd_inventory |
| 화면명 | 상품 목록 |
| 화면 경로 | /inventory.html |

## 2. UI 요소 정의

| 요소 ID | 유형 | 라벨 | 필수 | 입력 검증 규칙 | 안내 문구 | 에러 메시지 |
|---|---|---|---|---|---|---|
| product_list | 목록 | 상품 목록 | - | - | - | - |
| product_name | 텍스트 | 상품명 | - | - | - | - |
| price | 텍스트 | 가격 | - | - | - | - |
| sort | 선택 | Sort products | - | 선택 목록: Name (A to Z), Name (Z to A), Price (low to high), Price (high to low) | - | - |

## 3. 성공 조건

화면에 진입하면 "Products" 제목과 상품 목록이 표시된다. 상품 목록에는 아래 테스트
데이터의 상품 6개가 한 항목씩 표시된다. 처음에는 상품명 오름차순(A to Z)이다.
정렬에서 "Price (high to low)" 를 고르면 가격 내림차순으로 다시 표시한다.

## 4. 전제

이 화면은 로그인한 상태에서 동작한다. 비로그인 상태로 접근하면 로그인 화면으로 이동시킨다.

| Username | Password |
|---|---|
| standard_user | secret_sauce |

## 5. 테스트 상품 데이터

| 상품명 | 가격 |
|---|---|
| Sauce Labs Backpack | $29.99 |
| Sauce Labs Bike Light | $9.99 |
| Sauce Labs Bolt T-Shirt | $15.99 |
| Sauce Labs Fleece Jacket | $49.99 |
| Sauce Labs Onesie | $7.99 |
| Test.allTheThings() T-Shirt (Red) | $15.99 |
