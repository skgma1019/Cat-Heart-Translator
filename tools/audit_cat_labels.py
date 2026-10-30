"""Read CAT label ZIPs in place; write a compact JSON audit outside the dataset.

Usage: py -3.12 tools/audit_cat_labels.py --root "E:\\...\\반려동물 구분을 위한 동물 영상"
Requires only the Python standard library. Does not extract or modify source ZIPs.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
import sys
from zipfile import BadZipFile, ZipFile

LABEL_PREFIX = "[라벨]"
ID_KEYS = {"animal_id", "cat_id", "subject_id", "individual_id", "pet_id", "original_video_id", "session_id", "shooting_id", "recording_id"}


def scalar_ids(value: object, prefix: str = "") -> dict[str, str]:
    found: dict[str, str] = {}
    if not isinstance(value, dict):
        return found
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else key
        normalized = key.lower().replace("-", "_")
        if (normalized in ID_KEYS or normalized.endswith("_id")) and isinstance(child, (str, int)):
            found[path] = str(child)
        elif isinstance(child, dict):
            found.update(scalar_ids(child, path))
    return found


def label_matches_video(label_name: str, file_video: str) -> bool:
    stem = label_name.removesuffix(".json")
    parts = file_video.replace("\\", "/").split("/")
    video = parts[-1]
    choices = {video, video.removesuffix(".mp4")}
    if len(parts) > 1:
        choices.add(f"{parts[-2]}_{video}")
    return stem in choices


def audit(root: Path) -> dict:
    if not root.is_dir():
        raise FileNotFoundError(f"Dataset folder not found: {root}")
    archives = sorted(p for p in root.rglob("*.zip") if p.name.startswith(LABEL_PREFIX) and p.parent.name.upper() == "CAT")
    if not archives:
        raise FileNotFoundError(f"No CAT label ZIP files found under: {root}")
    by_class: dict[str, dict] = {}
    split_video: dict[str, set[str]] = defaultdict(set)
    split_video_basename: dict[str, set[str]] = defaultdict(set)
    split_id_values: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    failures: list[dict] = []
    for archive in archives:
        split = archive.parent.parent.name
        code = archive.stem[len(LABEL_PREFIX):]
        key = f"{split}/{code}"
        action = Counter()
        inspect_action = Counter()
        species = Counter()
        metadata_keys = Counter()
        animal_keys = Counter()
        id_fields = Counter()
        count = 0
        action_disagreements = 0
        video_name_mismatches = 0
        annotation_count = 0
        first_example: dict | None = None
        try:
            with ZipFile(archive) as z:
                names = [n for n in z.namelist() if n.lower().endswith(".json")]
                if not names:
                    failures.append({"archive": str(archive), "error": "No JSON entries"})
                for name in names:
                    try:
                        document = json.loads(z.read(name))
                        meta = document.get("metadata", {})
                        if not isinstance(meta, dict):
                            raise ValueError("metadata is not an object")
                        count += 1
                        action[str(meta.get("action"))] += 1
                        species[str(meta.get("species"))] += 1
                        metadata_keys.update(meta.keys())
                        animal = meta.get("animal", {})
                        if isinstance(animal, dict):
                            animal_keys.update(animal.keys())
                        inspected = meta.get("inspect", {})
                        inspected_action = inspected.get("action") if isinstance(inspected, dict) else None
                        inspect_action[str(inspected_action)] += 1
                        if meta.get("action") != inspected_action:
                            action_disagreements += 1
                        video = str(document.get("file_video", ""))
                        if not label_matches_video(Path(name).name, video):
                            video_name_mismatches += 1
                        normalized_video = video.replace("\\", "/")
                        split_video[split].add(normalized_video)
                        split_video_basename[split].add(normalized_video.rsplit("/", 1)[-1])
                        annotations = document.get("annotations", [])
                        if isinstance(annotations, list):
                            annotation_count += len(annotations)
                        ids = scalar_ids({k: v for k, v in document.items() if k != "annotations"})
                        id_fields.update(ids.keys())
                        for path, value in ids.items():
                            split_id_values[path][split].add(value)
                        if first_example is None:
                            first_example = {"entry": name, "file_video": video, "action": meta.get("action"), "species": meta.get("species"), "metadata_keys": sorted(meta), "animal_keys": sorted(animal) if isinstance(animal, dict) else []}
                    except (ValueError, TypeError, KeyError) as exc:
                        failures.append({"archive": str(archive), "entry": name, "error": str(exc)[:200]})
        except (BadZipFile, OSError) as exc:
            failures.append({"archive": str(archive), "error": str(exc)[:200]})
        by_class[key] = {"split": split, "code": code, "json_count": count, "metadata_action": dict(action), "inspect_action": dict(inspect_action), "species": dict(species), "action_disagreements": action_disagreements, "video_name_mismatches": video_name_mismatches, "annotation_count": annotation_count, "metadata_keys": sorted(metadata_keys), "animal_keys": sorted(animal_keys), "explicit_id_field_counts": dict(id_fields), "example": first_example}
        print(f"{key}: {count} JSON checked", flush=True)
    train = split_video.get("Training", set())
    valid = split_video.get("Validation", set())
    train_base = split_video_basename.get("Training", set())
    valid_base = split_video_basename.get("Validation", set())
    id_overlap = {path: {"training_values": len(values.get("Training", set())), "validation_values": len(values.get("Validation", set())), "overlap": len(values.get("Training", set()) & values.get("Validation", set()))} for path, values in split_id_values.items()}
    return {"dataset_root": str(root), "created_at": datetime.now().isoformat(timespec="seconds"), "cat_label_zip_count": len(archives), "classes": by_class, "file_video_exact_overlap": len(train & valid), "file_video_basename_overlap": len(train_base & valid_base), "expected_cat_label_zip_count": 24, "complete_archive_set": len(archives) == 24, "explicit_id_overlap": id_overlap, "failures_count": len(failures), "failures_sample": failures[:30], "warning": "No explicit individual ID means same-cat leakage cannot be ruled out. No model training was performed."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="Existing dataset folder on E:; read only")
    parser.add_argument("--output", type=Path, default=Path.home() / "Downloads" / "cat-behavior-label-audit.json")
    args = parser.parse_args()
    result = audit(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Audit saved to: {args.output}")
    print(f"CAT label archives: {result['cat_label_zip_count']}; failures: {result['failures_count']}")
    return 0 if result["failures_count"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
