#!/usr/bin/env python3
"""
🧹 Anki Duplicate Resolver — CLI Edition
Chạy nền bằng Python, không cần trình duyệt.
Kết nối trực tiếp AnkiConnect (port 8765).

Sử dụng:
  python deduplicate.py                        # Tìm theo tag "duplicate"
  python deduplicate.py --tag marked           # Tìm theo tag khác
  python deduplicate.py --scan-all             # Quét toàn bộ collection
  python deduplicate.py --field Ques --fuzzy    # Quét fuzzy dùng trường Ques
  python deduplicate.py --fuzzy --suspend      # Tìm trùng và Tạm dừng (An toàn nhất)
  python deduplicate.py --fuzzy --tag-review   # Chỉ gắn tag DUPE_REVIEW để xem lại
  python deduplicate.py --dry-run              # Chỉ báo cáo, KHÔNG xoá gì
"""

import argparse
import json
import sys
import time
import re
import requests
import unicodedata
import string
from collections import defaultdict

# ─── AnkiConnect ─────────────────────────────────────────────
ANKI_URL = "http://127.0.0.1:8765"

def anki_invoke(action, **params):
    """Giao tiếp với AnkiConnect."""
    payload = {"action": action, "version": 6, "params": params}
    try:
        resp = requests.post(ANKI_URL, json=payload, timeout=30)
        data = resp.json()
        if data.get("error"):
            raise Exception(data["error"])
        return data.get("result")
    except requests.exceptions.ConnectionError:
        print("\n❌ Không thể kết nối AnkiConnect!")
        print("   ➤ Hãy mở Anki và bật addon AnkiConnect (port 8765).")
        sys.exit(1)

# ─── HTML stripper ───────────────────────────────────────────
def strip_html(html):
    """Xoá các thẻ HTML, chuẩn hoá Unicode và xoá dấu câu để so sánh."""
    if not html:
        return ""
    # Xoá HTML
    text = re.sub(r'<[^>]+>', '', html)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    
    # Chuẩn hoá Unicode (NFKC giúp xử lý tiếng Việt có dấu tốt hơn)
    text = unicodedata.normalize('NFKC', text)
    
    # Chuyển về chữ thường và xoá khoảng trắng thừa
    text = text.lower().strip()
    
    # Xoá dấu câu cơ bản để so sánh chính xác hơn
    text = text.translate(str.maketrans('', '', string.punctuation))
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# ─── Levenshtein / Fuzzy ────────────────────────────────────
def levenshtein(a, b):
    """Tính khoảng cách Levenshtein."""
    if a == b:
        return 0
    # Giới hạn 200 ký tự để tránh chậm
    a = a[:200]
    b = b[:200]
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(la + 1))
    for i in range(1, lb + 1):
        curr = [i] + [0] * la
        for j in range(1, la + 1):
            cost = 0 if b[i-1] == a[j-1] else 1
            curr[j] = min(curr[j-1] + 1, prev[j] + 1, prev[j-1] + cost)
        prev = curr
    return prev[la]

def get_shingles(text, k=3):
    """Chia văn bản thành các tập hợp k-grams để so sánh nhanh."""
    if len(text) < k:
        return {text}
    return {text[i:i+k] for i in range(len(text) - k + 1)}

def jaccard_similarity(set1, set2):
    """Tính độ tương đồng Jaccard dựa trên tập hợp shingles."""
    if not set1 or not set2:
        return 0.0
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union

def similarity(a, b):
    """Tính độ tương đồng Levenshtein (chỉ khi Jaccard Pass)."""
    if a == b:
        return 1.0
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 1.0
    return 1.0 - (levenshtein(a, b) / max_len)

# ─── Scoring (giống web UI) ─────────────────────────────────
def ai_score(stats):
    """
    Score = reps × 3 + interval × 2 − lapses + ease / 10
    Thẻ có score cao hơn sẽ được giữ lại.
    """
    reps = stats.get("reps", 0)
    interval = stats.get("interval", 0)
    lapses_val = stats.get("lapses", 0)
    ease = stats.get("ease", 0)
    
    if reps == 0 and interval == 0:
        return None  # Thẻ mới, chấm theo nội dung
    
    return reps * 3 + interval * 2 - lapses_val + ease / 10

