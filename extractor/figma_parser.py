import json
import os

def create_mock_figma_data():
    """
    Figma 화면 정보를 딕셔너리와 리스트 구조로 구성하는 함수입니다.
    """
    # UI 요소들을 리스트(List) 안에 딕셔너리(Dictionary) 형태로 담습니다.
    ui_elements_list = [
        {
            "id": "node-101",
            "type": "INPUT_FIELD",
            "name": "이메일 입력창",
            "label": "이메일"
        },
        {
            "id": "node-102",
            "type": "INPUT_FIELD",
            "name": "비밀번호 입력창",
            "label": "비밀번호"
        },
        {
            "id": "node-103",
            "type": "BUTTON",
            "name": "회원가입 버튼",
            "text": "가입하기"
        }
    ]

    # 입력 조건과 에러 메시지를 매칭하는 리스트입니다.
    validation_rules = [
        {"element_id": "node-101", "condition": "이메일 미입력 (빈값)", "error": "필수 입력 메시지 표시"},
        {"element_id": "node-101", "condition": "이메일 형식 오류", "error": "이메일 형식 오류 메시지 표시"},
        {"element_id": "node-101", "condition": "중복 이메일", "error": "중복 가입 안내 메시지 표시"},
        {"element_id": "node-102", "condition": "짧은 비밀번호", "error": "비밀번호 길이 오류 표시"}
    ]

    # 최종적으로 JSON으로 만들 큰 딕셔너리입니다.
    figma_data = {
        "document": {
            "screen_name": "회원가입",
            "ui_elements": ui_elements_list,
            "validation_rules": validation_rules,
            "success_condition": {
                "action": "올바른 이메일과 비밀번호 입력 후 버튼 클릭",
                "expected_result": "가입 성공 후 로그인 화면 이동"
            }
        }
    }
    
    return figma_data

def save_to_json(data, folder_path, file_name):
    """
    생성된 딕셔너리 데이터를 JSON 파일로 저장하는 함수입니다.
    """
    # 폴더가 없으면 자동으로 생성해주는 안전장치입니다.
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
        
    file_path = os.path.join(folder_path, file_name)
    
    # 딕셔너리를 JSON 포맷으로 변환하여 파일에 씁니다.
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        
    print(f"✅ 성공: {file_path} 파일이 생성되었습니다!")

# 이 스크립트를 직접 실행할 때만 아래 코드가 작동합니다.
if __name__ == "__main__":
    # 1. 데이터를 생성하는 함수 호출
    extracted_data = create_mock_figma_data()
    # 2. JSON 파일로 저장하는 함수 호출
    save_to_json(extracted_data, folder_path="extractor/output", file_name="signup_test_data.json")
   