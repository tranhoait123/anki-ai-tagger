import time

import config
from anki_client import get_notes, get_notes_info, add_tags
from ai_analyzer import analyze_batch_clinical_text
from similar_selector import select_similar_cards


NOTES_INFO_BATCH_SIZE = 500
LOCAL_FILTER_LOG_EVERY = 5000


def _limit_reached(tagged_count):
    max_cards = getattr(config, "MAX_CARDS_PER_RUN", None)
    return max_cards is not None and tagged_count >= max_cards


def _parse_field_names(field_mode):
    if not field_mode or str(field_mode).strip().lower() == "all":
        return []
    return [part.strip() for part in str(field_mode).split(",") if part.strip()]


def _field_value(note, field_name):
    field_data = note.get("fields", {}).get(field_name)
    if not field_data:
        return ""
    return field_data.get("value", "").strip()


def _build_note_content(note, field_mode="all"):
    content_parts = []
    excluded = set(getattr(config, "FIELDS_TO_EXCLUDE", []))
    fields = note.get("fields", {})
    requested_fields = _parse_field_names(field_mode)

    if requested_fields:
        for field_name in requested_fields:
            if field_name in excluded:
                continue
            val = _field_value(note, field_name)
            if val and val not in ("<div><br></div>", "<br>"):
                content_parts.append(f"[{field_name}]: {val}")
        return "\n".join(content_parts)

    for field_name, field_data in fields.items():
        if field_name in excluded:
            continue

        val = field_data.get("value", "").strip()
        if val and val not in ("<div><br></div>", "<br>"):
            content_parts.append(f"[{field_name}]: {val}")

    return "\n".join(content_parts)


def _tag_matches_skip(existing_tag, skip_tag):
    return existing_tag == skip_tag or existing_tag.startswith(f"{skip_tag}::")


def _should_skip_processed(existing_tags, preset):
    skip_tags = preset.get("skip_tags", [])
    if skip_tags:
        return any(_tag_matches_skip(existing, skip) for existing in existing_tags for skip in skip_tags)

    if preset.get("kind") == "duplicate_review":
        return any(tag.startswith("AI_DUP_") for tag in existing_tags)
    if preset.get("kind") == "tagging":
        return any(tag.startswith("AI::") for tag in existing_tags)
    return any(tag in preset.get("allowed_tags", []) for tag in existing_tags)


def _prepare_card(note, preset):
    fields_to_read = preset.get("fields_to_read") or "all"
    content = _build_note_content(note, ", ".join(fields_to_read) if isinstance(fields_to_read, list) else fields_to_read)
    if len(content.strip()) < 10:
        return None

    existing_tags = note.get("tags", [])
    if _should_skip_processed(existing_tags, preset):
        return None

    field_mode = getattr(config, "SIMILAR_FIELD_MODE", "Ques, A, B, C, D") or "Ques, A, B, C, D"
    compare_text = _build_note_content(note, field_mode)
    if not compare_text:
        compare_text = content

    return {
        "note_id": note["noteId"],
        "existing_tags": existing_tags,
        "content": content,
        "compare_text": compare_text,
    }


def _combined_result_tags(res):
    result_tags = []
    for tag in getattr(res, "suggested_tags", []) or []:
        tag = tag.strip()
        if tag:
            result_tags.append(tag)
    for tag in getattr(res, "duplicate_review_tags", []) or []:
        tag = tag.strip()
        if tag:
            result_tags.append(tag)
    return list(dict.fromkeys(result_tags))


def _analyze_and_tag_batch(batch_buffer, tagged_count, duplicate_review_mode=False):
    yield {"type": "progress", "current": f"Đang gửi {len(batch_buffer)} thẻ lên AI", "total": "ai"}
    yield {"type": "info", "msg": f"Đang gửi {len(batch_buffer)} thẻ cho AI phân tích đồng loạt..."}
    batch_result = analyze_batch_clinical_text(
        batch_buffer,
        config.SYSTEM_PROMPT,
        duplicate_review_mode=duplicate_review_mode,
    )

    if batch_result and batch_result.results:
        for res in batch_result.results:
            new_tags = _combined_result_tags(res)

            if new_tags:
                add_result = add_tags([res.note_id], new_tags)
                if add_result is None or add_result is False:
                    yield {"type": "error", "msg": f"Không gắn được tags cho NoteID: {res.note_id}. AnkiConnect trả lỗi hoặc mất kết nối."}
                    continue

                tagged_count += 1
                tags_str = ", ".join(new_tags)
                yield {"type": "success", "msg": f"Đã gắn tags '{tags_str}' cho NoteID: {res.note_id}<br><b>Lập luận:</b> {res.reasoning} (Độ tin cậy: {res.confidence:.2f})"}

                if _limit_reached(tagged_count):
                    break
            else:
                yield {"type": "warning", "msg": f"Bỏ qua NoteID: {res.note_id}. Không có dữ kiện đủ đặc hiệu."}
    else:
        yield {"type": "error", "msg": "Lỗi phân tích Lô hoặc AI bị sập/chặn."}

    return tagged_count


