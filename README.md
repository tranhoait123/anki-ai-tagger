# Anki AI Tagger V2.2.0

Công cụ tự động phân tích và gắn thẻ (Tag) cho các Notes trong Anki dựa trên trí tuệ nhân tạo (Google Gemini API). Hệ thống này hoạt động theo mô hình Zero-Shot Classifier: AI tự đọc nội dung thẻ và tag gốc để suy luận ra hệ thống Tag y khoa phức tạp hoàn toàn tự động chỉ với 1 lần quét.

## Yêu cầu hệ thống

1. **Python 3.8+**
2. **Anki Desktop** đang mở và đã cài đặt Add-on **AnkiConnect** (Mã: `2055492159`).
3. Khóa API (API Key) từ **Google Gemini 2.5 Flash** (Miễn phí).

## Cài đặt nhanh

Mở Terminal (hoặc Command Prompt) và chạy các lệnh dưới đây để thiết lập môi trường:

```bash
# Tạo môi trường ảo (Khuyến nghị)
python -m venv venv
source venv/bin/activate

# Cài đặt thư viện cần thiết
pip install -r requirements.txt
```

## Khởi chạy ứng dụng (Web UI)

1. Đảm bảo phần mềm Anki đang được bật.
2. Trên **macOS**, bạn chỉ cần Click đúp vào file `Start_AI_Tagger.command` nằm trong thư mục cài đặt.
3. Trên **Windows/Linux**, mở terminal chạy lệnh:

```bash
python web_app.py
```

4. Trình duyệt sẽ tự động mở trang Dashboard trực quan.

## Chế độ xử lý

- **Quét tag chuyên khoa**: chọn một preset tag như Nhi khoa, Nội khoa, Giải phẫu rồi chạy.
- **Lọc thẻ**: chọn preset lọc như case lâm sàng, câu hỏi tiếng Anh, câu hỏi không đầy đủ.
- **Trùng lặp review**: app chọn cụm thẻ gần giống local rồi AI chỉ gắn tag review như `AI_DUP_REVIEW`, `AI_DUP_KEEP_CANDIDATE`, `AI_DUP_DELETE_CANDIDATE`, `AI_DUP_NEAR_KEEP_SEPARATE`; không xoá hoặc suspend thẻ.

## Preset tag/lọc

Các bộ tag và rule lọc nằm trong thư mục `presets/*.yaml`, không còn nhét trực tiếp trong `config.py`.

Mỗi preset có các phần chính:

- `kind`: `tagging`, `filter`, hoặc `duplicate_review`.
- `allowed_tags`: danh sách tag AI được phép trả về.
- `default_tag`: tag fallback khi không chắc chắn.
- `instructions`: rule/hướng dẫn phân loại.
- `skip_tags`: thẻ đã có các tag này sẽ bị bỏ qua.
- `fields_to_read`: field Anki cần gửi AI; để trống nghĩa là đọc tất cả field không bị exclude.

Trong Web UI, dùng panel **Quản lý Preset** để duplicate preset mặc định, sửa danh sách tag/rule, xem preview prompt và lưu thành preset mới.

Ứng dụng chỉ gắn tag trong Anki. Các thao tác xoá/suspend thẻ không còn nằm trong app để tránh mất dữ liệu ngoài ý muốn.

## Chú ý Bảo mật và Chi phí

- KHÔNG BAO GIỜ push API Key của bạn lên Github.
- Đối với API Key Free Tier, Google giới hạn 15 Lượt hỏi / 1 Phút. Tool đã tính toán trễ tự động để vừa vặn ngưỡng này, nhưng tốc độ sẽ khá chậm so với khối lượng vài ngàn thẻ.
- **Khuyến nghị**: Hãy nạp thanh toán vào Google Cloud Platform (GCP) để dùng gói Pay-as-you-go. Nó sẽ gỡ bỏ giới hạn tốc độ và quét xong toàn bộ bộ bài trong nháy mắt với chi phí rất rẻ. Mũi tên xanh sẽ chạy mượt hơn trên thanh Progress Bar.

Dự án này là hệ thống được mod hóa giúp cộng đồng tận dụng sự thông minh của AI để tiết kiệm hàng trăm giờ lao động tay chân.
