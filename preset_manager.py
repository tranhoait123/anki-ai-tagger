from dataclasses import dataclass, field
from pathlib import Path
import re

import yaml


PRESETS_DIR = Path(__file__).resolve().parent / "presets"
VALID_KINDS = {"tagging", "filter", "duplicate_review"}
VALID_SCAN_MODES = {"sequential", "similar"}


class PresetError(ValueError):
    pass


@dataclass
class Preset:
    id: str
    name: str
    kind: str
    allowed_tags: list[str]
    default_tag: str = ""
    instructions: str = ""
    skip_tags: list[str] = field(default_factory=list)
    scan_mode: str = "sequential"
    batch_size: int = 500
    fields_to_read: list[str] = field(default_factory=list)
    built_in: bool = False

    def to_dict(self, include_prompt=False):
        data = {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "allowed_tags": self.allowed_tags,
            "default_tag": self.default_tag,
            "instructions": self.instructions,
            "skip_tags": self.skip_tags,
            "scan_mode": self.scan_mode,
            "batch_size": self.batch_size,
            "fields_to_read": self.fields_to_read,
            "built_in": self.built_in,
        }
        if include_prompt:
            data["prompt_preview"] = build_system_prompt(self)
        return data


def slugify_preset_id(raw_id):
    raw_id = (raw_id or "").strip()
    raw_id = re.sub(r"\s+", "_", raw_id)
    raw_id = re.sub(r"[^A-Za-z0-9_-]", "", raw_id)
    return raw_id[:80]


def _as_list(value, field_name):
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.splitlines() if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise PresetError(f"{field_name} phải là danh sách hoặc text nhiều dòng.")


def _preset_path(preset_id):
    safe_id = slugify_preset_id(preset_id)
    if not safe_id:
        raise PresetError("Preset id không hợp lệ.")
    return PRESETS_DIR / f"{safe_id}.yaml"


def _preset_from_data(data, fallback_id=""):
    if not isinstance(data, dict):
        raise PresetError("Preset YAML phải là object.")

    preset_id = slugify_preset_id(data.get("id") or fallback_id)
    name = str(data.get("name") or preset_id).strip()
    kind = str(data.get("kind") or "tagging").strip()
    scan_mode = str(data.get("scan_mode") or "sequential").strip()

    if not preset_id:
        raise PresetError("Preset thiếu id.")
    if not name:
        raise PresetError(f"Preset {preset_id} thiếu name.")
    if kind not in VALID_KINDS:
        raise PresetError(f"Preset {preset_id} có kind không hợp lệ: {kind}.")
    if scan_mode not in VALID_SCAN_MODES:
        raise PresetError(f"Preset {preset_id} có scan_mode không hợp lệ: {scan_mode}.")

    allowed_tags = _as_list(data.get("allowed_tags"), "allowed_tags")
    default_tag = str(data.get("default_tag") or "").strip()
    instructions = str(data.get("instructions") or "").strip()
    skip_tags = _as_list(data.get("skip_tags"), "skip_tags")
    fields_to_read = _as_list(data.get("fields_to_read"), "fields_to_read")

    try:
        batch_size = int(data.get("batch_size") or 500)
    except (TypeError, ValueError) as exc:
        raise PresetError(f"Preset {preset_id} có batch_size không hợp lệ.") from exc
    if batch_size <= 0:
        raise PresetError(f"Preset {preset_id} có batch_size phải lớn hơn 0.")

    if not allowed_tags:
        raise PresetError(f"Preset {preset_id} cần ít nhất một allowed_tags.")
    if not instructions:
        raise PresetError(f"Preset {preset_id} thiếu instructions.")
    if default_tag and default_tag not in allowed_tags:
        allowed_tags.append(default_tag)

    return Preset(
        id=preset_id,
        name=name,
        kind=kind,
        allowed_tags=list(dict.fromkeys(allowed_tags)),
        default_tag=default_tag,
        instructions=instructions,
        skip_tags=list(dict.fromkeys(skip_tags)),
        scan_mode=scan_mode,
        batch_size=batch_size,
        fields_to_read=list(dict.fromkeys(fields_to_read)),
        built_in=bool(data.get("built_in", False)),
    )


def load_preset(preset_id):
    path = _preset_path(preset_id)
    if not path.exists():
        raise PresetError(f"Không tìm thấy preset: {preset_id}.")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _preset_from_data(data, fallback_id=path.stem)


def list_presets():
    PRESETS_DIR.mkdir(exist_ok=True)
    presets = []
    for path in sorted(PRESETS_DIR.glob("*.yaml")):
        presets.append(load_preset(path.stem))
    return presets


def save_preset(payload, preset_id=None):
    data = dict(payload or {})
    if preset_id:
        data["id"] = preset_id
    preset = _preset_from_data(data, fallback_id=preset_id or "")
    path = _preset_path(preset.id)
    if path.exists():
        existing = load_preset(preset.id)
        if existing.built_in:
            raise PresetError("Preset mặc định không sửa trực tiếp được. Hãy duplicate rồi sửa bản mới.")
    PRESETS_DIR.mkdir(exist_ok=True)
    path.write_text(
        yaml.safe_dump(preset.to_dict(include_prompt=False), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return preset


def delete_preset(preset_id):
    preset = load_preset(preset_id)
    if preset.built_in:
        raise PresetError("Preset mặc định không thể xoá. Hãy duplicate rồi sửa bản mới.")
    _preset_path(preset.id).unlink()


def build_system_prompt(preset):
    tags_text = "\n".join(f"- {tag}" for tag in preset.allowed_tags)
    default_rule = (
        f"- Nếu không chắc chắn hoặc không đủ dữ kiện, trả về tag mặc định: `{preset.default_tag}`."
        if preset.default_tag else
        "- Nếu không chắc chắn, chỉ chọn tag an toàn nhất trong danh sách."
    )
    kind_rule = {
        "tagging": "Nhiệm vụ chính: phân loại nội dung thẻ vào đúng bộ tag được phép.",
        "filter": "Nhiệm vụ chính: lọc/đánh dấu thẻ theo tiêu chí trong hướng dẫn.",
        "duplicate_review": "Nhiệm vụ chính: review trùng/gần trùng; chỉ gắn tag review để người dùng kiểm tra thủ công.",
    }[preset.kind]

    return f"""{preset.instructions}

NGUỒN SỰ THẬT TỪ PRESET:
{kind_rule}

DANH SÁCH TAG ĐƯỢC PHÉP SỬ DỤNG:
{tags_text}

QUY TẮC CHUNG:
- Chỉ trả về tag có trong danh sách trên, không tự tạo tag mới.
{default_rule}
- Luôn trả về bản ghi cho mọi thẻ trong batch.
"""
