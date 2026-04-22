import os
import json
import logging
import webbrowser
import requests as req_lib
from threading import Lock, Thread, Timer
from flask import Flask, render_template, request, jsonify, Response
import config
from scanner import run_scan_generator
from anki_client import get_deck_names, get_tags

# Tắt log mặc định của Flask cho gọn Terminal
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)

BACKGROUND_LOG_LIMIT = 500
background_lock = Lock()
background_job = {
    "id": 0,
    "status": "idle",
    "logs": [],
    "next_seq": 1,
    "progress": None,
    "thread": None,
    "message": "Chưa có job nền nào đang chạy."
}


def apply_config_from_payload(data):
    """Cập nhật config trên RAM từ dữ liệu form."""
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

    batch_size = data.get("batch_size")
    if batch_size:
        try:
            config.BATCH_SIZE = int(batch_size)
        except ValueError:
            config.BATCH_SIZE = 50

    limit = data.get("limit")
    if limit is not None and str(limit).strip() != "":
        try:
            config.MAX_CARDS_PER_RUN = int(limit)
        except ValueError:
            config.MAX_CARDS_PER_RUN = None
    else:
        config.MAX_CARDS_PER_RUN = None


def append_background_log(status_dict):
    with background_lock:
        entry = dict(status_dict)
        entry["seq"] = background_job["next_seq"]
        background_job["next_seq"] += 1

        if entry.get("type") == "progress":
            background_job["progress"] = {
                "current": entry.get("current", 0),
                "total": entry.get("total", 0)
            }
        else:
            background_job["logs"].append(entry)
            if len(background_job["logs"]) > BACKGROUND_LOG_LIMIT:
                background_job["logs"] = background_job["logs"][-BACKGROUND_LOG_LIMIT:]


def background_scan_worker(job_id):
    try:
        append_background_log({"type": "info", "msg": "Đã khởi động job nền. Bạn có thể refresh trang, terminal vẫn nối lại được."})
        for status_dict in run_scan_generator():
            with background_lock:
                if background_job["id"] != job_id:
                    return

            append_background_log(status_dict)

            if status_dict.get("type") == "done":
                with background_lock:
                    background_job["status"] = "done"
                    background_job["message"] = status_dict.get("msg", "Job nền đã hoàn tất.")
                return

        with background_lock:
            if background_job["id"] == job_id and background_job["status"] not in ("done", "error"):
                background_job["status"] = "done"
                background_job["message"] = "Job nền đã kết thúc."
    except Exception as e:
        append_background_log({"type": "error", "msg": f"Lỗi job nền: {e}"})
        with background_lock:
            if background_job["id"] == job_id:
                background_job["status"] = "error"
                background_job["message"] = str(e)

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
        current_model=getattr(config, 'CURRENT_MODEL', 'gemini-3.1-flash-lite-preview'),
        max_cards=getattr(config, 'MAX_CARDS_PER_RUN', '') if getattr(config, 'MAX_CARDS_PER_RUN', None) is not None else '',
        batch_size=getattr(config, 'BATCH_SIZE', 50)
    )

@app.route("/save_config", methods=["POST"])
def save_config():
    apply_config_from_payload(request.json or {})
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
    with background_lock:
        if background_job["status"] == "running":
            background_job["status"] = "stopping"
            background_job["message"] = "Đang dừng job nền..."
    return jsonify({"status": "stopped"})


@app.route("/start_background_scan", methods=["POST"])
def start_background_scan():
    apply_config_from_payload(request.json or {})

    with background_lock:
        if background_job["status"] in ("running", "stopping"):
            return jsonify({
                "status": "already_running",
                "job_id": background_job["id"],
                "message": "Đang có job nền chạy. Terminal sẽ nối lại job hiện tại."
            })

        config.STOP_SCAN = False
        background_job["id"] += 1
        background_job["status"] = "running"
        background_job["logs"] = []
        background_job["next_seq"] = 1
        background_job["progress"] = None
        background_job["message"] = "Job nền đang chạy."
        job_id = background_job["id"]

        worker = Thread(target=background_scan_worker, args=(job_id,), daemon=True)
        background_job["thread"] = worker
        worker.start()

    return jsonify({
        "status": "started",
        "job_id": job_id,
        "message": "Đã bắt đầu chạy nền."
    })


@app.route("/background_status")
def background_status():
    since = request.args.get("since", 0, type=int)
    with background_lock:
        logs = [entry for entry in background_job["logs"] if entry.get("seq", 0) > since]
        return jsonify({
            "job_id": background_job["id"],
            "status": background_job["status"],
            "message": background_job["message"],
            "progress": background_job["progress"],
            "logs": logs,
            "last_seq": background_job["next_seq"] - 1
        })

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
    app.run(host="127.0.0.1", port=5500, debug=True, use_reloader=False)
