import os
import shutil
import random
import cv2
import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt

# ==========================================
# 实验配置
# ==========================================
# 模式选择: 
# 'SANDBOX': 纯模拟，生成 0 字节测试文件
# 'REAL_SAMPLE': 从真实数据集中复制 10 组文件到沙盒进行实战演练 (推荐)
MODE = 'REAL_SAMPLE' 

# 正式数据集的根路径
REAL_DATA_ROOT = Path(r"C:\finalproject\smartcam\Indoor Obstacle.yolov8")
# 沙盒路径
SANDBOX_ROOT = Path.cwd() / "test_sandbox"
# 类别名称（对应 data.yaml）
CLASS_NAMES = ['chair', 'door', 'person', 'shelf', 'stair', 'table', 'wardrobe']
# ==========================================

def get_long_path(path_obj: Path) -> str:
    """解决 Windows 260 字符限制的路径包装"""
    path_str = str(path_obj.resolve())
    if os.name == 'nt' and not path_str.startswith("\\\\?\\"):
        return "\\\\?\\" + path_str
    return path_str

def prepare_real_samples():
    """从真实数据集中随机复制样本到沙盒，不改动原数据"""
    img_src = REAL_DATA_ROOT / "train" / "images"
    lbl_src = REAL_DATA_ROOT / "train" / "labels"
    
    img_dst = SANDBOX_ROOT / "images"
    lbl_dst = SANDBOX_ROOT / "labels"
    
    img_dst.mkdir(parents=True, exist_ok=True)
    lbl_dst.mkdir(parents=True, exist_ok=True)

    if not img_src.exists():
        print(f"❌ 错误: 找不到真实数据路径 {img_src}")
        return False

    all_images = [f for f in os.listdir(img_src) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    samples = random.sample(all_images, min(10, len(all_images)))

    print(f"🚚 正在从真实数据集复制 {len(samples)} 组样本到沙盒...")
    for img_name in samples:
        shutil.copy2(get_long_path(img_src / img_name), get_long_path(img_dst / img_name))
        lbl_name = Path(img_name).stem + ".txt"
        if (lbl_src / lbl_name).exists():
            shutil.copy2(get_long_path(lbl_src / lbl_name), get_long_path(lbl_dst / lbl_name))
    
    print("✅ 样本复制完成。")
    return True

def draw_yolo_labels(img_path, lbl_path, output_path):
    """读取图片和YOLO格式标签并绘制"""
    img = cv2.imread(get_long_path(img_path))
    if img is None: return
    
    h, w, _ = img.shape
    if not lbl_path.exists(): return

    with open(get_long_path(lbl_path), 'r') as f:
        lines = f.readlines()

    for line in lines:
        parts = line.strip().split()
        if len(parts) < 5: continue
        
        cls_id = int(parts[0])
        cx, cy, nw, nh = map(float, parts[1:])
        
        # 归一化坐标转像素坐标
        x1 = int((cx - nw/2) * w)
        y1 = int((cy - nh/2) * h)
        x2 = int((cx + nw/2) * w)
        y2 = int((cy + nh/2) * h)
        
        # 绘制矩形框
        color = (0, 255, 0) # 绿色
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        label_text = f"{CLASS_NAMES[cls_id] if cls_id < len(CLASS_NAMES) else cls_id}"
        cv2.putText(img, label_text, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    cv2.imwrite(get_long_path(output_path), img)

def visualize_results(count=3):
    """随机选取重命名后的结果进行可视化对齐验证"""
    img_dir = SANDBOX_ROOT / "images"
    lbl_dir = SANDBOX_ROOT / "labels"
    vis_dir = SANDBOX_ROOT / "visual_verification"
    vis_dir.mkdir(parents=True, exist_ok=True)
    
    images = [f for f in os.listdir(img_dir) if f.lower().endswith(('.jpg', '.jpeg'))]
    samples = random.sample(images, min(count, len(images)))
    
    print(f"\n🎨 正在生成 {len(samples)} 张可视化验证图...")
    for img_name in samples:
        img_path = img_dir / img_name
        lbl_path = lbl_dir / (img_path.stem + ".txt")
        out_path = vis_dir / f"check_{img_name}"
        draw_yolo_labels(img_path, lbl_path, out_path)
        print(f"  📍 验证图已生成: {out_path.name}")

def rename_sync_core(img_dir: Path, lbl_dir: Path, prefix: str):
    """核心同步重命名逻辑"""
    print(f"\n📦 正在执行同步重命名...")
    images = sorted([f for f in os.listdir(img_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
    
    mapping_log = ["| 原始文件名 | 新文件名 | 状态 |", "| :--- | :--- | :--- |"]
    for i, old_img_name in enumerate(images):
        old_img_path = img_dir / old_img_name
        new_base = f"{prefix}_{i:06d}"
        new_img_path = img_dir / f"{new_base}{old_img_path.suffix}"
        
        old_lbl_path = lbl_dir / (old_img_path.stem + ".txt")
        new_lbl_path = lbl_dir / f"{new_base}.txt"

        try:
            os.rename(get_long_path(old_img_path), get_long_path(new_img_path))
            status = "仅图片"
            if old_lbl_path.exists():
                os.rename(get_long_path(old_lbl_path), get_long_path(new_lbl_path))
                status = "✅ 已对齐"
            mapping_log.append(f"| {old_img_name} | {new_base} | {status} |")
        except Exception as e:
            print(f" ❌ 失败: {e}")

    (SANDBOX_ROOT / "mapping_report.md").write_text("\n".join(mapping_log), encoding="utf-8")

def main():
    if SANDBOX_ROOT.exists():
        shutil.rmtree(get_long_path(SANDBOX_ROOT), ignore_errors=True)
    
    if prepare_real_samples():
        rename_sync_core(SANDBOX_ROOT / "images", SANDBOX_ROOT / "labels", "test_sample")
        visualize_results(3)
        print(f"\n✨ 全部演练完成！")
        print(f"1. 映射表见: {SANDBOX_ROOT}/mapping_report.md")
        print(f"2. 可视化效果见: {SANDBOX_ROOT}/visual_verification/ (请点开图片查看框是否准确)")

if __name__ == "__main__":
    main()