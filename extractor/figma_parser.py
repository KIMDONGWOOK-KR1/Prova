import json
import os
import requests

def fetch_figma_data(file_key, token):
    """Figma API에서 원본 데이터를 가져옵니다."""
    url = f"https://api.figma.com/v1/files/{file_key}"
    headers = {"X-Figma-Token": token}
    
    print("Figma 서버에 데이터를 요청하는 중...")
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        print("✅ 원본 데이터 수신 성공!")
        return response.json()
    else:
        print(f"❌ 에러 발생: 상태 코드 {response.status_code}")
        return None

# --- 새롭게 추가된 데이터 필터링(추출) 함수 ---
def parse_figma_nodes(node, elements_list):
    """
    원본 데이터 구조를 반복적으로 파고들며 버튼과 입력창만 찾아냅니다.
    """
    # 노드에 이름(name) 정보가 없으면 패스합니다.
    node_name = node.get("name", "").lower()

    # 이름에 'button'이나 '버튼'이 포함된 경우 UI 요소로 추출
    if "button" in node_name or "버튼" in node_name:
        elements_list.append({
            "id": node.get("id"),
            "type": "BUTTON",
            "name": node.get("name"),
            # 화면 상의 좌표 정보를 함께 가져옵니다.
            "coordinates": node.get("absoluteBoundingBox", {}) 
        })
    # 이름에 'input'이나 '입력'이 포함된 경우 추출
    elif "input" in node_name or "입력" in node_name:
        elements_list.append({
            "id": node.get("id"),
            "type": "INPUT_FIELD",
            "name": node.get("name"),
            "coordinates": node.get("absoluteBoundingBox", {})
        })

    # 만약 이 상자 안에 더 작은 상자들(children)이 있다면, 
    # 반복문(for loop)을 돌면서 함수를 다시 실행해 안쪽까지 샅샅이 뒤집니다.
    if "children" in node:
        for child in node["children"]:
            parse_figma_nodes(child, elements_list)

def extract_core_requirements(raw_data):
    """
    원본 데이터에서 화면명, UI 요소, 입력 조건 등을 프로젝트 규격에 맞게 재조립합니다.
    """
    document_node = raw_data.get("document", {})
    
    # 빈 리스트를 만들고 필터링 함수에 넘겨주어 알맹이만 채워오게 합니다.
    extracted_elements = []
    parse_figma_nodes(document_node, extracted_elements)

    # 1차 MVP 대상인 '회원가입' 테스트 시나리오를 위한 기본 틀을 완성합니다.
    structured_data = {
        "document": {
            "screen_name": raw_data.get("name", "알 수 없는 화면"),
            "ui_elements": extracted_elements,
            # 설계 문서 추출 담당 파트의 요구사항인 에러 메시지와 성공 조건을 추가합니다.
            "validation_rules": [
                {"condition": "이메일 미입력", "error_message": "필수 입력 메시지 표시"},
                {"condition": "이메일 형식 오류", "error_message": "이메일 형식 오류 메시지 표시"},
                {"condition": "중복 이메일", "error_message": "중복 가입 안내 메시지 표시"},
                {"condition": "짧은 비밀번호", "error_message": "비밀번호 길이 오류 표시"}
            ],
            "success_condition": {
                "action": "올바른 이메일/비밀번호 입력 후 가입 버튼 클릭",
                "expected_result": "가입 성공 후 로그인 화면 이동"
            }
        }
    }
    return structured_data

def save_to_json(data, folder_path, file_name):
    """데이터를 JSON 파일로 저장합니다."""
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    file_path = os.path.join(folder_path, file_name)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"✅ 정제된 결과물이 {file_path}에 저장되었습니다!")

if __name__ == "__main__":
    MY_FIGMA_TOKEN = ""
    MY_FILE_KEY = ""
    
    # 1. API에서 원본 데이터를 가져옵니다.
    raw_figma_data = fetch_figma_data(MY_FILE_KEY, MY_FIGMA_TOKEN)
    
    if raw_figma_data:
        # 2. 원본 데이터에서 프로젝트에 필요한 정보(화면명, UI 요소, 조건 등)만 추출합니다.
        final_structured_data = extract_core_requirements(raw_figma_data)
        
        # 3. 추출된 깔끔한 데이터를 최종 JSON으로 저장합니다.
        save_to_json(final_structured_data, folder_path="extractor/output", file_name="final_extracted_data.json")