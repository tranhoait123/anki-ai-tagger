import json
import requests

def invoke_anki(action, **params):
    """Hàm giao tiếp cơ sở với AnkiConnect qua Cổng 8765"""
    request_data = json.dumps({'action': action, 'params': params, 'version': 6})
    try:
        # Sử dụng 127.0.0.1 thay vì localhost để tránh lỗi phân giải IPv6 trên macOS
        response = requests.post('http://127.0.0.1:8765', data=request_data).json()
        if response.get('error'):
            raise Exception(response['error'])
        return response.get('result')
    except Exception as e:
        print(f"[LỖI ANKI] Không thể kết nối hoặc thực thi: {e}")
        return None

def get_deck_names():
    """Lấy danh sách toàn bộ Deck đang có trong Anki"""
    return invoke_anki('deckNames') or []

def get_tags():
    """Lấy danh sách toàn bộ Tag đang có trong Anki"""
    return invoke_anki('getTags') or []

def get_notes(deck_name, tag_name=""):
    """Lấy danh sách ID của các Note thuộc một Deck (và Tag tùy chọn)"""
    query = f'"deck:{deck_name}"'
    if tag_name:
        query += f' "tag:{tag_name}"'
    return invoke_anki('findNotes', query=query)

def get_notes_info(note_ids):
    """Lấy thông tin chi tiết (fields, tags) của các notes từ danh sách ID."""
    if not note_ids:
        return []
    return invoke_anki('notesInfo', notes=note_ids)

def add_tags(note_ids, tags):
    """Thêm một hoặc nhiều tag cho các notes."""
    if not note_ids:
        return False
    
    # AnkiConnect API yêu cầu tham số tags là một chuỗi phân tách bằng khoảng trắng,
    # chứ không phải một List (mảng). Vì vậy cần chuyển mảng thành chuỗi:
    if isinstance(tags, list):
        tags = " ".join(tags)
        
    return invoke_anki('addTags', notes=note_ids, tags=tags)
