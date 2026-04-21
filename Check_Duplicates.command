#!/bin/zsh
# Start Duplicate Resolver CLI via terminal
cd "$(dirname "$0")"

if [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "--------------------------------------------------------"
echo "🔍 LỰA CHỌN PHẠM VI QUÉT TRÙNG LẶP:"
echo "--------------------------------------------------------"
echo "1. CHỈ so sánh Câu hỏi (Trường 'Ques'):"
echo "   python3 deduplicate.py --field Ques --dry-run"
echo ""
echo "2. So sánh TOÀN BỘ (Ques + Đáp án A,B,C,D,E):"
echo "   python3 deduplicate.py --field \"Ques,A,B,C,D,E\" --dry-run"
echo "--------------------------------------------------------"

echo "\n🔍 Đang chạy quét thử mặc định (TOÀN BỘ)..."
python3 deduplicate.py --field "Ques,A,B,C,D,E" --dry-run

echo "\n--------------------------------------------------------"
echo "❓ NẾU BẠN MUỐN QUÉT CHỈ THEO 'QUES', HÃY CHẠY LỆNH SAU:"
echo "python3 deduplicate.py --field Ques"
echo "--------------------------------------------------------"

# Giữ cửa sổ terminal mở để xem kết quả
zsh
