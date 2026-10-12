# 화면기획서 — 사용자 표 (the-internet)

문서번호: EXT-TI-TABLES
작성일: 2026-09-27
작성자: 소인배 (사이트가 실제로 보이는 내용을 옮겨 적음)

## 1. 화면 개요

| 항목 | 내용 |
|---|---|
| 화면 ID | ti_tables |
| 화면명 | 사용자 표 |
| 화면 경로 | /tables |
| 설명 | 등록된 사용자의 이름·이메일·미납금을 표로 보여 주는 화면 |

## 2. UI 요소 정의

| 요소 ID | 유형 | 라벨 | 필수 | 입력 검증 규칙 | 안내 문구 | 에러 메시지 |
|---|---|---|---|---|---|---|
| user_list | 목록 | 사용자 목록 | - | - | - | - |
| last_name | 텍스트 | Last Name | - | - | - | - |
| due | 텍스트 | Due | - | - | - | - |

## 3. 성공 조건

화면에 진입하면 "Data Tables" 제목과 사용자 목록이 표시된다. 사용자 목록에는 아래
테스트 데이터의 사용자 4명이 한 행씩 표시된다.

## 4. 테스트 데이터

| Last Name | First Name | Email | Due |
|---|---|---|---|
| Smith | John | jsmith@gmail.com | $50.00 |
| Bach | Frank | fbach@yahoo.com | $51.00 |
| Doe | Jason | jdoe@hotmail.com | $100.00 |
| Conway | Tim | tconway@earthlink.net | $50.00 |
