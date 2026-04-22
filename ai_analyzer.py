import google.generativeai as genai
from pydantic import BaseModel, Field
from typing import List
import time

import config

# Định nghĩa cấu trúc JSON trả về từ AI (Chain-of-Thought: yêu cầu AI lập luận trước khi đưa ra kết luận)
class CardAnalysis(BaseModel):
    note_id: int = Field(description="ID gốc của thẻ Anki.")
    reasoning: str = Field(description="Lập luận y khoa chi tiết: phân tích từng dấu hiệu trong thẻ, bám sát các gợi ý chuyên khoa.")
    suggested_tags: List[str] = Field(description="Danh sách các Tag phù hợp nhất được AI sinh ra dựa theo định dạng ở System Prompt.")
    confidence: float = Field(description="Độ tự tin trung bình của các Tag (0.0 đến 1.0).")

class BatchDiagnosisResult(BaseModel):
    results: List[CardAnalysis] = Field(description="Mảng danh sách lưu trữ kết quả phân tích đồng loạt cho toàn bộ các thẻ được yêu cầu.")

def analyze_batch_clinical_text(cards_batch: List[dict], system_prompt: str) -> BatchDiagnosisResult:
    """Gửi một Lô (Batch) danh sách thẻ và Tag gốc cho Gemini phân tích cùng lúc"""
    
    # Ghép thông tin danh sách thẻ thành văn bản Prompt
    batch_text = ""
    for card in cards_batch:
        batch_text += f"--- THẺ ID: {card['note_id']} ---\n"
        batch_text += f"- Tag Gốc: {', '.join(card['existing_tags']) if card['existing_tags'] else 'Không có'}\n"
        batch_text += f"- Nội Dung:\n{card['content']}\n\n"
        
    prompt = f"""
    HƯỚNG DẪN HỆ THỐNG DÀNH CHO BATCH PROCESSING:
    {system_prompt}
    
    BẠN SẼ NHẬN ĐƯỢC MỘT LÔ (BATCH) CÁC THẺ SAU ĐÂY:
    {batch_text}
    
    YÊU CẦU LẬP LUẬN LÂM SÀNG BẮT BUỘC (CHAIN-OF-THOUGHT) CHO MỖI THẺ:
    Mỗi thẻ được truyền phải có một bản ghi phản hồi riêng biệt trong mảng JSON `results`.
    Với mỗi thẻ (xác định qua `note_id`), bạn phải viết vào trường `reasoning` quá trình suy luận THẬT NGẮN GỌN (tổng cộng tối đa 30 từ):
    1. Cơ quan tổn thương / Phân hệ.
    2. Hội chứng / Bệnh lý nghi ngờ.
    3. Trích xuất Tag: Khẳng định keyword hoặc dùng Tag mặc định.
    
    Dựa vào lập luận, xuất các Tag mới vào `suggested_tags`. SỐ LƯỢNG VÀ TÊN TAG PHẢI TUÂN THỦ NGHIÊM NGẶT THEO QUY TẮC TRONG HƯỚNG DẪN HỆ THỐNG Ở TRÊN. Đảm bảo trả về mảng `results` bao hàm ĐẦY ĐỦ số lượng thẻ đã cho, không được bỏ sót thẻ nào!
    """

    max_attempts = len(config.GEMINI_API_KEYS)
    if max_attempts == 0:
        print("[LỖI AI] Không có API Key nào được cấu hình.")
        return None
        
    attempts = 0
    # Cấu hình an toàn để tránh bị chặn nội dung y khoa nhạy cảm
    safety_settings = {
        genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: genai.types.HarmBlockThreshold.BLOCK_NONE,
        genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
        genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: genai.types.HarmBlockThreshold.BLOCK_NONE,
        genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
    }

    while attempts < max_attempts:
        current_key = config.GEMINI_API_KEYS[config.CURRENT_KEY_INDEX].strip()
        if not current_key or current_key == "ĐIỀN_CÁC_API_KEY_CÁCH_NHAU_BỞI_DẤU_PHẨY":
            print("[LỖI AI] Chưa điền API Key hợp lệ.")
            return None
            
        genai.configure(api_key=current_key)
        model = genai.GenerativeModel(config.CURRENT_MODEL)
        
        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    response_schema=BatchDiagnosisResult,
                    temperature=0.0, # Kết quả mang tính logic chặt chẽ, lặp lại tốt nhất
                    max_output_tokens=65536 # Mở khoá tối đa đầu ra cho Gemini 3.1 (65k tokens)
                ),
                safety_settings=safety_settings
            )
            
            if not response.text:
                print(f"[CẢNH BÁO AI] Phản hồi trống từ Gemini. Có thể do nội dung bị chặn.")
                return None
                
            return BatchDiagnosisResult.model_validate_json(response.text)
        except Exception as e:
            error_msg = str(e).lower()
            
            # Ghi log chi tiết ra file để chẩn đoán chuyên sâu
            with open("ai_error_report.txt", "a", encoding="utf-8") as f:
                f.write(f"--- LỖI GIÂY THỨ {time.strftime('%H:%M:%S')} ---\n")
                f.write(f"Model: {config.CURRENT_MODEL}\n")
                f.write(f"Key: ...{current_key[-4:]}\n")
                f.write(f"Error: {str(e)}\n\n")

            # Kiểm tra các lỗi cần đổi Key: 429 (Hết hạn mức) hoặc 403 (Bị đình chỉ/Sai quyền)
            retry_keywords = ["429", "quota", "exhausted", "403", "forbidden", "permission", "suspended", "invalid"]
            if any(kw in error_msg for kw in retry_keywords):
                status_msg = "BỊ ĐÌNH CHỈ hoặc SAI QUYỀN (403)" if any(kw in error_msg for kw in ["403", "forbidden", "permission", "suspended"]) else "HẾT HẠN MỨC (429)"
                
                print(f"[CẢNH BÁO LỖI] API Key kết thúc bằng {current_key[-4:]} {status_msg}.")
                config.CURRENT_KEY_INDEX = (config.CURRENT_KEY_INDEX + 1) % max_attempts
                attempts += 1
                if attempts < max_attempts:
                    print(f"-> Tự động chuyển sang API Key dự phòng thứ {config.CURRENT_KEY_INDEX + 1}. Thử lại ngay...")
                    continue
                else:
                    print("[LỖI API] TẤT CẢ CÁC KHÓA BẠN CUNG CẤP ĐỀU ĐÃ VÔ HIỆU / HẾT HẠN MỨC!")
                    return None
            else:
                print(f"[LỖI AI] Lỗi hệ thống nghiêm trọng (Key: {current_key[-4:]}): {e}")
                return None
                
    return None
