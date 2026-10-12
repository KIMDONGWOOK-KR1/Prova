# 화면기획서 — 직원 표 검색 (demoqa)

문서번호: EXT-DQ-WEBTABLES
작성일: 2026-09-27
작성자: 소인배 (사이트가 실제로 보이는 내용을 옮겨 적음)

## 1. 화면 개요

| 항목 | 내용 |
|---|---|
| 화면 ID | dq_webtables |
| 화면명 | 직원 표 |
| 화면 경로 | /webtables |
| 설명 | 직원 목록을 표로 보여 주고, 검색어로 목록을 거르는 화면 |

## 2. UI 요소 정의

| 요소 ID | 유형 | 라벨 | 필수 | 입력 검증 규칙 | 안내 문구 | 에러 메시지 |
|---|---|---|---|---|---|---|
| search | 입력 | 검색어 | - | - | Type to search | - |
| employee_list | 목록 | 직원 목록 | - | - | - | - |
| first_name | 텍스트 | First Name | - | - | - | - |
| salary | 텍스트 | Salary | - | - | - | - |

### 2-1. 검색 동작 규칙

- 검색어를 입력하는 즉시 목록을 거른다. 별도의 검색 버튼은 누르지 않는다.
- 어느 열이든 검색어를 포함하는 직원만 남긴다. 영문 대소문자를 구분하지 않는다.
- 일치하는 직원이 없으면 목록에 행이 남지 않는다.

## 3. 성공 조건

화면에 진입하면 직원 목록에 아래 테스트 데이터의 직원 3명이 표시된다.

## 4. 테스트 데이터

| First Name | Last Name | Age | Email | Salary | Department |
|---|---|---|---|---|---|
| Cierra | Vega | 39 | cierra@example.com | 10000 | Insurance |
| Alden | Cantrell | 45 | alden@example.com | 12000 | Compliance |
| Kierra | Gentry | 29 | kierra@example.com | 2000 | Legal |

## 5. 예시 검색

| 검색어 | 결과 건수 |
|---|---|
| cierra | 1 |
| ierra | 2 |
| zzzz | 0 |
