import os
import json
import logging
import webbrowser
import requests as req_lib
from threading import Timer
from flask import Flask, render_template, request, jsonify, Response
import config
from scanner import run_scan_generator
from anki_client import get_deck_names, get_tags

# Tắt log mặc định của Flask cho gọn Terminal
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)

@app.route("/")
def index():
    # Load config hiện tại lên giao diện
    try:
        available_decks = get_deck_names()
        available_tags = get_tags()
    except Exception as e:
        available_decks = []
        available_tags = []
        print(f"Lỗi tải danh sách Anki: {e}")
        
    return render_template(
        "index.html",
        api_keys=", ".join(getattr(config, 'GEMINI_API_KEYS', [])),
        deck=config.TARGET_DECK,
        source_tag=getattr(config, 'SOURCE_FILTER_TAG', ''),
        available_decks=available_decks,
        available_tags=available_tags,
        exclude=", ".join(getattr(config, 'FIELDS_TO_EXCLUDE', [])),
        system_prompt=getattr(config, 'SYSTEM_PROMPT', ''),
        specialty_prompts=getattr(config, 'SPECIALTY_PROMPTS', {}),
        available_models=getattr(config, 'AVAILABLE_MODELS', []),
        current_model=getattr(config, 'CURRENT_MODEL', 'gemini-3.1-flash-lite-preview')
    )

@app.route("/save_config", methods=["POST"])
def save_config():
    data = request.json
    
    # Cập nhật tạm thời config trên RAM cho phiên làm việc này
    keys_str = data.get("api_keys", "")
    if keys_str:
        config.GEMINI_API_KEYS = [k.strip() for k in keys_str.split(",") if k.strip()]
    config.CURRENT_KEY_INDEX = 0
    config.TARGET_DECK = data.get("deck", config.TARGET_DECK)
    config.SOURCE_FILTER_TAG = data.get("source_tag", "")
    config.CURRENT_MODEL = data.get("model", getattr(config, 'CURRENT_MODEL', 'gemini-3.1-flash-lite-preview'))
    
    exclude_str = data.get("exclude", "")
    config.FIELDS_TO_EXCLUDE = [x.strip() for x in exclude_str.split(",") if x.strip()]
    
    config.SYSTEM_PROMPT = data.get("system_prompt", getattr(config, 'SYSTEM_PROMPT', ''))
    
    return jsonify({"status": "success"})

@app.route("/duplicate-resolver")
def duplicate_resolver():
    return render_template("duplicate_resolver.html")

@app.route("/anki-proxy", methods=["POST"])
def anki_proxy():
    """Proxy AnkiConnect requests to avoid CORS issues in browser."""
    try:
        payload = request.get_json(force=True)
        resp = req_lib.post(
            'http://127.0.0.1:8765',
            json=payload,
            timeout=30
        )
        return jsonify(resp.json())
    except req_lib.exceptions.ConnectionError:
        return jsonify({"result": None, "error": "Không thể kết nối AnkiConnect. Hãy mở Anki và bật addon AnkiConnect."})
    except Exception as e:
        return jsonify({"result": None, "error": str(e)})

@app.route("/stop_scan", methods=["POST"])
def stop_scan():
    config.STOP_SCAN = True
    return jsonify({"status": "stopped"})

@app.route("/stream_scan")
def stream_scan():
    config.STOP_SCAN = False # Reset cờ mỗi khi quét mới
    def generate():
        for status_dict in run_scan_generator():
            # Format SSE (Server-Sent Events)
            yield f"data: {json.dumps(status_dict)}\n\n"
            
    return Response(generate(), mimetype="text/event-stream")

def open_browser():
    webbrowser.open_new('http://127.0.0.1:5500/')

if __name__ == "__main__":
    print("🚀 Đang khởi động Anki AI Web UI...")
    # Tự động mở trình duyệt sau 1.5 giây
    Timer(1.5, open_browser).start()
    app.run(host="127.0.0.1", port=5500, debug=True)
