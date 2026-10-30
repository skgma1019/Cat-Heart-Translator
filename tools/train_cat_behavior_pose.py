"""Train a CAT behavior pilot from ordered keypoints and bounding boxes only.

Reads label ZIPs in place; does not decode JPGs, extract ZIPs, or alter data.
Uses the same clip selection as v2/v3 for an exploratory comparison.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import json
from pathlib import Path
import sys
from zipfile import ZipFile

from train_cat_behavior_pilot import scores, select_rows

POINTS = 15
CHANNELS = POINTS * 3 + 4


def annotation_vector(annotation: dict, metadata: dict) -> tuple[list[float], int]:
    box = annotation.get("bounding_box") or {}
    try:
        image_w, image_h = float(metadata["width"]), float(metadata["height"])
        x, y = float(box["x"]), float(box["y"])
        width, height = float(box["width"]), float(box["height"])
    except (KeyError, TypeError, ValueError):
        return [0.0] * CHANNELS, 0
    if min(image_w, image_h, width, height) <= 0:
        return [0.0] * CHANNELS, 0
    center_x, center_y = x + width / 2, y + height / 2
    points = annotation.get("keypoints") or {}
    if not isinstance(points, dict):
        points = {}
    vector = []
    visible = 0
    for index in range(1, POINTS + 1):
        point = points.get(str(index))
        try:
            px, py = float(point["x"]), float(point["y"])
            vector.extend(((px - center_x) / width, (py - center_y) / height, 1.0))
            visible += 1
        except (KeyError, TypeError, ValueError):
            vector.extend((0.0, 0.0, 0.0))
    vector.extend((center_x / image_w, center_y / image_h, width / image_w, height / image_h))
    return vector, visible


def clip_sequence(document: dict, frames: int) -> tuple[list[list[float]], int]:
    annotations = [a for a in document.get("annotations", []) if isinstance(a, dict)]
    if not annotations:
        raise ValueError("Clip has no annotations")
    annotations.sort(key=lambda a: (float(a.get("timestamp", 0)), int(a.get("frame_number", 0))))
    if frames == 1:
        selected = [annotations[len(annotations) // 2]]
    else:
        selected = [annotations[round(i * (len(annotations) - 1) / (frames - 1))] for i in range(frames)]
    sequence = []
    visible_total = 0
    for annotation in selected:
        vector, visible = annotation_vector(annotation, document.get("metadata", {}))
        sequence.append(vector)
        visible_total += visible
    return sequence, visible_total


def read_split(rows, root: Path, frames: int, torch):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["label_zip"]].append(row)
    sequences = {}
    stats = Counter()
    for relative_zip, group in sorted(grouped.items()):
        with ZipFile(root / relative_zip) as archive:
            for row in group:
                document = json.loads(archive.read(row["label_entry"]))
                sequence, visible = clip_sequence(document, frames)
                sequences[row["clip"]] = sequence
                stats["sampled_frames"] += frames
                stats["visible_keypoints"] += visible
                stats["possible_keypoints"] += frames * POINTS
                if visible == 0:
                    stats["clips_without_visible_keypoints"] += 1
        print(f"{relative_zip}: {len(group)} label clips read", flush=True)
    return torch.tensor([sequences[row["clip"]] for row in rows], dtype=torch.float32), stats


def make_model(torch, classes: int):
    return torch.nn.Sequential(
        torch.nn.Conv1d(CHANNELS, 64, kernel_size=3, padding=1),
        torch.nn.ReLU(),
        torch.nn.Conv1d(64, 64, kernel_size=3, padding=1),
        torch.nn.ReLU(),
        torch.nn.Flatten(),
        torch.nn.Linear(64 * 16, 128),
        torch.nn.ReLU(),
        torch.nn.Dropout(0.3),
        torch.nn.Linear(128, classes),
    )


def run(args):
    import torch

    if not args.root.is_dir():
        raise FileNotFoundError(f"Dataset root not found: {args.root}")
    if not args.manifest.is_file():
        raise FileNotFoundError(f"Manifest CSV not found: {args.manifest}")
    torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_rows, valid_rows, codes = select_rows(args.manifest, args.train_per_class, args.valid_per_class, args.seed)
    print(f"Device: {device}; train={len(train_rows)}; validation={len(valid_rows)}", flush=True)
    train_x, train_stats = read_split(train_rows, args.root, args.frames, torch)
    valid_x, valid_stats = read_split(valid_rows, args.root, args.frames, torch)
    # Standardize coordinates but preserve binary visibility masks.
    means = train_x.mean(dim=(0, 1))
    scales = train_x.std(dim=(0, 1)).clamp_min(0.05)
    for index in range(2, POINTS * 3, 3):
        means[index], scales[index] = 0.0, 1.0
    train_x = ((train_x - means) / scales).transpose(1, 2).to(device)
    valid_x = ((valid_x - means) / scales).transpose(1, 2).to(device)
    labels = {code: index for index, code in enumerate(codes)}
    train_y = torch.tensor([labels[row["code"]] for row in train_rows], device=device)
    valid_y = torch.tensor([labels[row["code"]] for row in valid_rows], device=device)
    counts = torch.bincount(train_y, minlength=len(codes)).float()
    class_weights = counts.sum() / (len(codes) * counts)
    model = make_model(torch, len(codes)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.0005, weight_decay=0.02)
    best_f1, best_epoch, best_state, stale = -1.0, 0, None, 0
    for epoch in range(1, args.epochs + 1):
        model.train()
        for indices in torch.randperm(len(train_y), device=device).split(64):
            optimizer.zero_grad(set_to_none=True)
            loss = torch.nn.functional.cross_entropy(model(train_x[indices]), train_y[indices], weight=class_weights)
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.inference_mode():
            guessed = model(valid_x).argmax(1).cpu().tolist()
        metrics = scores(guessed, valid_y.cpu().tolist(), codes)
        if metrics["macro_f1"] > best_f1 + 1e-4:
            best_f1, best_epoch, best_state, stale = metrics["macro_f1"], epoch, deepcopy(model.state_dict()), 0
        else:
            stale += 1
        if epoch % 5 == 0 or epoch == 1:
            print(f"Epoch {epoch}: validation macro F1={metrics['macro_f1']:.3f}; best={best_f1:.3f}", flush=True)
        if stale >= args.patience:
            break
    model.load_state_dict(best_state)
    model.eval()
    with torch.inference_mode():
        predicted = model(valid_x).argmax(1).cpu().tolist()
    result = scores(predicted, valid_y.cpu().tolist(), codes)
    result.update({"model": "16-frame normalized keypoints and bounding box Conv1D", "train_clips": len(train_rows), "validation_clips": len(valid_rows), "best_epoch": best_epoch, "codes": codes, "sampled_frames_per_clip": args.frames, "train_annotation_stats": dict(train_stats), "validation_annotation_stats": dict(valid_stats), "seed": args.seed, "torch_version": torch.__version__, "note": "Exploratory comparison, not independent test. Same-cat leakage unknown; do not deploy."})
    args.output.mkdir(parents=True, exist_ok=True)
    metrics_path = args.output / "cat-behavior-pose-metrics.json"
    metrics_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    torch.save({"model": model.cpu().state_dict(), "means": means, "scales": scales, "codes": codes, "frames": args.frames, "architecture": "cat_keypoint_conv1d_v1"}, args.output / "cat-behavior-pose.pt")
    print(f"Validation accuracy={result['accuracy']:.3f}; macro F1={result['macro_f1']:.3f}")
    print(f"Metrics: {metrics_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path.home() / "Downloads" / "cat-behavior-manifest.csv")
    parser.add_argument("--output", type=Path, default=Path.home() / "Downloads" / "cat-behavior-pose")
    parser.add_argument("--train-per-class", type=int, default=300)
    parser.add_argument("--valid-per-class", type=int, default=100)
    parser.add_argument("--frames", type=int, default=16)
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--patience", type=int, default=12)
    parser.add_argument("--seed", type=int, default=20261030)
    args = parser.parse_args()
    if args.frames != 16 or min(args.train_per_class, args.valid_per_class, args.epochs, args.patience) < 1:
        parser.error("This Conv1D architecture requires --frames 16 and positive limits")
    run(args)


if __name__ == "__main__":
    sys.exit(main())
