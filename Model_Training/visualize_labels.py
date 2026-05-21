import cv2
import os
import random
from pathlib import Path

# ══════════════════════════════════════════════════════════════════
# Configuration Area
# ══════════════════════════════════════════════════════════════════
DATASET_DIR = "experiment_dataset/train"  # Which split to check
OUTPUT_DIR = "annotation_check"           # Output save location
CLASS_NAMES = ['chair', 'door', 'person', 'shelf', 'stair', 'table', 'wardrobe']

# Assign colors for different classes (B, G, R)
COLORS = [
    (255, 0, 0),   # chair - Blue
    (0, 255, 0),   # door - Green
    (0, 0, 255),   # person - Red
    (255, 255, 0), # shelf - Cyan
    (255, 0, 255), # stair - Purple
    (0, 255, 255), # table - Yellow
    (128, 0, 128)  # wardrobe - Dark Purple
]

def draw_yolo_labels(image_path, label_path):
    # Read the image
    img = cv2.imread(str(image_path))
    if img is None:
        return None
    
    h, w, _ = img.shape
    
    # Read the label file
    if not os.path.exists(label_path):
        return img

    with open(label_path, 'r') as f:
        lines = f.readlines()
        
    for line in lines:
        parts = line.strip().split()
        if len(parts) != 5:
            continue
            
        cls_id = int(parts[0])
        # YOLO format: x_center, y_center, width, height (all normalized values 0-1)
        x_c, y_c, bw, bh = map(float, parts[1:])
        
        # Convert back to pixel coordinates
        x1 = int((x_c - bw/2) * w)
        y1 = int((y_c - bh/2) * h)
        x2 = int((x_c + bw/2) * w)
        y2 = int((y_c + bh/2) * h)
        
        # Draw bounding box
        color = COLORS[cls_id % len(COLORS)]
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        
        # Draw label text
        label_text = CLASS_NAMES[cls_id] if cls_id < len(CLASS_NAMES) else str(cls_id)
        cv2.putText(img, label_text, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
    return img

def main():
    img_dir = Path(DATASET_DIR) / "images"
    lbl_dir = Path(DATASET_DIR) / "labels"
    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Get a list of all image files
    image_files = list(img_dir.glob("*.jpg")) + list(img_dir.glob("*.png"))
    
    if not image_files:
        print(f"❌ Error: No images found in {img_dir}")
        return

    # Randomly sample 20 images for inspection, or you can change the number
    sample_size = min(20, len(image_files))
    samples = random.sample(image_files, sample_size)

    print(f"🚀 Drawing annotations for {sample_size} images...")

    for img_path in samples:
        lbl_path = lbl_dir / (img_path.stem + ".txt")
        
        # Draw
        result_img = draw_yolo_labels(img_path, lbl_path)
        
        if result_img is not None:
            # Save to output directory
            save_path = out_dir / img_path.name
            cv2.imwrite(str(save_path), result_img)

    print(f"✅ Inspection complete! Please check the folder: {out_dir.resolve()}")

if __name__ == "__main__":
    main()