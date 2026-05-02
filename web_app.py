import os
import json
import logging
import webbrowser
from threading import Lock, Thread, Timer
from flask import Flask, render_template, request, jsonify, Response
import config
from scanner import run_scan_generator
from anki_client import get_deck_names, get_tags
from preset_manager import (
    PresetError,
    build_system_prompt,
    delete_preset,
    list_presets,
    load_preset,
    save_preset,
)

# Tắt log mặc định của Flask cho gọn Terminal
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)

BACKGROUND_LOG_LIMIT = 500
background_lock = Lock()
scan_lock = Lock()
background_job = {
    "id": 0,
    "status": "idle",
    "logs": [],
    "next_seq": 1,
    "progress": None,
    "thread": None,
    "message": "Chưa có job nền nào đang chạy."
}


def _parse_positive_int(raw_value, field_label, allow_blank=False, default=None):
    raw_text = "" if raw_value is None else str(raw_value).strip()
    if raw_text == "":
        if allow_blank:
            return default
        if default is not None:
            return default
        raise ValueError(f"{field_label} không được để trống.")

    try:
        value = int(raw_text)
    except ValueError as exc:
        raise ValueError(f"{field_label} phải là số nguyên hợp lệ.") from exc

    if value <= 0:
        raise ValueError(f"{field_label} phải lớn hơn 0. Để trống nếu muốn chạy toàn bộ.")

    return value


def apply_config_from_payload(data):
    """Cập nhật config trên RAM từ dữ liệu form."""
    keys_str = data.get("api_keys", "")
    gemini_api_keys = getattr(config, 'GEMINI_API_KEYS', [])
    if keys_str:
        gemini_api_keys = [k.strip() for k in keys_str.split(",") if k.strip()]

    exclude_str = data.get("exclude", "")
    excluded_fields = [x.strip() for x in exclude_str.split(",") if x.strip()]

    preset_id = data.get("preset_id") or getattr(config, "CURRENT_PRESET_ID", "Nhi_khoa")
    preset = load_preset(preset_id)

    batch_size = data.get("batch_size")
    parsed_batch_size = _parse_positive_int(
        batch_size,
        "Batch Size",
        allow_blank=False,
        default=preset.batch_size or getattr(config, 'BATCH_SIZE', 500)
    )

    limit = data.get("limit")
    parsed_limit = _parse_positive_int(limit, "Giới Hạn Tổng", allow_blank=True, default=None)

    config.GEMINI_API_KEYS = gemini_api_keys
    config.CURRENT_KEY_INDEX = 0
    config.TARGET_DECK = data.get("deck", config.TARGET_DECK)
    config.SOURCE_FILTER_TAG = data.get("source_tag", "")
    config.CURRENT_MODEL = data.get("model", getattr(config, 'CURRENT_MODEL', 'gemini-3.1-flash-lite-preview'))
    config.FIELDS_TO_EXCLUDE = excluded_fields
    config.CURRENT_PRESET_ID = preset.id
    config.CURRENT_PRESET = preset.to_dict(include_prompt=False)
    config.SYSTEM_PROMPT_OVERRIDE = data.get("system_prompt_override", "") or ""
    config.SYSTEM_PROMPT = config.SYSTEM_PROMPT_OVERRIDE.strip() or build_system_prompt(preset)
    config.BATCH_SIZE = parsed_batch_size
    requested_scan_mode = data.get("card_selection_mode") or preset.scan_mode or "sequential"
    if preset.kind == "duplicate_review":
        requested_scan_mode = "similar"
    config.CARD_SELECTION_MODE = requested_scan_mode
    fields_for_compare = data.get("similar_field_mode") or ", ".join(preset.fields_to_read) or "Ques, A, B, C, D"
    config.SIMILAR_FIELD_MODE = fields_for_compare
    config.SIMILAR_SEED_KEYWORD = data.get("similar_seed_keyword", "") or ""
    config.MAX_CARDS_PER_RUN = parsed_limit


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


