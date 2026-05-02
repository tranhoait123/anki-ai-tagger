import html
import re
import string
import unicodedata
from collections import Counter, defaultdict

MAX_COMPARE_CHARS = 4000
MAX_TOKENS = 500
MAX_TOKEN_FEATURES = 160
MAX_WORD_SHINGLES = 220
MAX_CHAR_SHINGLES = 260
MAX_DENSE_CENTERS = 1800


def normalize_text(text):
    """Normalize Anki HTML/text into a compact comparison string."""
    if not text:
        return ""

    text = str(text)[:MAX_COMPARE_CHARS]
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    text = text.lower()
    text = text.translate(str.maketrans({ch: " " for ch in string.punctuation}))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize(text):
    return [tok for tok in re.findall(r"\w+", normalize_text(text), flags=re.UNICODE) if len(tok) > 1][:MAX_TOKENS]


def _word_shingles(tokens, size=2):
    if len(tokens) < size:
        return set(tokens)
    shingles = []
    for i in range(len(tokens) - size + 1):
        shingles.append(" ".join(tokens[i:i + size]))
        if len(shingles) >= MAX_WORD_SHINGLES:
            break
    return set(shingles)


def _char_shingles(text, size=4):
    compact = re.sub(r"\s+", "", normalize_text(text))
    if len(compact) < size:
        return {compact} if compact else set()
    shingles = []
    for i in range(len(compact) - size + 1):
        shingles.append(compact[i:i + size])
        if len(shingles) >= MAX_CHAR_SHINGLES:
            break
    return set(shingles)


def _features(text):
    tokens = tokenize(text)
    token_counts = Counter(tokens)

    weighted = Counter()
    for token, count in token_counts.most_common(MAX_TOKEN_FEATURES):
        weighted[f"t:{token}"] += min(count, 3) * 3
    for shingle in _word_shingles(tokens):
        weighted[f"w:{shingle}"] += 2
    for shingle in _char_shingles(text):
        weighted[f"c:{shingle}"] += 1

    return weighted


def _weighted_jaccard(left, right):
    if not left or not right:
        return 0.0

    shared = set(left) & set(right)
    union = set(left) | set(right)
    numerator = sum(min(left[key], right[key]) for key in shared)
    denominator = sum(max(left.get(key, 0), right.get(key, 0)) for key in union)
    return numerator / denominator if denominator else 0.0


def _candidate_features(cards):
    enriched = []
    for pos, card in enumerate(cards):
        text = card.get("compare_text") or card.get("content") or ""
        features = _features(text)
        enriched.append({
            "pos": pos,
            "card": card,
            "features": features,
            "feature_count": sum(features.values()),
        })
    return enriched


def select_similar_cards(cards, limit, seed_keyword=""):
    """
    Pick a local semantic-ish batch without external APIs.

    If seed_keyword exists, rank all cards by similarity to the seed.
    Otherwise, find the densest local neighborhood using an inverted index,
    then return the cards closest to that center.
    """
    if not cards:
        return [], {"mode": "empty", "center_note_id": None, "score": 0.0}

    safe_limit = max(1, int(limit or len(cards)))
    enriched = _candidate_features(cards)

    if seed_keyword and seed_keyword.strip():
        seed_features = _features(seed_keyword)
        ranked = sorted(
            enriched,
            key=lambda item: _weighted_jaccard(seed_features, item["features"]),
            reverse=True,
        )
        selected = [item["card"] for item in ranked[:safe_limit]]
        top_score = _weighted_jaccard(seed_features, ranked[0]["features"]) if ranked else 0.0
        return selected, {
            "mode": "seed",
            "center_note_id": None,
            "score": top_score,
            "seed": seed_keyword.strip(),
        }

    postings = defaultdict(list)
    for item in enriched:
        for feature, weight in item["features"].items():
            postings[feature].append((item["pos"], weight))

    best_center = enriched[0]
    best_density = -1.0
    max_posting = max(80, min(500, len(enriched) // 2 or 80))

    if len(enriched) <= MAX_DENSE_CENTERS:
        center_candidates = enriched
    else:
        step = max(1, len(enriched) // MAX_DENSE_CENTERS)
        center_candidates = enriched[::step][:MAX_DENSE_CENTERS]

    for item in center_candidates:
        votes = Counter()
        for feature, weight in item["features"].items():
            matches = postings.get(feature, [])
            if len(matches) > max_posting:
                continue
            for other_pos, other_weight in matches:
                if other_pos == item["pos"]:
                    continue
                votes[other_pos] += min(weight, other_weight)

        if not votes:
            density = 0.0
        else:
            nearest = votes.most_common(min(safe_limit, len(votes)))
            density = sum(score for _, score in nearest) / max(1, len(nearest))

        if density > best_density:
            best_density = density
            best_center = item

    ranked = sorted(
        enriched,
        key=lambda item: _weighted_jaccard(best_center["features"], item["features"]),
        reverse=True,
    )
    selected = [item["card"] for item in ranked[:safe_limit]]
    return selected, {
        "mode": "dense",
        "center_note_id": best_center["card"].get("note_id"),
        "score": best_density,
        "centers_evaluated": len(center_candidates),
        "total_candidates": len(enriched),
    }