def _note_info_batches(note_ids, batch_size=NOTES_INFO_BATCH_SIZE):
    for start in range(0, len(note_ids), batch_size):
        chunk = note_ids[start:start + batch_size]
        notes_info = get_notes_info(chunk) or []
        yield start, notes_info


def _preset_for_scan():
    preset = getattr(config, "CURRENT_PRESET", None) or {}
    return {
        "id": preset.get("id", getattr(config, "CURRENT_PRESET_ID", "")),
        "name": preset.get("name", getattr(config, "CURRENT_PRESET_ID", "Preset")),
        "kind": preset.get("kind", "tagging"),
        "allowed_tags": preset.get("allowed_tags", []),
        "skip_tags": preset.get("skip_tags", []),
        "scan_mode": preset.get("scan_mode", getattr(config, "CARD_SELECTION_MODE", "sequential")),
        "fields_to_read": preset.get("fields_to_read", []),
    }


def run_scan_generator():
    preset = _preset_for_scan()
    source_tag_msg = f" (Giới hạn trong Tag: {config.SOURCE_FILTER_TAG})" if getattr(config, "SOURCE_FILTER_TAG", "") else " (Toàn bộ Deck)"
    yield {"type": "info", "msg": f"Bắt đầu quét Deck: {config.TARGET_DECK}{source_tag_msg}"}
    yield {"type": "info", "msg": f"[*] Preset: <b>{preset['name']}</b> ({preset['kind']})"}

    if not hasattr(config, "GEMINI_API_KEYS") or not config.GEMINI_API_KEYS or config.GEMINI_API_KEYS[0] == "ĐIỀN_CÁC_API_KEY_CÁCH_NHAU_BỞI_DẤU_PHẨY":
        yield {"type": "error", "msg": "Lỗi Cấu Hình: Chưa điền API Key trong file config.py hoặc trên giao diện."}
        return
    if not getattr(config, "SYSTEM_PROMPT", "").strip():
        yield {"type": "error", "msg": "Preset chưa tạo được prompt. Hãy kiểm tra preset đang chọn."}
        return

    tag_filter = getattr(config, "SOURCE_FILTER_TAG", "")
    note_ids = get_notes(config.TARGET_DECK, tag_filter)

    if not note_ids:
        yield {"type": "error", "msg": "Không tìm thấy thẻ nào hoặc sai tên Deck / Anki chưa mở."}
        return

    yield {"type": "info", "msg": f"Đã tìm thấy {len(note_ids)} thẻ. Bắt đầu phân tích..."}

    tagged_count = 0
    total = len(note_ids)
    is_duplicate_mode = preset["kind"] == "duplicate_review"
    selection_mode = "similar" if is_duplicate_mode else (getattr(config, "CARD_SELECTION_MODE", "sequential") or "sequential")
    use_similar_selection = selection_mode == "similar"
    batch_size = max(1, int(getattr(config, "BATCH_SIZE", 500) or 500))

    if use_similar_selection:
        field_mode = getattr(config, "SIMILAR_FIELD_MODE", "Ques, A, B, C, D") or "Ques, A, B, C, D"
        seed_keyword = getattr(config, "SIMILAR_SEED_KEYWORD", "") or ""
        seed_msg = f"seed: <b>{seed_keyword}</b>" if seed_keyword.strip() else "tự tìm cụm gần nhau nhất"
        yield {"type": "info", "msg": f"[*] Cách chọn thẻ gửi AI: <b>Gần giống nhau local</b> ({seed_msg}, field: {field_mode}, batch: {batch_size})"}
    else:
        yield {"type": "info", "msg": f"[*] Cách chọn thẻ gửi AI: <b>Tuần tự trong Deck/Tag</b> (batch: {batch_size})"}

    batch_buffer = []
    similar_candidates = []

    yield {"type": "info", "msg": f"Bước 1/3: Đang tải và lọc thẻ theo lô {NOTES_INFO_BATCH_SIZE} notes/lần."}

    for batch_start, notes_info in _note_info_batches(note_ids):
        if not notes_info:
            yield {"type": "warning", "msg": f"Không tải được thông tin notes ở lô bắt đầu #{batch_start + 1}. Bỏ qua lô này."}
            continue

        for offset, note in enumerate(notes_info):
            idx = batch_start + offset

            if _limit_reached(tagged_count):
                yield {"type": "warning", "msg": f"Đã đạt giới hạn xử lý {config.MAX_CARDS_PER_RUN} thẻ. Dừng quét."}
                break

            yield {"type": "progress", "current": min(idx + 1, total), "total": total}

            if getattr(config, "STOP_SCAN", False):
                yield {"type": "warning", "msg": "ĐÃ DỪNG LẠI THEO YÊU CẦU CỦA BẠN."}
                break

            card = _prepare_card(note, preset)
            if not card:
                continue

            if use_similar_selection:
                similar_candidates.append(card)
                continue

            batch_buffer.append(card)

            if len(batch_buffer) >= batch_size:
                analyzer = _analyze_and_tag_batch(batch_buffer, tagged_count, duplicate_review_mode=is_duplicate_mode)
                while True:
                    try:
                        status = next(analyzer)
                        yield status
                    except StopIteration as stop:
                        tagged_count = stop.value if stop.value is not None else tagged_count
                        break

                batch_buffer = []
                time.sleep(1)

                if _limit_reached(tagged_count):
                    yield {"type": "warning", "msg": f"Đã đạt giới hạn xử lý {config.MAX_CARDS_PER_RUN} thẻ. Dừng quét."}
                    break

        if getattr(config, "STOP_SCAN", False) or _limit_reached(tagged_count):
            break

        processed = min(batch_start + len(notes_info), total)
        if use_similar_selection and (processed == total or processed % LOCAL_FILTER_LOG_EVERY == 0):
            yield {"type": "info", "msg": f"Bước 1/3: Đã lọc {len(similar_candidates)} thẻ hợp lệ sau {processed}/{total} notes."}

    if (
        not use_similar_selection
        and batch_buffer
        and not getattr(config, "STOP_SCAN", False)
        and not _limit_reached(tagged_count)
    ):
        analyzer = _analyze_and_tag_batch(batch_buffer, tagged_count, duplicate_review_mode=is_duplicate_mode)
        while True:
            try:
                status = next(analyzer)
                yield status
            except StopIteration as stop:
                tagged_count = stop.value if stop.value is not None else tagged_count
                break

            if _limit_reached(tagged_count):
                yield {"type": "warning", "msg": f"Đã đạt giới hạn xử lý {config.MAX_CARDS_PER_RUN} thẻ. Dừng quét."}

    if use_similar_selection and not getattr(config, "STOP_SCAN", False):
        yield {"type": "info", "msg": f"Bước 1/3 hoàn tất: Có {len(similar_candidates)} thẻ hợp lệ sau khi bỏ thẻ rỗng/đã xử lý."}

        if similar_candidates:
            try:
                yield {"type": "progress", "current": "Đang chọn cụm gần giống local", "total": "local"}
                yield {"type": "info", "msg": f"Bước 2/3: Đang chọn {batch_size} thẻ gần giống nhất từ {len(similar_candidates)} thẻ hợp lệ. Deck lớn có thể mất một chút."}
                selected_cards, selector_info = select_similar_cards(
                    similar_candidates,
                    batch_size,
                    getattr(config, "SIMILAR_SEED_KEYWORD", "") or "",
                )
                if len(selected_cards) < min(batch_size, len(similar_candidates)):
                    yield {"type": "warning", "msg": f"Chỉ chọn được {len(selected_cards)} thẻ gần giống để gửi AI."}

                if selector_info.get("mode") == "seed":
                    yield {"type": "info", "msg": f"Bước 2/3 hoàn tất: Đã chọn {len(selected_cards)} thẻ gần seed '<b>{selector_info.get('seed')}</b>' (điểm top: {selector_info.get('score', 0):.3f})."}
                else:
                    yield {"type": "info", "msg": f"Bước 2/3 hoàn tất: Đã chọn {len(selected_cards)} thẻ trong cụm gần giống nhất (center NoteID: {selector_info.get('center_note_id')}, density: {selector_info.get('score', 0):.2f}, đã thử {selector_info.get('centers_evaluated', '?')}/{selector_info.get('total_candidates', '?')} tâm cụm)."}
            except Exception as e:
                selected_cards = similar_candidates[:batch_size]
                yield {"type": "warning", "msg": f"Thuật toán chọn gần giống bị lỗi ({e}). Fallback sang {len(selected_cards)} thẻ hợp lệ đầu tiên."}

            if selected_cards:
                action_msg = "phân tích/gắn tag review" if is_duplicate_mode else "phân tích/gắn tag"
                yield {"type": "info", "msg": f"Bước 3/3: Gửi {len(selected_cards)} thẻ đã chọn lên AI để {action_msg}."}
                analyzer = _analyze_and_tag_batch(selected_cards, tagged_count, duplicate_review_mode=is_duplicate_mode)
                while True:
                    try:
                        status = next(analyzer)
                        yield status
                    except StopIteration as stop:
                        tagged_count = stop.value if stop.value is not None else tagged_count
                        break

    if getattr(config, "STOP_SCAN", False):
        final_msg = f"ĐÃ DỪNG! Đã gắn tag cho {tagged_count}/{len(note_ids)} thẻ trước khi dừng."
    elif _limit_reached(tagged_count):
        final_msg = f"HOÀN TẤT! Đã chạm giới hạn {config.MAX_CARDS_PER_RUN} thẻ và gắn tag cho {tagged_count}/{len(note_ids)} thẻ."
    elif tagged_count == 0:
        final_msg = f"HOÀN TẤT! Không có thẻ nào được gắn tag (0/{len(note_ids)})."
    else:
        final_msg = f"HOÀN TẤT! Đã gắn tag thành công cho {tagged_count}/{len(note_ids)} thẻ."

    yield {"type": "done", "msg": final_msg}