def background_scan_worker(job_id, lock_acquired=False):
    if not lock_acquired and not scan_lock.acquire(blocking=False):
        append_background_log({"type": "error", "msg": "Đang có lượt quét khác chạy. Job nền không được khởi động."})
        with background_lock:
            if background_job["id"] == job_id:
                background_job["status"] = "error"
                background_job["message"] = "Đang có lượt quét khác chạy."
        return

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
    finally:
        scan_lock.release()

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
        
    presets = [preset.to_dict(include_prompt=True) for preset in list_presets()]
    current_preset_id = getattr(config, "CURRENT_PRESET_ID", "Nhi_khoa")
    try:
        current_preset = load_preset(current_preset_id)
    except PresetError:
        current_preset = presets[0] if presets else None

    if current_preset and not getattr(config, "SYSTEM_PROMPT", ""):
        if hasattr(current_preset, "to_dict"):
            config.CURRENT_PRESET = current_preset.to_dict(include_prompt=False)
            config.SYSTEM_PROMPT = build_system_prompt(current_preset)

    return render_template(
        "index.html",
        api_keys=", ".join(getattr(config, 'GEMINI_API_KEYS', [])),
        deck=config.TARGET_DECK,
        source_tag=getattr(config, 'SOURCE_FILTER_TAG', ''),
        available_decks=available_decks,
        available_tags=available_tags,
        exclude=", ".join(getattr(config, 'FIELDS_TO_EXCLUDE', [])),
        system_prompt_override=getattr(config, 'SYSTEM_PROMPT_OVERRIDE', ''),
        presets=presets,
        current_preset_id=current_preset_id,
        available_models=getattr(config, 'AVAILABLE_MODELS', []),
        current_model=getattr(config, 'CURRENT_MODEL', 'gemini-3.1-flash-lite-preview'),
        max_cards=getattr(config, 'MAX_CARDS_PER_RUN', '') if getattr(config, 'MAX_CARDS_PER_RUN', None) is not None else '',
        batch_size=getattr(config, 'BATCH_SIZE', 500),
        card_selection_mode=getattr(config, 'CARD_SELECTION_MODE', 'sequential'),
        similar_field_mode=getattr(config, 'SIMILAR_FIELD_MODE', 'Ques, A, B, C, D'),
        similar_seed_keyword=getattr(config, 'SIMILAR_SEED_KEYWORD', '')
    )


@app.route("/api/presets")
def api_list_presets():
    return jsonify({
        "presets": [preset.to_dict(include_prompt=False) for preset in list_presets()]
    })


@app.route("/api/presets/<preset_id>")
def api_get_preset(preset_id):
    try:
        preset = load_preset(preset_id)
    except PresetError as e:
        return jsonify({"status": "error", "message": str(e)}), 404
    return jsonify(preset.to_dict(include_prompt=True))


@app.route("/api/presets", methods=["POST"])
def api_create_preset():
    try:
        preset = save_preset(request.json or {})
    except PresetError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    return jsonify({"status": "success", "preset": preset.to_dict(include_prompt=True)}), 201


@app.route("/api/presets/<preset_id>", methods=["PUT"])
def api_update_preset(preset_id):
    try:
        preset = save_preset(request.json or {}, preset_id=preset_id)
    except PresetError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    return jsonify({"status": "success", "preset": preset.to_dict(include_prompt=True)})


@app.route("/api/presets/<preset_id>", methods=["DELETE"])
def api_delete_preset(preset_id):
    try:
        delete_preset(preset_id)
    except PresetError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    return jsonify({"status": "success"})

@app.route("/save_config", methods=["POST"])
def save_config():
    if scan_lock.locked():
        return jsonify({
            "status": "busy",
            "message": "Đang có lượt quét chạy. Không đổi cấu hình giữa chừng."
        }), 409

    try:
        apply_config_from_payload(request.json or {})
    except (PresetError, ValueError) as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    return jsonify({"status": "success"})

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
    try:
        payload = request.json or {}
        apply_config_from_payload(payload)
    except (PresetError, ValueError) as e:
        return jsonify({"status": "error", "message": str(e)}), 400

    with background_lock:
        if background_job["status"] in ("running", "stopping"):
            return jsonify({
                "status": "already_running",
                "job_id": background_job["id"],
                "message": "Đang có job nền chạy. Terminal sẽ nối lại job hiện tại."
            })

        if scan_lock.locked():
            return jsonify({
                "status": "already_running",
                "job_id": background_job["id"],
                "message": "Đang có lượt quét khác chạy. Terminal sẽ nối lại job hiện tại."
            }), 409

        scan_lock.acquire()
        config.STOP_SCAN = False
        background_job["id"] += 1
        background_job["status"] = "running"
        background_job["logs"] = []
        background_job["next_seq"] = 1
        background_job["progress"] = None
        background_job["message"] = "Job nền đang chạy."
        job_id = background_job["id"]

        worker = Thread(target=background_scan_worker, args=(job_id, True), daemon=True)
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
    def generate():
        if not scan_lock.acquire(blocking=False):
            status_dict = {"type": "error", "msg": "Đang có lượt quét khác chạy. Vui lòng chờ lượt hiện tại kết thúc."}
            yield f"data: {json.dumps(status_dict)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'msg': 'Không khởi động lượt quét mới vì app đang bận.'})}\n\n"
            return

        config.STOP_SCAN = False
        try:
            for status_dict in run_scan_generator():
                yield f"data: {json.dumps(status_dict)}\n\n"
        finally:
            scan_lock.release()
            
    return Response(generate(), mimetype="text/event-stream")

def open_browser():
    webbrowser.open_new('http://127.0.0.1:5500/')

if __name__ == "__main__":
    print("🚀 Đang khởi động Anki AI Web UI...")
    # Tự động mở trình duyệt sau 1.5 giây
    Timer(1.5, open_browser).start()
    app.run(host="127.0.0.1", port=5500, debug=True, use_reloader=False)
