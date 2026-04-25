import os
from pathlib import Path
from PIL import Image  # Used for image corruption check

def get_long_path(path_obj: Path) -> str:
    """Handles the Windows long path prefix (MAX_PATH fix)."""
    path_str = str(path_obj.resolve())
    if os.name == 'nt' and not path_str.startswith("\\\\?\\"):
        return "\\\\?\\" + path_str
    return path_str

def is_image_valid(img_path):
    """Verifies if the image can be opened normally (filters corrupt files)."""
    try:
        with Image.open(img_path) as img:
            img.verify()  # Verify file integrity
        return True
    except Exception:
        return False

def run_experiment():
    base_dir = Path.cwd()
    # Output directory; original data remains untouched
    exp_base = base_dir / "experiment_dataset"
    
    print(f"🚀 Starting renaming experiment...")
    print(f"📂 Source path: {base_dir}")
    print(f"📂 Target path: {exp_base}")

    stats = {"success": 0, "bad_images": 0, "missing_labels": 0}

    # Processing scope: 'train' and 'valid' splits
    for split in ['train', 'valid']:
        src_imgs_dir = base_dir / split / 'images'
        src_lbls_dir = base_dir / split / 'labels'
        
        if not src_imgs_dir.exists():
            continue

        dst_imgs_dir = exp_base / split / 'images'
        dst_lbls_dir = exp_base / split / 'labels'
        dst_imgs_dir.mkdir(parents=True, exist_ok=True)
        dst_lbls_dir.mkdir(parents=True, exist_ok=True)

        # Retrieve images (handling long paths)
        safe_src_imgs = get_long_path(src_imgs_dir)
        all_files = os.listdir(safe_src_imgs)
        images = [f for f in all_files if f.lower().endswith(('.jpg', '.jpeg', '.png'))]

        print(f"\nProcessing {split} split ({len(images)} images total)...")

        for idx, img_name in enumerate(images):
            old_img_path = src_imgs_dir / img_name
            safe_old_img = get_long_path(old_img_path)
            
            # 1. Corruption check
            if not is_image_valid(safe_old_img):
                stats["bad_images"] += 1
                continue

            # 2. Label verification
            label_name = os.path.splitext(img_name)[0] + ".txt"
            old_lbl_path = src_lbls_dir / label_name
            safe_old_lbl = get_long_path(old_lbl_path)

            if not os.path.exists(safe_old_lbl):
                stats["missing_labels"] += 1

            # 3. Create short-path hard links
            new_name = f"{idx:06d}{os.path.splitext(img_name)[1]}"
            new_img_path = dst_imgs_dir / new_name
            new_lbl_path = dst_lbls_dir / (f"{idx:06d}.txt")

            try:
                # os.link creates a new directory entry pointing to the same data block
                if not new_img_path.exists():
                    os.link(safe_old_img, get_long_path(new_img_path))
                
                if os.path.exists(safe_old_lbl) and not new_lbl_path.exists():
                    os.link(safe_old_lbl, get_long_path(new_lbl_path))
                
                stats["success"] += 1
            except Exception as e:
                print(f"❌ Link failed: {img_name[:30]}... Error: {e}")

    print("\n" + "="*30)
    print(f"✅ Experiment Complete!")
    print(f"📊 Successfully mapped: {stats['success']} images")
    print(f"🚫 Corrupt images removed: {stats['bad_images']}")
    print(f"⚠️ Missing labels: {stats['missing_labels']}")
    print(f"💡 Note: Files in 'experiment_dataset' now have shorter names and use zero extra disk space.")
    print("="*30)

if __name__ == "__main__":
    run_experiment()