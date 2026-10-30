"""Second CAT behavior experiment: more clips and order-sensitive frame features.

Reads ZIPs in place. Per-archive feature caches allow a stopped run to resume.
The resulting checkpoint is experimental and must not be deployed directly.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import sys
from zipfile import ZipFile

from train_cat_behavior_pilot import evenly_spaced, scores, select_rows


def temporal_summary(vectors, torch):
    """Keep clip appearance, variation, and direction of adjacent changes."""
    return torch.cat((vectors.mean(0), vectors.std(0, unbiased=False), vectors[-1] - vectors[0], (vectors[1:] - vectors[:-1]).abs().mean(0)))


def encode_split(rows, root, output, encoder, transform, torch, Image, device, frame_count, batch_size, split):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["source_zip"]].append(row)
    vectors_by_clip = {}
    cache_dir = output / "feature-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    for relative_zip, group in sorted(grouped.items()):
        cache_path = cache_dir / f"{split}-{Path(relative_zip).stem}.pt"
        clips = [row["clip"] for row in group]
        cache_key = {"clips": clips, "frames": frame_count, "encoder": "MobileNet_V3_Small_Weights.DEFAULT"}
        if cache_path.exists():
            cached = torch.load(cache_path, map_location="cpu", weights_only=True)
            if cached["key"] == cache_key:
                vectors_by_clip.update(zip(clips, cached["features"]))
                print(f"{relative_zip}: reused {len(clips)} cached clips", flush=True)
                continue
        with ZipFile(root / relative_zip) as archive:
            names_by_clip = defaultdict(list)
            wanted = set(clips)
            for name in archive.namelist():
                clip = name.rsplit("/", 1)[0]
                if clip in wanted and name.lower().endswith((".jpg", ".jpeg")):
                    names_by_clip[clip].append(name)
            results = []
            for index, clip in enumerate(clips, 1):
                names = sorted(names_by_clip[clip], key=lambda name: int(name.rsplit("/", 1)[-1].split("_")[1]))
                if not names:
                    raise ValueError(f"No JPEG frames for {relative_zip}: {clip}")
                selected = evenly_spaced(names, frame_count)
                images = []
                for name in selected:
                    with archive.open(name) as stream:
                        with Image.open(BytesIO(stream.read())) as image:
                            images.append(transform(image.convert("RGB")))
                encoded = []
                with torch.inference_mode():
                    for start in range(0, len(images), batch_size):
                        batch = torch.stack(images[start:start + batch_size]).to(device)
                        encoded.append(encoder(batch).float().cpu())
                results.append(temporal_summary(torch.cat(encoded), torch))
                if index % 25 == 0 or index == len(clips):
                    print(f"{relative_zip}: {index}/{len(clips)} clips encoded", flush=True)
        features = torch.stack(results)
        torch.save({"key": cache_key, "features": features}, cache_path)
        vectors_by_clip.update(zip(clips, features))
    return torch.stack([vectors_by_clip[row["clip"]] for row in rows])


def run(args):
    import torch
    from PIL import Image
    from torchvision.models import MobileNet_V3_Small_Weights, mobilenet_v3_small

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU unavailable. Check CUDA PyTorch and NVIDIA driver.")
    if not args.root.is_dir():
        raise FileNotFoundError(f"Dataset root not found: {args.root}")
    if not args.manifest.is_file():
        raise FileNotFoundError(f"Manifest CSV not found: {args.manifest}")
    args.output.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(args.seed)
    device = torch.device("cuda")
    train_rows, valid_rows, codes = select_rows(args.manifest, args.train_per_class, args.valid_per_class, args.seed)
    print(f"GPU: {torch.cuda.get_device_name(0)}; train={len(train_rows)}; validation={len(valid_rows)}", flush=True)
    print("Feature extraction may take hours; completed archives are cached for restart.", flush=True)
    weights = MobileNet_V3_Small_Weights.DEFAULT
    encoder = mobilenet_v3_small(weights=weights)
    encoder.classifier = torch.nn.Identity()
    encoder = encoder.to(device).eval()
    train_x = encode_split(train_rows, args.root, args.output, encoder, weights.transforms(), torch, Image, device, args.frames, args.batch_size, "Training")
    valid_x = encode_split(valid_rows, args.root, args.output, encoder, weights.transforms(), torch, Image, device, args.frames, args.batch_size, "Validation")
    mean = train_x.mean(0)
    std = train_x.std(0).clamp_min(1e-5)
    train_x = ((train_x - mean) / std).to(device)
    valid_x = ((valid_x - mean) / std).to(device)
    label_index = {code: index for index, code in enumerate(codes)}
    train_y = torch.tensor([label_index[row["code"]] for row in train_rows], device=device)
    valid_y = torch.tensor([label_index[row["code"]] for row in valid_rows], device=device)
    counts = torch.bincount(train_y, minlength=len(codes)).float()
    weights_for_loss = counts.sum() / (len(codes) * counts)
    head = torch.nn.Sequential(torch.nn.Linear(train_x.shape[1], 256), torch.nn.ReLU(), torch.nn.Dropout(0.25), torch.nn.Linear(256, len(codes))).to(device)
    optimizer = torch.optim.AdamW(head.parameters(), lr=0.0003, weight_decay=0.02)
    best_f1 = -1.0
    best_state = None
    best_epoch = 0
    stale = 0
    for epoch in range(1, args.epochs + 1):
        head.train()
        for ids in torch.randperm(len(train_y), device=device).split(64):
            optimizer.zero_grad(set_to_none=True)
            loss = torch.nn.functional.cross_entropy(head(train_x[ids]), train_y[ids], weight=weights_for_loss)
            loss.backward()
            optimizer.step()
        head.eval()
        with torch.inference_mode():
            guesses = head(valid_x).argmax(1).cpu().tolist()
        metrics = scores(guesses, valid_y.cpu().tolist(), codes)
        if metrics["macro_f1"] > best_f1 + 1e-4:
            best_f1 = metrics["macro_f1"]
            best_state = deepcopy(head.state_dict())
            best_epoch = epoch
            stale = 0
        else:
            stale += 1
        if epoch % 5 == 0 or epoch == 1:
            print(f"Epoch {epoch}: validation macro F1={metrics['macro_f1']:.3f}; best={best_f1:.3f}", flush=True)
        if stale >= args.patience:
            break
    head.load_state_dict(best_state)
    head.eval()
    with torch.inference_mode():
        predicted = head(valid_x).argmax(1).cpu().tolist()
    result = scores(predicted, valid_y.cpu().tolist(), codes)
    result.update({"model": "MobileNetV3 Small frozen encoder + temporal summary + MLP", "train_clips": len(train_rows), "validation_clips": len(valid_rows), "frames_per_clip": args.frames, "best_epoch": best_epoch, "codes": codes, "seed": args.seed, "torch_version": torch.__version__, "note": "Pilot; validation used for checkpoint selection, not an independent test. Same-cat leakage unknown. Scores are not calibrated probabilities. Do not deploy."})
    metrics_path = args.output / "cat-behavior-v2-metrics.json"
    metrics_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    torch.save({"encoder": encoder.cpu().state_dict(), "head": head.cpu().state_dict(), "mean": mean, "std": std, "codes": codes, "frames": args.frames, "architecture": "mobilenet_v3_small_temporal_v2"}, args.output / "cat-behavior-v2.pt")
    print(f"Validation accuracy={result['accuracy']:.3f}; macro F1={result['macro_f1']:.3f}; best epoch={best_epoch}")
    print(f"Metrics: {metrics_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path.home() / "Downloads" / "cat-behavior-manifest.csv")
    parser.add_argument("--output", type=Path, default=Path.home() / "Downloads" / "cat-behavior-v2")
    parser.add_argument("--train-per-class", type=int, default=300)
    parser.add_argument("--valid-per-class", type=int, default=100)
    parser.add_argument("--frames", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--patience", type=int, default=12)
    parser.add_argument("--seed", type=int, default=20261030)
    args = parser.parse_args()
    if min(args.train_per_class, args.valid_per_class, args.frames, args.batch_size, args.epochs, args.patience) < 1 or args.frames < 2:
        parser.error("All size options must be positive; --frames must be at least 2")
    run(args)


if __name__ == "__main__":
    sys.exit(main())
