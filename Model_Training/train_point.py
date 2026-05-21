"""
YOLOv8 Clean Training Script - Perfect Path Fix Version
"""

import sys
import time
import logging
from pathlib import Path
from datetime import datetime

# ══════════════════════════════════════════════════════════════════
#  CONFIG AREA
# ══════════════════════════════════════════════════════════════════

YAML_PATH = "data_exp.yaml"  
MODEL_WEIGHTS = "yolov8s.pt"  # Core: Upgraded to Small version to increase feature capacity


# ── Training Parameters ───────────────────────────────────────────
EPOCHS    = 60     # Large dataset, requires more epochs for fine-tuning
IMGSZ     = 640    # Increase resolution to capture small obstacles
BATCH     = 16     # Recommended 16 for 8GB VRAM at 640 resolution to prevent OOM
DEVICE    = 0      
WORKERS   = 2      # Increase this if CPU is strong to speed up image loading
PATIENCE  = 10
FRACTION  = 0.5    

# ── Path Control & Tagging (Core Fix) ─────────────────────────────
# Fix 1: Use absolute path, prevent YOLO from auto-nesting
PROJECT_DIR = Path.cwd() / "runs"
# Fix 2: Generate independent folder with timestamp for each run (e.g., exp_0422_1933)
CURRENT_RUN_NAME = f"exp_{datetime.now().strftime('%m%d_%H%M')}"

# ══════════════════════════════════════════════════════════════════

def setup_logger() -> logging.Logger:
    logger = logging.getLogger("YOLOv8Train")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s  %(message)s", datefmt="%H:%M:%S")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    if not logger.handlers:
        logger.addHandler(sh)
    return logger

def find_latest_checkpoint(proj_dir: Path):
    """Automatically find the latest last.pt in all historical runs for resuming training."""
    if not proj_dir.exists():
        return None
    # Recursively search for all last.pt
    checkpoints = list(proj_dir.rglob("weights/last.pt"))
    if not checkpoints:
        return None
    # Sort by file's last modification time, take the latest one
    checkpoints.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return checkpoints[0]

def train(logger: logging.Logger):
    from ultralytics import YOLO

    yaml_file = Path.cwd() / YAML_PATH
    if not yaml_file.exists():
        logger.error(f"❌ Cannot find config file: {yaml_file}")
        sys.exit(1)

    # Automatically find resume checkpoint
    last_pt = find_latest_checkpoint(PROJECT_DIR)

    logger.info("=" * 60)
    logger.info("  YOLOv8 Indoor Obstacle Safety Training Started")
    logger.info(f"  Run Name : {CURRENT_RUN_NAME}")
    logger.info(f"  Resume   : {'✅ Interruption detected, preparing to resume' if last_pt else '🆕 New training round'}")
    logger.info("=" * 60)

    t0 = time.time()

    if last_pt:
        model = YOLO(str(last_pt))
        results = model.train(resume=True)
    else:
        model = YOLO(MODEL_WEIGHTS)
        results = model.train(
            data         = str(yaml_file),
            epochs       = EPOCHS,
            imgsz        = IMGSZ,
            batch        = BATCH,
            device       = DEVICE,
            workers      = WORKERS,
            project      = str(PROJECT_DIR),   # Force absolute path
            name         = CURRENT_RUN_NAME,   # Use tagged name with timestamp
            exist_ok     = True,
            patience     = PATIENCE,
            fraction     = FRACTION,
            cache        = False,           
            amp          = True,
            mosaic       = 0.5,   
            plots        = True,
            save         = True,
            verbose      = True,
        )

    elapsed_minutes = (time.time() - t0) / 60

    # Core Fix: Grab the real save path directly from the model's underlying attributes
    save_dir = Path(model.trainer.save_dir)
    best_pt = save_dir / "weights" / "best.pt"

    # Print final report
    logger.info("\n" + "🌟" * 25)
    logger.info("       🚀 T R A I N I N G   S U M M A R Y")
    logger.info("🌟" * 25)
    logger.info(f"⏱️ Total Time    : {elapsed_minutes:.1f} minutes")
    logger.info(f"📁 Run Tag       : {save_dir.name}")
    
    if best_pt.exists():
        logger.info(f"🧠 Best Weights  : {best_pt.resolve()}")
    else:
        logger.error("❌ best.pt not found, the model might not have made effective improvements.")

    # Print performance metrics
    try:
        if hasattr(results, 'box'):
            logger.info(f"🎯 mAP50         : {results.box.map50:.4f}")
            logger.info(f"🎯 mAP50-95      : {results.box.map:.4f}")
    except Exception:
        pass
        
    logger.info("🌟" * 25 + "\n")

def main():
    try:
        import ultralytics
    except ImportError:
        print("Error: ultralytics is not installed. Please run `pip install ultralytics`")
        sys.exit(1)

    logger = setup_logger()
    
    import torch
    if not torch.cuda.is_available():
        logger.error("CUDA is not available, please check your PyTorch installation!")
        sys.exit(1)
        
    torch.cuda.empty_cache()
    train(logger)

if __name__ == "__main__":
    main()