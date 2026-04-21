#!/bin/bash
cd "$(dirname "$0")"

echo "====================================="
echo "  🚀 KHỞI ĐỘNG ANKI AI TAGGER WEB  "
echo "====================================="

# Khởi tạo venv nếu chưa có
if [ ! -d "venv" ]; then
    echo "Lần đầu tiên chạy, đang thiết lập thư viện (sẽ mất chút thời gian)..."
    python3 -m venv venv
fi

# Kích hoạt môi trường và cập nhật thư viện
source venv/bin/activate
pip install -r requirements.txt --quiet

# Chạy Web Server
python web_app.py