# ─── Main Logic ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="🧹 Anki Duplicate Resolver — CLI Edition",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ:
  python deduplicate.py                        → Tìm thẻ có tag "duplicate"
  python deduplicate.py --scan-all             → Quét toàn bộ collection  
  python deduplicate.py --scan-all --dry-run   → Xem trước, không xoá
  python deduplicate.py --field Question       → So sánh theo field "Question"
  python deduplicate.py --fuzzy                → Bật fuzzy matching 90%
        """
    )
    parser.add_argument("--tag", help="Tag để tìm thẻ trùng (nếu không dùng --scan-all)")
    parser.add_argument("--scan-all", action="store_true", default=True, help="Quét toàn bộ collection (Mặc định)")
    parser.add_argument("--field", default="Front", help="Field dùng để so sánh trùng (mặc định: Front)")
    parser.add_argument("--fuzzy", action="store_true", help="Bật fuzzy matching (≥90%% giống nhau)")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ báo cáo, KHÔNG xoá thẻ nào")
    parser.add_argument("--suspend", action="store_true", help="Tạm dừng (Suspend) thẻ thay vì xoá vĩnh viễn")
    parser.add_argument("--tag-review", action="store_true", help="Chỉ gắn tag DUPE_REVIEW mà không xoá/suspend")
    parser.add_argument("--batch-size", type=int, default=1000, help="Kích thước batch khi tải notes (mặc định: 1000)")
    args = parser.parse_args()

    print("=" * 60)
    print("🧹 ANKI DUPLICATE RESOLVER — CLI Edition")
    print("=" * 60)
    
    if args.dry_run:
        print("⚠️  CHẾ ĐỘ DRY-RUN: Chỉ báo cáo, KHÔNG xoá thẻ nào.\n")
    
    # 1. Kiểm tra kết nối AnkiConnect
    print("🔗 Đang kết nối AnkiConnect...")
    version = anki_invoke("version")
    print(f"   ✅ Đã kết nối (AnkiConnect v{version})\n")

    # 2. Tìm notes
    if args.scan_all:
        print(f"📦 Đang tìm toàn bộ thẻ trong collection...")
        note_ids = anki_invoke("findNotes", query="deck:*") or []
    else:
        print(f'🏷  Đang tìm thẻ có tag: "{args.tag}"...')
        note_ids = anki_invoke("findNotes", query=f"tag:{args.tag}") or []
    
    if not note_ids:
        print("❌ Không tìm thấy thẻ nào!")
        if not args.scan_all:
            print(f'   Thử: python deduplicate.py --scan-all')
        sys.exit(0)
    
    print(f"   📋 Tìm thấy {len(note_ids)} thẻ.\n")

    # 3. Tải thông tin notes (batch)
    print("📥 Đang tải thông tin thẻ...")
    all_notes = []
    batches = [note_ids[i:i+args.batch_size] for i in range(0, len(note_ids), args.batch_size)]
    for i, batch in enumerate(batches):
        notes_info = anki_invoke("notesInfo", notes=batch) or []
        all_notes.extend(notes_info)
        pct = int((i + 1) / len(batches) * 100)
        print(f"   [{pct:3d}%] Batch {i+1}/{len(batches)} — {len(all_notes)} thẻ", end="\r")
    print(f"   ✅ Đã tải {len(all_notes)} thẻ.                    \n")

    # 4. Nhóm theo field
    compare_field = args.field
    print(f"🔍 Đang nhóm thẻ trùng theo: \"{compare_field}\"...")
    
    exact_groups = defaultdict(list)
    no_field_count = 0
    
    # Danh sách các trường cần gộp
    field_list = [f.strip() for f in compare_field.split(",") if f.strip()]
    
    for note in all_notes:
        fields = note.get("fields", {})
        
        # Gộp nội dung các trường
        combined_text = ""
        found_any = False
        
        for f_name in field_list:
            val = fields.get(f_name, {}).get("value", "")
            if val:
                combined_text += " " + val
                found_any = True
        
        # Nếu không tìm thấy trường nào trong danh sách, dùng fallback
        if not found_any:
            fallbacks = ["Ques", "Question", "Front", "front", "Text"]
            for f_name in fallbacks:
                val = fields.get(f_name, {}).get("value", "")
                if val:
                    combined_text = val
                    found_any = True
                    break
        
        key = strip_html(combined_text).strip().lower()
        if not key:
            no_field_count += 1
            continue
        exact_groups[key].append(note)
    
    if no_field_count > 0:
        print(f"   ⚠ {no_field_count} thẻ không có dữ liệu trong field \"{compare_field}\" → bỏ qua.")

    # 5. Fuzzy matching (if enabled)
    if args.fuzzy:
        print(f"🧠 Đang chạy Expert Fuzzy Matching (Scale: 92k+)...")
        # Semantic safety words (Expert medical set)
        critical_words = {
            'không', 'chưa', 'trừ', 'ngoại trừ', 'ngoại lệ', 'chỉ', 'luôn', 
            'tất cả', 'không bao giờ', 'ít nhất', 'duy nhất', 'ngoài'
        }
        
        def has_semantic_diff(s1, s2):
            w1 = set(s1.lower().split())
            w2 = set(s2.lower().split())
            for w in critical_words:
                if (w in w1) != (w in w2):
                    return True
            return False
        
        # Sắp xếp theo độ dài để tối ưu vòng lặp (O(N^2) -> O(N*window))
        unique_keys = sorted(list(exact_groups.keys()), key=len)
        # Pre-calculating shingles for all unique keys to speed up inner loop
        key_shingles = {k: get_shingles(k) for k in unique_keys}
        
        used = set()
        fuzzy_groups = {}
        total_keys = len(unique_keys)
        
        for i in range(total_keys):
            if i in used:
                continue
            k1 = unique_keys[i]
            cluster = list(exact_groups[k1])
            used.add(i)
            s1 = key_shingles[k1]
            
            # Chỉ so sánh với các thẻ có độ dài tương đương
            max_diff = max(4, int(len(k1) * 0.15))
            
            for j in range(i + 1, total_keys):
                if j in used:
                    continue
                k2 = unique_keys[j]
                
                # Cửa sổ độ dài
                if len(k2) - len(k1) > max_diff:
                    break
                
                # Pre-filter: Jaccard similarity (Fast)
                s2 = key_shingles[k2]
                if jaccard_similarity(s1, s2) < 0.7:
                    continue
                    
                # Phép so sánh đắt đỏ nhất: Levenshtein
                sim = similarity(k1, k2)
                if sim >= 0.90:
                    if has_semantic_diff(k1, k2):
                        continue
                    cluster.extend(exact_groups[k2])
                    used.add(j)
            
            if len(cluster) >= 2:
                fuzzy_groups[k1] = cluster
            
            if i % 100 == 0 or i == total_keys - 1:
                pct = int((i + 1) / total_keys * 100)
                sys.stdout.write(f"\r   [{pct:3d}%] Đang quét {i+1}/{total_keys} keys (Found {len(fuzzy_groups)} unique groups)...")
                sys.stdout.flush()
        
        groups = list(fuzzy_groups.items())
        print(f"\n   ✅ Expert fuzzy matching hoàn thành.                    ")
    else:
        groups = [(k, v) for k, v in exact_groups.items() if len(v) >= 2]
    
    # Sort by group size descending
    groups.sort(key=lambda x: len(x[1]), reverse=True)
    
    total_dupes_notes = sum(len(v) for _, v in groups)
    print(f"\n{'='*60}")
    print(f"📊 KẾT QUẢ TÌM KIẾM:")
    print(f"   • {len(groups)} nhóm trùng lặp")
    print(f"   • {total_dupes_notes} thẻ tổng cộng trong các nhóm")
    print(f"   • ~{total_dupes_notes - len(groups)} thẻ sẽ bị xoá")
    print(f"{'='*60}\n")
    
    if len(groups) == 0:
        print("🎉 Không tìm thấy thẻ trùng lặp! Collection đã sạch.")
        sys.exit(0)
    
    # 6. Tải card stats cho các thẻ trùng
    print("📊 Đang tải stats (reps, interval, lapses, ease)...")
    dupe_notes = [n for _, notes in groups for n in notes]
    all_card_ids = [cid for n in dupe_notes for cid in (n.get("cards", []))]
    
    stats_cache = {}
    if all_card_ids:
        card_batches = [all_card_ids[i:i+args.batch_size] for i in range(0, len(all_card_ids), args.batch_size)]
        all_cards_info = []
        for i, batch in enumerate(card_batches):
            cards = anki_invoke("cardsInfo", cards=batch) or []
            all_cards_info.extend(cards)
            pct = int((i + 1) / len(card_batches) * 100)
            print(f"   [{pct:3d}%] Card batch {i+1}/{len(card_batches)}", end="\r")
        
        card_map = {}
        for ci in all_cards_info:
            key = ci.get("cardId") or ci.get("id")
            if key is not None:
                card_map[key] = ci
        
        for note in dupe_notes:
            max_reps = 0
            max_int = 0
            total_lapses = 0
            sum_ease = 0
            cnt = 0
            for cid in note.get("cards", []):
                ci = card_map.get(cid)
                if not ci:
                    continue
                max_reps = max(max_reps, ci.get("reps", 0))
                max_int = max(max_int, ci.get("interval", 0))
                total_lapses += ci.get("lapses", 0)
                sum_ease += ci.get("factor", 0)
                cnt += 1
            stats_cache[note["noteId"]] = {
                "reps": max_reps,
                "interval": max_int,
                "lapses": total_lapses,
                "ease": round(sum_ease / cnt / 10) if cnt > 0 else 0,
            }
    
    print(f"   ✅ Đã tải stats cho {len(stats_cache)} notes.          \n")

    # 7. Xác nhận trước khi xoá
    if not args.dry_run:
        print("⚠️  CẢNH BÁO: Thao tác này sẽ XOÁ VĨNH VIỄN các thẻ trùng!")
        print("   Thẻ có điểm score cao hơn sẽ được giữ lại.")
        print("   Tags từ thẻ bị xoá sẽ được gộp vào thẻ giữ lại.\n")
        confirm = input("   Bạn có muốn tiếp tục? (y/N): ").strip().lower()
        if confirm not in ("y", "yes"):
            print("\n🛑 Đã huỷ. Không xoá thẻ nào.")
            sys.exit(0)
        print()

    # 8. Xử lý từng nhóm
    kept_count = 0
    deleted_count = 0
    errors = 0
    active_tag = None if args.scan_all else args.tag
    
    print("🚀 Bắt đầu xử lý...\n")
    
    for i, (front_key, notes) in enumerate(groups):
        preview = front_key[:60] + ("…" if len(front_key) > 60 else "")
        
        # Score tất cả notes trong nhóm
        scored = []
        for n in notes:
            s = stats_cache.get(n["noteId"], {})
            score = ai_score(s)
            back_len = len(strip_html(n.get("fields", {}).get("Back", {}).get("value", "")))
            scored.append({
                "note": n,
                "score": score,
                "is_new": score is None,
                "back_len": back_len,
                "stats": s,
            })
        
        # Sort: reviewed > new, higher score > lower score, longer back > shorter
        scored.sort(key=lambda x: (
            not x["is_new"],       # reviewed first (True=1 > False=0)
            x["score"] or 0,      # higher score
            x["back_len"],         # longer content
        ), reverse=True)
        
        keep = scored[0]
        delete_list = scored[1:]
        
        keep_note = keep["note"]
        delete_notes_list = [d["note"] for d in delete_list]
        delete_ids = [d["note"]["noteId"] for d in delete_list]
        
        # Score info
        if keep["is_new"]:
            score_info = f"📝 nội dung ({keep['back_len']} ký tự)"
        else:
            score_info = f"⭐ score={keep['score']:.0f} (reps:{keep['stats'].get('reps',0)} int:{keep['stats'].get('interval',0)})"
        
        if args.dry_run:
            # Chỉ báo cáo
            print(f"  [{i+1:4d}/{len(groups)}] \"{preview}\"")
            print(f"           → GIỮ #{keep_note['noteId']} ({score_info})")
            print(f"           → XOÁ {len(delete_ids)} thẻ (Dry Run)")
        elif args.tag_review:
            # Chỉ gắn tag để reviewer xem lại
            try:
                tag_name = "DUPE_REVIEW"
                anki_invoke("addTags", notes=[keep_note["noteId"]] + delete_ids, tags=tag_name)
                print(f"  🏷  [{i+1:4d}/{len(groups)}] Đã gắn tag {tag_name} cho {len(delete_ids)+1} thẻ.")
                kept_count += 1
            except Exception as e:
                errors += 1
                print(f"  ❌ [{i+1:4d}/{len(groups)}] Lỗi gắn tag: {e}")
        else:
            try:
                # Tag Merging: gộp tags từ thẻ bị xoá vào thẻ giữ lại
                all_delete_tags = set()
                for dn in delete_notes_list:
                    for t in dn.get("tags", []):
                        all_delete_tags.add(t)
                keep_tags = set(keep_note.get("tags", []))
                new_tags = [t for t in all_delete_tags if t not in keep_tags and t != active_tag]
                
                if new_tags:
                    anki_invoke("addTags", notes=[keep_note["noteId"]], tags=" ".join(new_tags))
                
                # Xử lý xoá hoặc suspend
                if delete_ids:
                    if args.suspend:
                        # Suspend các card thuộc note
                        all_cids = [cid for dn in delete_notes_list for cid in dn.get("cards", [])]
                        if all_cids:
                            anki_invoke("suspend", cards=all_cids)
                        # Gắn tag để biết là thẻ trùng đã suspend
                        anki_invoke("addTags", notes=delete_ids, tags="DUPE_SUSPENDED")
                        action_msg = f"đã suspend {len(delete_ids)} thẻ"
                    else:
                        anki_invoke("deleteNotes", notes=delete_ids)
                        action_msg = f"đã xoá {len(delete_ids)} thẻ"
                
                # Xoá tag tìm kiếm khỏi thẻ giữ lại
                if active_tag:
                    anki_invoke("removeTags", notes=[keep_note["noteId"]], tags=active_tag)
                
                kept_count += 1
                deleted_count += len(delete_ids)
                merge_info = f" · +{len(new_tags)} tags" if new_tags else ""
                
                print(f"  ✅ [{i+1:4d}/{len(groups)}] Giữ #{keep_note['noteId']} · {action_msg} · {score_info}{merge_info}")
                
            except Exception as e:
                errors += 1
                print(f"  ❌ [{i+1:4d}/{len(groups)}] Lỗi: {e}")
        
        # Nhường CPU 1 chút nếu xoá thật
        if not args.dry_run and (i + 1) % 50 == 0:
            time.sleep(0.1)
    
    # 9. Tổng kết
    print(f"\n{'='*60}")
    print(f"🏁 KẾT QUẢ:")
    if args.dry_run:
        print(f"   📋 DRY-RUN: {len(groups)} nhóm trùng lặp")
        print(f"   📋 Sẽ giữ {len(groups)} thẻ, xoá ~{total_dupes_notes - len(groups)} thẻ")
        print(f"\n   ➤ Để xoá thật, chạy lại KHÔNG có --dry-run")
    else:
        print(f"   ✅ Đã giữ: {kept_count} thẻ")
        print(f"   🗑  Đã xoá: {deleted_count} thẻ")
        if errors:
            print(f"   ❌ Lỗi: {errors}")
        print(f"\n   🎉 Hoàn tất! Collection đã được dọn dẹp.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
