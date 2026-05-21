"""
YOLOv8 Dataset Preparation Pipeline  (Windows MAX_PATH fix)
=============================================================
- Splits train -> train / val / test  (70 / 20 / 10)
- Fixes data.yaml paths
- Applies heavy augmentation (mosaic, perspective, HSV, flip, blur, noise)
- Handles Windows 260-char MAX_PATH by renaming files to short IDs

Usage:
    pip install opencv-python pyyaml tqdm
    python prepare_dataset.py
Run from the dataset root folder.
"""

import os, shutil, random, math, yaml, cv2, hashlib
import numpy as np
from pathlib import Path
from tqdm import tqdm


# ── Enable long-path support via \\?\ prefix on Windows ──────────────────────
def lp(p) -> str:
    """Return an extended-length path string safe for Windows API calls."""
    s = str(Path(p).resolve())
    if os.name == "nt" and not s.startswith("\\\\?\\"):
        s = "\\\\?\\" + s
    return s


# ── CONFIG ────────────────────────────────────────────────────────────────────
DATASET_ROOT   = Path(__file__).parent
TRAIN_RATIO    = 0.70
VAL_RATIO      = 0.20
TEST_RATIO     = 0.10
AUG_MULTIPLIER = 3
SEED           = 42
IMAGE_EXTS     = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
# ─────────────────────────────────────────────────────────────────────────────

random.seed(SEED)
np.random.seed(SEED)


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def short_id(path: Path, idx: int) -> str:
    """
    Short, collision-free filename: img_<zero-padded-index>_<6-char-hash>
    e.g.  img_000042_3fa1bc
    """
    h = hashlib.md5(path.name.encode()).hexdigest()[:6]
    return f"img_{idx:06d}_{h}"


