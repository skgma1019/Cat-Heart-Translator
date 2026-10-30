"""Check CAT frame/label ZIP pairs in place and write a compact clip manifest.

Requires Python 3.12 standard library only. ZIP files are read, never extracted or
modified. Output is written to Downloads by default, outside the dataset tree.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
import json
from pathlib import Path
import re
import sys
from zipfile import BadZipFile, ZipFile

FRAME_RE = re.compile(r"frame_(\d+)_timestamp_(\d+)\.jpe?g$", re.I)
FIELDS = ["split", "code", "clip", "source_zip", "label_zip", "label_entry", "frame_count", "first_timestamp_ms", "last_timestamp_ms", "metadata_action", "file_video"]


def inspect_pair(root: Path, split: str, code: str, rows: list[dict], problems: Counter, examples: dict[str, list[str]], check_jpegs: int) -> None:
    folder = root / split / "CAT"
    source = folder / f"[원천]{code}.zip"
    label = folder / f"[라벨]{code}.zip"
    if not source.is_file() or not label.is_file():
        problems["missing_zip_pair"] += 1
        examples["missing_zip_pair"].append(f"{split}/{code}")
        return

    try:
        with ZipFile(source) as frames_zip, ZipFile(label) as labels_zip:
            clips: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
            sampled_jpegs = 0
            for entry in frames_zip.infolist():
                if entry.is_dir():
                    continue
                name = entry.filename.replace("\\", "/")
                if not name.lower().endswith((".jpg", ".jpeg")):
                    problems["unexpected_source_file"] += 1
                    if len(examples["unexpected_source_file"]) < 5:
                        examples["unexpected_source_file"].append(f"{split}/{code}: {name}")
                    continue
                if "/" not in name:
                    problems["unplaced_frame"] += 1
                    continue
                clip = name.rsplit("/", 1)[0]
                match = FRAME_RE.fullmatch(name.rsplit("/", 1)[-1])
                if match:
                    clips[clip].append((int(match[1]), int(match[2]), entry.filename))
                else:
                    problems["unrecognized_frame_name"] += 1
                    if len(examples["unrecognized_frame_name"]) < 5:
                        examples["unrecognized_frame_name"].append(f"{split}/{code}: {name}")
                if sampled_jpegs < check_jpegs:
                    with frames_zip.open(entry) as stream:
                        start = stream.read(3)
                    if start != b"\xff\xd8\xff":
                        problems["invalid_jpeg_header"] += 1
                        examples["invalid_jpeg_header"].append(f"{split}/{code}: {name}")
                    sampled_jpegs += 1

            labels = {n.replace("\\", "/")[:-5]: n for n in labels_zip.namelist() if n.lower().endswith(".json")}
            for clip in sorted(clips):
                frames = clips[clip]
                label_entry = labels.get(clip)
                if not label_entry:
                    problems["clip_without_label"] += 1
                    if len(examples["clip_without_label"]) < 5:
                        examples["clip_without_label"].append(f"{split}/{code}: {clip}")
                    continue
                try:
                    doc = json.loads(labels_zip.read(label_entry))
                    metadata = doc["metadata"]
                    if metadata.get("species") != "CAT":
                        problems["non_cat_species"] += 1
                        continue
                    action = metadata["action"]
                    file_video = doc.get("file_video", "")
                except (ValueError, TypeError, KeyError, UnicodeError) as exc:
                    problems["bad_label_json"] += 1
                    if len(examples["bad_label_json"]) < 5:
                        examples["bad_label_json"].append(f"{split}/{code}: {label_entry}: {exc}")
                    continue
                numbers = [f[0] for f in frames]
                if len(numbers) != len(set(numbers)):
                    problems["duplicate_frame_number"] += 1
                    if len(examples["duplicate_frame_number"]) < 5:
                        examples["duplicate_frame_number"].append(f"{split}/{code}: {clip}")
                timestamps = [f[1] for f in frames]
                rows.append({"split": split, "code": code, "clip": clip, "source_zip": str(source.relative_to(root)), "label_zip": str(label.relative_to(root)), "label_entry": label_entry, "frame_count": len(frames), "first_timestamp_ms": min(timestamps), "last_timestamp_ms": max(timestamps), "metadata_action": action, "file_video": file_video})
            for clip in labels.keys() - clips.keys():
                problems["label_without_clip"] += 1
                if len(examples["label_without_clip"]) < 5:
                    examples["label_without_clip"].append(f"{split}/{code}: {clip}")
    except (BadZipFile, OSError, RuntimeError) as exc:
        problems["zip_read_error"] += 1
        examples["zip_read_error"].append(f"{split}/{code}: {exc}")


def build(root: Path, output: Path, check_jpegs: int) -> dict:
    if not root.is_dir():
        raise FileNotFoundError(f"Dataset folder not found: {root}")
    rows: list[dict] = []
    problems: Counter = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    for split in ("Training", "Validation"):
        folder = root / split / "CAT"
        if not folder.is_dir():
            raise FileNotFoundError(f"CAT folder not found: {folder}")
        codes = sorted({p.stem[len("[라벨]"):] for p in folder.glob("*.zip") if p.name.startswith("[라벨]")})
        if len(codes) != 12:
            problems["unexpected_class_count"] += 1
            examples["unexpected_class_count"].append(f"{split}: {len(codes)} classes")
        for code in codes:
            before = len(rows)
            inspect_pair(root, split, code, rows, problems, examples, check_jpegs)
            print(f"{split}/{code}: {len(rows) - before} matched clips", flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    report = {"created_at": datetime.now().isoformat(timespec="seconds"), "dataset_root": str(root), "manifest": str(output), "clips": len(rows), "training_clips": sum(r["split"] == "Training" for r in rows), "validation_clips": sum(r["split"] == "Validation" for r in rows), "problems": dict(problems), "examples": dict(examples), "sampled_jpegs_per_archive": check_jpegs, "note": "Frame JPEG content is only header-sampled. Same-cat split overlap remains unknown; no training performed."}
    report_path = output.with_name(output.stem + "-report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Manifest: {output}\nReport: {report_path}\nClips: {len(rows)}; problems: {sum(problems.values())}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="Existing E: dataset folder; read only")
    parser.add_argument("--output", type=Path, default=Path.home() / "Downloads" / "cat-behavior-manifest.csv")
    parser.add_argument("--check-jpegs", type=int, default=1, help="JPEG headers to inspect per source ZIP (default: 1)")
    args = parser.parse_args()
    if args.check_jpegs < 0:
        parser.error("--check-jpegs must be nonnegative")
    report = build(args.root, args.output, args.check_jpegs)
    return 0 if report["clips"] == 24244 and not report["problems"] else 2


if __name__ == "__main__":
    sys.exit(main())
