import os

# ================= CẤU HÌNH NGƯỜI DÙNG =================
GEMINI_API_KEYS = [os.environ.get("GEMINI_API_KEY", "ĐIỀN_CÁC_API_KEY_CÁCH_NHAU_BỞI_DẤU_PHẨY")]
CURRENT_KEY_INDEX = 0

AVAILABLE_MODELS = [
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite-preview-02-05",
    "gemini-2.0-pro-exp-02-05",
    "gemini-2.0-flash-exp",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemma-4-31b-it",
    "gemma-2-27b-it",
    "gemma-2-9b-it"
]
CURRENT_MODEL = "gemini-3.1-flash-lite-preview"

# 1. Cấu hình vị trí dữ liệu Anki
TARGET_DECK = "Nhi_Khoa"
SOURCE_FILTER_TAG = ""
FIELDS_TO_EXCLUDE = ["Note", "Source", "Tags", "Ex"]

# 2. Preset đang dùng. Nội dung preset nằm trong thư mục presets/*.yaml.
CURRENT_PRESET_ID = "Nhi_khoa"
CURRENT_PRESET = None
SYSTEM_PROMPT = ""
SYSTEM_PROMPT_OVERRIDE = ""

# 3. Cách chọn thẻ
CARD_SELECTION_MODE = "sequential"
SIMILAR_FIELD_MODE = "Ques, A, B, C, D"
SIMILAR_SEED_KEYWORD = ""

# 4. Cờ hiệu trạng thái hệ thống
STOP_SCAN = False

# 5. Kích thước lô và giới hạn chạy
BATCH_SIZE = 500
MAX_CARDS_PER_RUN = None
