# Anki AI Tagger V2.1.0

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

Hệ thống này giúp bạn giải quyết tình trạng thẻ trùng lặp một cách thông minh bằng cách so sánh nội dung và giữ lại thẻ có lịch sử ôn tập tốt nhất.

## Công cụ xoá trùng lặp (CLI - Chạy nền)

Nếu giao diện Web load chậm do dữ liệu quá lớn, bạn có thể chạy trực tiếp script Python để giải quyết thẻ trùng lặp:

```bash
# Bật môi trường ảo (nếu chưa bật)
source venv/bin/activate

# 1. Xem thử các thẻ trùng (không xoá gì cả)
python deduplicate.py --scan-all --dry-run

# 2. Xoá trùng lặp tự động (chọn thẻ tốt nhất để giữ lại)
python deduplicate.py --scan-all

# Các tuỳ chọn khác:
# --field Front      : So sánh theo field cụ thể (Mặc định: Front)
# --fuzzy            : Tìm thẻ gần giống nhau (độ chính xác 90%)
# --tag duplicate    : Chỉ tìm thẻ có tag cụ thể (Mặc định: duplicate)
```

## Chú ý Bảo mật và Chi phí

- KHÔNG BAO GIỜ push API Key của bạn lên Github.
- Đối với API Key Free Tier, Google giới hạn 15 Lượt hỏi / 1 Phút. Tool đã tính toán trễ tự động để vừa vặn ngưỡng này, nhưng tốc độ sẽ khá chậm so với khối lượng vài ngàn thẻ.
- **Khuyến nghị**: Hãy nạp thanh toán vào Google Cloud Platform (GCP) để dùng gói Pay-as-you-go. Nó sẽ gỡ bỏ giới hạn tốc độ và quét xong toàn bộ bộ bài trong nháy mắt với chi phí rất rẻ. Mũi tên xanh sẽ chạy mượt hơn trên thanh Progress Bar.

Dự án này là hệ thống được mod hóa giúp cộng đồng tận dụng sự thông minh của AI để tiết kiệm hàng trăm giờ lao động tay chân.
