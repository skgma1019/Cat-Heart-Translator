"""Make a compact contact sheet of v2 CAT validation errors; no retraining.

Uses the v2 checkpoint and validation feature cache. Reads a few source JPGs
from ZIPs in place and writes CSV, PNG, JSON under Downloads/cat-behavior-v2.
Model scores are uncalibrated and are not probabilities.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from io import BytesIO
import json
from pathlib import Path
import sys
from zipfile import ZipFile

from train_cat_behavior_pilot import evenly_spaced, select_rows


def load_features(rows, cache_dir, torch):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["source_zip"]].append(row)
    by_clip = {}
    for relative_zip, group in grouped.items():
        cache_path = cache_dir / f"Validation-{Path(relative_zip).stem}.pt"
        if not cache_path.is_file():
            raise FileNotFoundError(f"Validation feature cache missing: {cache_path}")
        cached = torch.load(cache_path, map_location="cpu", weights_only=True)
        clips = [row["clip"] for row in group]
        if cached["key"]["clips"] != clips:
            raise ValueError(f"Feature cache selection differs: {cache_path}")
        by_clip.update(zip(clips, cached["features"]))
    return torch.stack([by_clip[row["clip"]] for row in rows])


def choose_errors(rows, codes, logits, per_class, torch):
    predictions = logits.argmax(1).tolist()
    scores = torch.softmax(logits, dim=1).max(1).values.tolist()
    wrong = defaultdict(list)
    all_errors = []
    for row, predicted_index, score in zip(rows, predictions, scores):
        if codes[predicted_index] == row["code"]:
            continue
        item = dict(row)
        item["predicted_code"] = codes[predicted_index]
        item["uncalibrated_score"] = round(score, 4)
        wrong[row["code"]].append(item)
        all_errors.append(item)
    selected = []
    for code in codes:
        # Show the most misleading errors, then a less confident error if available.
        candidates = sorted(wrong[code], key=lambda item: item["uncalibrated_score"], reverse=True)
        selected.extend(candidates[:per_class])
    return selected, all_errors


def make_sheet(items, root, output, Image, ImageDraw, ImageFont):
    frame_width, frame_height = 170, 130
    row_height = 180
    canvas = Image.new("RGB", (frame_width * 3 + 20, row_height * len(items) + 10), "#fffaf1")
    painter = ImageDraw.Draw(canvas)
    zip_groups = defaultdict(list)
    for index, item in enumerate(items):
        zip_groups[item["source_zip"]].append((index, item))
    for relative_zip, group in zip_groups.items():
        with ZipFile(root / relative_zip) as archive:
            names = archive.namelist()
            for index, item in group:
                clip_prefix = item["clip"].rstrip("/") + "/"
                frames = sorted((name for name in names if name.startswith(clip_prefix) and name.lower().endswith((".jpg", ".jpeg"))), key=lambda name: int(name.rsplit("/", 1)[-1].split("_")[1]))
                chosen = evenly_spaced(frames, 3)
                y = index * row_height
                title = f"{index + 1}. {item['code']} -> {item['predicted_code']}  score={item['uncalibrated_score']:.2f}"
                painter.text((10, y + 5), title, fill="#2c2823")
                painter.text((10, y + 25), item["clip"].rsplit("/", 1)[-1][:65], fill="#5c5650")
                for column, name in enumerate(chosen):
                    with archive.open(name) as stream:
                        with Image.open(BytesIO(stream.read())) as image:
                            thumbnail = image.convert("RGB")
                            thumbnail.thumbnail((frame_width - 10, frame_height))
                            x = column * frame_width + 10
                            canvas.paste(thumbnail, (x, y + 45))
    canvas.save(output)


def run(args):
    import torch
    from PIL import Image, ImageDraw, ImageFont

    if not args.root.is_dir():
        raise FileNotFoundError(f"Dataset root not found: {args.root}")
    if not args.manifest.is_file():
        raise FileNotFoundError(f"Manifest CSV not found: {args.manifest}")
    checkpoint_path = args.model_dir / "cat-behavior-v2.pt"
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"v2 checkpoint not found: {checkpoint_path}")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    _, rows, codes = select_rows(args.manifest, 300, 100, 20261030)
    if codes != checkpoint["codes"]:
        raise ValueError("Checkpoint and manifest class order differ")
    x = load_features(rows, args.model_dir / "feature-cache", torch)
    x = (x - checkpoint["mean"]) / checkpoint["std"]
    head = torch.nn.Sequential(torch.nn.Linear(x.shape[1], 256), torch.nn.ReLU(), torch.nn.Dropout(0.25), torch.nn.Linear(256, len(codes)))
    head.load_state_dict(checkpoint["head"])
    head.eval()
    with torch.inference_mode():
        logits = head(x)
    selected, all_errors = choose_errors(rows, codes, logits, args.per_class, torch)
    args.model_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.model_dir / "cat-behavior-v2-errors.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        fields = ["split", "code", "predicted_code", "uncalibrated_score", "clip", "source_zip", "label_entry"]
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(all_errors, key=lambda row: (row["code"], -row["uncalibrated_score"])))
    png_path = args.model_dir / "cat-behavior-v2-error-sheet.png"
    make_sheet(selected, args.root, png_path, Image, ImageDraw, ImageFont)
    report = {"validation_clips": len(rows), "wrong_predictions": len(all_errors), "selected_contact_sheet_rows": len(selected), "errors_by_true_code": dict(Counter(row["code"] for row in all_errors)), "note": "Scores are uncalibrated. Sheet is for visual error review, not independent model evaluation."}
    report_path = args.model_dir / "cat-behavior-v2-error-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Contact sheet: {png_path}\nError report: {report_path}\nWrong predictions: {len(all_errors)}/{len(rows)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path.home() / "Downloads" / "cat-behavior-manifest.csv")
    parser.add_argument("--model-dir", type=Path, default=Path.home() / "Downloads" / "cat-behavior-v2")
    parser.add_argument("--per-class", type=int, default=2)
    args = parser.parse_args()
    if args.per_class < 1 or args.per_class > 10:
        parser.error("--per-class must be between 1 and 10")
    run(args)


if __name__ == "__main__":
    sys.exit(main())
