"""Train a small CAT clip classifier from the audited ZIP manifest on Windows.

Reads source ZIPs in place, samples frames per clip, and writes a checkpoint and
metrics to Downloads. Does not change the original dataset or the sound model.
This is a pilot: do not deploy its scores as calibrated probabilities.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from io import BytesIO
import json
from pathlib import Path
import random
import sys
from zipfile import ZipFile


def select_rows(manifest: Path, per_train: int, per_valid: int, seed: int) -> tuple[list[dict], list[dict], list[str]]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["split"] in {"Training", "Validation"}:
                grouped[(row["split"], row["code"])].append(row)
    codes = sorted({code for _, code in grouped})
    if len(codes) != 12 or any(not grouped.get((split, code)) for split in ("Training", "Validation") for code in codes):
        raise ValueError("Manifest must contain both splits for all 12 CAT codes")
    rng = random.Random(seed)
    selected: dict[str, list[dict]] = {"Training": [], "Validation": []}
    for split, limit in (("Training", per_train), ("Validation", per_valid)):
        for code in codes:
            candidates = sorted(grouped[(split, code)], key=lambda row: row["clip"])
            selected[split].extend(rng.sample(candidates, min(limit, len(candidates))))
    return selected["Training"], selected["Validation"], codes


def frame_names(archive: ZipFile, clip: str) -> list[str]:
    prefix = clip.rstrip("/") + "/"
    return sorted((n for n in archive.namelist() if n.startswith(prefix) and n.lower().endswith((".jpg", ".jpeg"))), key=lambda n: int(n.rsplit("/", 1)[-1].split("_")[1]))


def evenly_spaced(items: list[str], count: int) -> list[str]:
    if not items:
        raise ValueError("Clip contains no JPEG frames")
    if count == 1:
        return [items[len(items) // 2]]
    return [items[round(i * (len(items) - 1) / (count - 1))] for i in range(count)]


def encode_rows(rows: list[dict], root: Path, model, transform, torch, Image, device, frame_count: int, batch_size: int):
    import numpy as np

    features: dict[str, object] = {}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["source_zip"]].append(row)
    for relative_zip, group in sorted(grouped.items()):
        path = root / relative_zip
        with ZipFile(path) as archive:
            for index, row in enumerate(group, 1):
                names = evenly_spaced(frame_names(archive, row["clip"]), frame_count)
                images = []
                for name in names:
                    with archive.open(name) as stream:
                        with Image.open(BytesIO(stream.read())) as image:
                            images.append(transform(image.convert("RGB")))
                vectors = []
                with torch.inference_mode():
                    for start in range(0, len(images), batch_size):
                        batch = torch.stack(images[start:start + batch_size]).to(device)
                        vectors.append(model(batch).float().cpu())
                features[row["clip"]] = torch.cat(vectors).mean(0).numpy()
                if index % 25 == 0 or index == len(group):
                    print(f"{relative_zip}: {index}/{len(group)} clips encoded", flush=True)
    x = np.stack([features[row["clip"]] for row in rows]).astype("float32")
    return torch.from_numpy(x)


def scores(predicted, actual, codes: list[str]):
    confusion = [[0] * len(codes) for _ in codes]
    for truth, guess in zip(actual, predicted):
        confusion[int(truth)][int(guess)] += 1
    total = sum(map(sum, confusion))
    accuracy = sum(confusion[i][i] for i in range(len(codes))) / total
    f1 = []
    recall = []
    for i in range(len(codes)):
        tp = confusion[i][i]
        fp = sum(confusion[j][i] for j in range(len(codes)) if j != i)
        fn = sum(confusion[i][j] for j in range(len(codes)) if j != i)
        f1.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0)
        recall.append(tp / (tp + fn) if tp + fn else 0)
    return {"accuracy": accuracy, "macro_f1": sum(f1) / len(f1), "per_class_recall": dict(zip(codes, recall)), "confusion_matrix": confusion}


def run(args) -> None:
    import torch
    from PIL import Image
    from torchvision.models import MobileNet_V3_Small_Weights, mobilenet_v3_small

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU unavailable. Install a CUDA-enabled PyTorch build and update NVIDIA driver before training.")
    if not args.root.is_dir() or not args.manifest.is_file():
        raise FileNotFoundError("Dataset root or manifest CSV not found")
    torch.manual_seed(args.seed)
    device = torch.device("cuda")
    train_rows, valid_rows, codes = select_rows(args.manifest, args.train_per_class, args.valid_per_class, args.seed)
    if {r["clip"] for r in train_rows} & {r["clip"] for r in valid_rows}:
        raise ValueError("Training and Validation clip names overlap")
    print(f"GPU: {torch.cuda.get_device_name(0)}; train={len(train_rows)}; validation={len(valid_rows)}", flush=True)
    weights = MobileNet_V3_Small_Weights.DEFAULT
    encoder = mobilenet_v3_small(weights=weights)
    encoder.classifier = torch.nn.Identity()
    encoder = encoder.to(device).eval()
    transform = weights.transforms()
    train_x = encode_rows(train_rows, args.root, encoder, transform, torch, Image, device, args.frames, args.batch_size)
    valid_x = encode_rows(valid_rows, args.root, encoder, transform, torch, Image, device, args.frames, args.batch_size)
    labels = {code: i for i, code in enumerate(codes)}
    train_y = torch.tensor([labels[r["code"]] for r in train_rows], dtype=torch.long)
    valid_y = torch.tensor([labels[r["code"]] for r in valid_rows], dtype=torch.long)
    counts = Counter(train_y.tolist())
    class_weights = torch.tensor([len(train_y) / (len(codes) * counts[i]) for i in range(len(codes))], device=device)
    head = torch.nn.Linear(train_x.shape[1], len(codes)).to(device)
    optimizer = torch.optim.AdamW(head.parameters(), lr=0.001, weight_decay=0.01)
    train_x_gpu, train_y_gpu = train_x.to(device), train_y.to(device)
    for epoch in range(1, args.epochs + 1):
        head.train()
        order = torch.randperm(len(train_y_gpu), device=device)
        for batch_ids in order.split(64):
            optimizer.zero_grad(set_to_none=True)
            loss = torch.nn.functional.cross_entropy(head(train_x_gpu[batch_ids]), train_y_gpu[batch_ids], weight=class_weights)
            loss.backward()
            optimizer.step()
        if epoch % 5 == 0 or epoch == args.epochs:
            print(f"Epoch {epoch}/{args.epochs}: loss={loss.item():.4f}", flush=True)
    head.eval()
    with torch.inference_mode():
        predicted = head(valid_x.to(device)).argmax(1).cpu().tolist()
    result = scores(predicted, valid_y.tolist(), codes)
    result.update({"model": "MobileNetV3 Small frozen image encoder + mean of sampled frames + linear classifier", "train_clips": len(train_rows), "validation_clips": len(valid_rows), "frames_per_clip": args.frames, "codes": codes, "seed": args.seed, "torch_version": torch.__version__, "note": "Pilot on a subset. Same-cat leakage cannot be ruled out. Softmax scores are not calibrated probabilities; do not deploy yet."})
    args.output.mkdir(parents=True, exist_ok=True)
    metrics_path = args.output / "cat-behavior-pilot-metrics.json"
    metrics_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    torch.save({"encoder": encoder.cpu().state_dict(), "head": head.cpu().state_dict(), "codes": codes, "frames": args.frames, "architecture": "mobilenet_v3_small"}, args.output / "cat-behavior-pilot.pt")
    print(f"Validation accuracy={result['accuracy']:.3f}; macro F1={result['macro_f1']:.3f}")
    print(f"Metrics: {metrics_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path.home() / "Downloads" / "cat-behavior-manifest.csv")
    parser.add_argument("--output", type=Path, default=Path.home() / "Downloads" / "cat-behavior-pilot")
    parser.add_argument("--train-per-class", type=int, default=100)
    parser.add_argument("--valid-per-class", type=int, default=30)
    parser.add_argument("--frames", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20261030)
    args = parser.parse_args()
    if min(args.train_per_class, args.valid_per_class, args.frames, args.batch_size, args.epochs) < 1:
        parser.error("All size and epoch options must be positive")
    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
