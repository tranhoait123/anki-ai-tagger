import time
import config
from anki_client import get_notes, get_notes_info, add_tags
from ai_analyzer import analyze_batch_clinical_text

def run_scan_generator():
    source_tag_msg = f" (Giới hạn trong Tag: {config.SOURCE_FILTER_TAG})" if getattr(config, 'SOURCE_FILTER_TAG', '') else " (Toàn bộ Deck)"
    yield {"type": "info", "msg": f"Bắt đầu quét Deck: {config.TARGET_DECK}{source_tag_msg}"}
    
    if not hasattr(config, 'GEMINI_API_KEYS') or not config.GEMINI_API_KEYS or config.GEMINI_API_KEYS[0] == "ĐIỀN_CÁC_API_KEY_CÁCH_NHAU_BỞI_DẤU_PHẨY":
        yield {"type": "error", "msg": "Lỗi Cấu Hình: Chưa điền API Key trong file config.py."}
        return

    # 1. Tìm các notes trong deck với bộ lọc tag phụ thêm (nếu có)
    tag_filter = getattr(config, 'SOURCE_FILTER_TAG', '')
    note_ids = get_notes(config.TARGET_DECK, tag_filter)
    
    if not note_ids:
        yield {"type": "error", "msg": "Không tìm thấy thẻ nào hoặc sai tên Deck / Anki chưa mở."}
        return
        
    yield {"type": "info", "msg": f"Đã tìm thấy {len(note_ids)} thẻ. Bắt đầu phân tích..."}
    
    # Xác định chế độ quét ngay từ đầu để log chẩn đoán
    prompt_norm = config.SYSTEM_PROMPT.strip().replace("\r\n", "\n")
    case_prompt_norm = config.SPECIALTY_PROMPTS.get("Case_lam_sang", "").strip().replace("\r\n", "\n")
    qa_prompt_norm = config.SPECIALTY_PROMPTS.get("Chat_hoi_dap", "").strip().replace("\r\n", "\n")
    is_clinical_mode = (prompt_norm == case_prompt_norm) or ("Xác định xem nội dung thẻ Anki có phải là một \"Ca lâm sàng\"" in config.SYSTEM_PROMPT)
    is_qa_mode = (prompt_norm == qa_prompt_norm) or ("CÂU HỎI THỰC SỰ" in config.SYSTEM_PROMPT and "CÂU HỎI KHÔNG ĐẦY ĐỦ" in config.SYSTEM_PROMPT)
    
    mode_name = "Nhận diện Câu hỏi" if is_qa_mode else ("Case lâm sàng" if is_clinical_mode else "Chuyên khoa")
    yield {"type": "info", "msg": f"[*] Chế độ nhận diện: <b>{mode_name}</b>"}

    # Lấy thông tin chi tiết của các notes
    notes_info = get_notes_info(note_ids)
    tagged_count = 0
    total = len(notes_info)
    
    # 2. Xử lý từng note
    batch_buffer = []
    
    for idx, note in enumerate(notes_info):
        note_id = note['noteId']
        
        # Cập nhật tiến trình
        yield {"type": "progress", "current": idx + 1, "total": total}
        
        # Kiểm tra cờ dừng khẩn cấp
        if getattr(config, 'STOP_SCAN', False):
            yield {"type": "warning", "msg": "🛑 ĐÃ DỪNG LẠI THEO YÊU CẦU CỦA BẠN."}
            break
            
        # Thu thập nội dung từ tất cả các trường (fields)
        content_parts = []
        for field_name, field_data in note['fields'].items():
            if hasattr(config, 'FIELDS_TO_EXCLUDE') and field_name in config.FIELDS_TO_EXCLUDE:
                continue
                
            val = field_data.get('value', '').strip()
            if val and val != "<div><br></div>" and val != "<br>":
                content_parts.append(f"[{field_name}]: {val}")
                
        content = "\n".join(content_parts)
        
        if len(content.strip()) < 10:
            # Vẫn vứt báo lỗi siêu nhanh nếu cần, nhưng chỉ log ẩn để đỡ giật hình
            continue
            
        # Rút xuất các Tag đã có sẵn trên thẻ
        existing_tags = note.get('tags', [])
        
        # Kiểm tra xem thẻ đã được xử lý chưa
        if is_qa_mode:
            # Trong chế độ Nhận diện Câu hỏi: Bỏ qua nếu đã có tag kết quả
            if any(tag in ['cau_hoi_hoan_chinh', 'cau_hoi_khong_day_du'] for tag in existing_tags):
                continue
        elif is_clinical_mode:
            # Trong chế độ Case Lâm Sàng: Bỏ qua nếu đã có tag kết quả lâm sàng
            if any(tag in ['case_lam_sang', '0_xac_dinh_case'] for tag in existing_tags):
                continue
        else:
            # Chế độ Chuyên Khoa: Bỏ qua nếu đã có bất kỳ Tag AI:: nào
            if any(tag.startswith('AI::') for tag in existing_tags):
                continue
            
        # Nạp thẻ hợp lệ vào Cỗ Máy Nhồi Lô (Buffer)
        batch_buffer.append({
            'note_id': note_id,
            'existing_tags': existing_tags,
            'content': content
        })
        
        # Kiểm tra xem Bộ Nhồi Lô đã Đầy, HOẶC đây là thẻ cuối cùng hay chưa?
        if len(batch_buffer) >= getattr(config, 'BATCH_SIZE', 15) or idx == total - 1:
            if not batch_buffer:
                continue 
                
            # 3. Phóng Lô (Batch) lên AI
            yield {"type": "info", "msg": f"Đang gửi {len(batch_buffer)} thẻ cho AI phân tích đồng loạt..."}
            batch_result = analyze_batch_clinical_text(batch_buffer, config.SYSTEM_PROMPT)
            
            if batch_result and batch_result.results:
                for res in batch_result.results:
                    new_tags = [tag.strip() for tag in res.suggested_tags if tag.strip()]
                    
                    if new_tags:
                        # 4. Thực thi gắn Nhóm Tag mới
                        add_tags([res.note_id], new_tags)
                        tagged_count += 1
                        tags_str = ", ".join(new_tags)
                        yield {"type": "success", "msg": f"Đã gắn tags '{tags_str}' cho NoteID: {res.note_id}<br><b>Lập luận:</b> {res.reasoning} (Độ tin cậy: {res.confidence:.2f})"}
                    else:
                        yield {"type": "warning", "msg": f"Bỏ qua NoteID: {res.note_id}. Không có dữ kiện đủ đặc hiệu."}
            else:
                yield {"type": "error", "msg": "Lỗi phân tích Lô hoặc AI bị sập/chặn."}
                
            # Xả rỗng Cỗ Máy Nhồi Lô để chuẩn bị cho nhóm tiếp theo
            batch_buffer = []
            time.sleep(1)

    yield {"type": "done", "msg": f"HOÀN TẤT! Đã gắn tag thành công cho {tagged_count}/{len(note_ids)} thẻ."}