def safe_imread(p: Path):
    """Read image using numpy fromfile to bypass Windows path-length limits."""
    arr = np.fromfile(lp(p), dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def safe_imwrite(p: Path, img):
    """Write image using tofile to bypass Windows path-length limits."""
    os.makedirs(lp(p.parent), exist_ok=True)
    ext = p.suffix.lower() if p.suffix else ".jpg"
    ok, buf = cv2.imencode(ext, img)
    if ok:
        buf.tofile(lp(p))


def read_labels(lbl_path: Path):
    boxes = []
    try:
        with open(lp(lbl_path), "r") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 5:
                    boxes.append([int(parts[0])] + [float(x) for x in parts[1:]])
    except (FileNotFoundError, OSError):
        pass
    return boxes


def write_labels(lbl_path: Path, boxes):
    os.makedirs(lp(lbl_path.parent), exist_ok=True)
    lines = [f"{int(c)} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"
             for c, cx, cy, w, h in boxes]
    with open(lp(lbl_path), "w") as f:
        f.write("\n".join(lines))


# ═══════════════════════════════════════════════════════════════════════════════
# 1. COLLECT
# ═══════════════════════════════════════════════════════════════════════════════

def collect_pairs(image_dir: Path):
    label_dir = image_dir.parent.parent / "train" / "labels"
    pairs, skipped = [], 0
    for img in sorted(image_dir.iterdir()):
        if img.suffix.lower() not in IMAGE_EXTS:
            continue
        lbl = label_dir / (img.stem + ".txt")
        if lbl.exists():
            pairs.append((img, lbl))
        else:
            skipped += 1
    if skipped:
        print(f"  [WARN] Skipped {skipped} images with no matching label.")
    return pairs


# ═══════════════════════════════════════════════════════════════════════════════
# 2. SPLIT
# ═══════════════════════════════════════════════════════════════════════════════

def split_dataset(pairs):
    random.shuffle(pairs)
    n       = len(pairs)
    n_val   = math.floor(n * VAL_RATIO)
    n_test  = math.floor(n * TEST_RATIO)
    n_train = n - n_val - n_test
    return {
        "train": pairs[:n_train],
        "val":   pairs[n_train : n_train + n_val],
        "test":  pairs[n_train + n_val :],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. COPY  (rename to short IDs to dodge MAX_PATH)
# ═══════════════════════════════════════════════════════════════════════════════

def copy_split(splits: dict, out_root: Path):
    """
    Copy files renaming them to short IDs.
    Returns dict: split_name -> list of (new_img_path, new_lbl_path)
    """
    split_index = {}
    global_idx  = 0

    for split_name, pairs in splits.items():
        img_dir = out_root / split_name / "images"
        lbl_dir = out_root / split_name / "labels"
        os.makedirs(lp(img_dir), exist_ok=True)
        os.makedirs(lp(lbl_dir), exist_ok=True)

        new_pairs = []
        for orig_img, orig_lbl in tqdm(pairs, desc=f"  Copying {split_name:5s}"):
            sid     = short_id(orig_img, global_idx)
            new_img = img_dir / (sid + ".jpg")
            new_lbl = lbl_dir / (sid + ".txt")

            img = safe_imread(orig_img)
            if img is None:
                global_idx += 1
                continue
            safe_imwrite(new_img, img)

            boxes = read_labels(orig_lbl)
            write_labels(new_lbl, boxes)

            new_pairs.append((new_img, new_lbl))
            global_idx += 1

        split_index[split_name] = new_pairs

    print(f"  Files copied & renamed -> {out_root}")
    return split_index


# ═══════════════════════════════════════════════════════════════════════════════
# 4. AUGMENTATION
# ═══════════════════════════════════════════════════════════════════════════════

def hsv_shift(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 0] = (hsv[..., 0] + random.uniform(-18, 18)) % 180
    hsv[..., 1] = np.clip(hsv[..., 1] * random.uniform(0.5, 1.5), 0, 255)
    hsv[..., 2] = np.clip(hsv[..., 2] * random.uniform(0.5, 1.5), 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def flip_horizontal(img, boxes):
    img   = cv2.flip(img, 1)
    boxes = [[c, 1.0 - cx, cy, w, h] for c, cx, cy, w, h in boxes]
    return img, boxes


def perspective_transform(img, boxes):
    h, w   = img.shape[:2]
    margin = 0.08
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([
        [random.uniform(0, margin)*w,       random.uniform(0, margin)*h],
        [random.uniform(1-margin, 1)*w,     random.uniform(0, margin)*h],
        [random.uniform(1-margin, 1)*w,     random.uniform(1-margin, 1)*h],
        [random.uniform(0, margin)*w,       random.uniform(1-margin, 1)*h],
    ])
    M   = cv2.getPerspectiveTransform(src, dst)
    img = cv2.warpPerspective(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)

    new_boxes = []
    for cls, cx, cy, bw, bh in boxes:
        pts = np.float32([
            [(cx-bw/2)*w, (cy-bh/2)*h],
            [(cx+bw/2)*w, (cy-bh/2)*h],
            [(cx+bw/2)*w, (cy+bh/2)*h],
            [(cx-bw/2)*w, (cy+bh/2)*h],
        ]).reshape(-1, 1, 2)
        pts_t    = cv2.perspectiveTransform(pts, M).reshape(-1, 2)
        x_coords = np.clip(pts_t[:, 0] / w, 0, 1)
        y_coords = np.clip(pts_t[:, 1] / h, 0, 1)
        ncx = (x_coords.min() + x_coords.max()) / 2
        ncy = (y_coords.min() + y_coords.max()) / 2
        nbw = x_coords.max() - x_coords.min()
        nbh = y_coords.max() - y_coords.min()
        if nbw > 0.01 and nbh > 0.01:
            new_boxes.append([cls, ncx, ncy, nbw, nbh])
    return img, new_boxes


def mosaic_aug(all_pairs, target_size=640):
    samples  = random.choices(all_pairs, k=4)
    s        = target_size
    canvas   = np.zeros((s*2, s*2, 3), dtype=np.uint8)
    all_boxes = []
    positions = [(0, 0), (s, 0), (0, s), (s, s)]

    for (ip, lp_path), (xo, yo) in zip(samples, positions):
        img = safe_imread(ip)
        if img is None:
            img = np.zeros((s, s, 3), dtype=np.uint8)
        img = cv2.resize(img, (s, s))
        canvas[yo:yo+s, xo:xo+s] = img
        for cls, cx, cy, bw, bh in read_labels(lp_path):
            all_boxes.append([cls,
                               (xo + cx*s) / (s*2),
                               (yo + cy*s) / (s*2),
                               bw/2, bh/2])

    canvas = canvas[s//2 : s//2+s, s//2 : s//2+s]
    final  = []
    for cls, cx, cy, bw, bh in all_boxes:
        ncx = (cx*2 - 0.5)*2
        ncy = (cy*2 - 0.5)*2
        if 0 < ncx < 1 and 0 < ncy < 1:
            final.append([cls, ncx, ncy, bw*2, bh*2])
    return canvas, final


def add_noise(img):
    noise = np.random.randn(*img.shape).astype(np.float32) * random.uniform(5, 20)
    return np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def gaussian_blur(img):
    k = random.choice([3, 5])
    return cv2.GaussianBlur(img, (k, k), 0)


def augment_split(split_dir: Path, pairs: list, multiplier: int):
    img_dir   = split_dir / "images"
    lbl_dir   = split_dir / "labels"
    aug_count = 0

    for img_path, lbl_path in tqdm(pairs, desc=f"  Augmenting {split_dir.name:5s}"):
        img = safe_imread(img_path)
        if img is None:
            continue
        boxes = read_labels(lbl_path)

        for i in range(multiplier):
            aug_img   = img.copy()
            aug_boxes = [b[:] for b in boxes]

            ops = random.sample(
                ["hsv", "flip", "perspective", "mosaic", "noise", "blur"],
                k=random.randint(2, 4)
            )
            for op in ops:
                if op == "hsv":
                    aug_img = hsv_shift(aug_img)
                elif op == "flip":
                    aug_img, aug_boxes = flip_horizontal(aug_img, aug_boxes)
                elif op == "perspective":
                    aug_img, aug_boxes = perspective_transform(aug_img, aug_boxes)
                elif op == "mosaic":
                    aug_img, aug_boxes = mosaic_aug(pairs)
                elif op == "noise":
                    aug_img = add_noise(aug_img)
                elif op == "blur":
                    aug_img = gaussian_blur(aug_img)

            out_name = f"{img_path.stem}_a{i}"
            safe_imwrite(img_dir / f"{out_name}.jpg", aug_img)
            write_labels(lbl_dir / f"{out_name}.txt", aug_boxes)
            aug_count += 1

    print(f"  Generated {aug_count} augmented images in {split_dir.name}/")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. data.yaml
# ═══════════════════════════════════════════════════════════════════════════════

def write_yaml(out_root: Path, names):
    cfg = {
        "path":  str(out_root.resolve()).replace("\\", "/"),
        "train": "train/images",
        "val":   "val/images",
        "test":  "test/images",
        "nc":    len(names),
        "names": names,
    }
    yaml_path = out_root / "data.yaml"
    with open(lp(yaml_path), "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
    print(f"  data.yaml -> {yaml_path}")
    return yaml_path


# ═══════════════════════════════════════════════════════════════════════════════
# 6. TRAINING HINT
# ═══════════════════════════════════════════════════════════════════════════════

def print_training_command(yaml_path: Path):
    p = str(yaml_path).replace("\\", "/")
    print("\n" + "="*60)
    print("  NEXT STEP -- Train YOLOv8")
    print("="*60)
    print("  pip install ultralytics\n")
    print(f'  yolo train data="{p}" model=yolov8n.pt epochs=100 imgsz=640 batch=16 device=0 name=indoor_obstacle_v1\n')
    print("  Jetson Orin Nano TensorRT export (run after training):")
    print("  yolo export model=runs/detect/indoor_obstacle_v1/weights/best.pt format=engine device=0")
    print("="*60 + "\n")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n  YOLOv8 Dataset Preparation Pipeline  (Windows MAX_PATH safe)")
    print("="*60)

    orig_train_img = DATASET_ROOT / "train" / "images"
    if not orig_train_img.exists():
        raise FileNotFoundError(
            f"Not found: {orig_train_img}\n"
            "Run this script from the dataset root folder."
        )

    out_root = DATASET_ROOT / "dataset_prepared"
    if out_root.exists():
        print(f"  [INFO] Removing existing {out_root.name}/ ...")
        shutil.rmtree(lp(out_root))

    print("\n[1/5] Collecting image-label pairs ...")
    pairs = collect_pairs(orig_train_img)
    print(f"  Found {len(pairs)} valid pairs.")
    if not pairs:
        raise RuntimeError("No pairs found. Check folder structure.")

    print(f"\n[2/5] Splitting  (train={TRAIN_RATIO:.0%} / val={VAL_RATIO:.0%} / test={TEST_RATIO:.0%}) ...")
    splits = split_dataset(pairs)
    for k, v in splits.items():
        print(f"  {k:5s}: {len(v)} images")

    print("\n[3/5] Copying & renaming to short IDs ...")
    split_index = copy_split(splits, out_root)

    print(f"\n[4/5] Augmenting train set  (x{AUG_MULTIPLIER} per image) ...")
    augment_split(out_root / "train", split_index["train"], AUG_MULTIPLIER)

    print("\n[5/5] Writing data.yaml ...")
    names     = ['chair', 'door', 'person', 'shelf', 'stair', 'table', 'wardrobe']
    yaml_path = write_yaml(out_root, names)

    print(f"\n  Done! Dataset ready in: {out_root}")
    print_training_command(yaml_path)


if __name__ == "__main__":
    main()