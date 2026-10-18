# SmartCam AutoTeacher Loop v1.0（学校电脑 Gazebo Classic）

**目的**：复用已经在学校电脑验证过的 `~/smartcam_vla/SmartCam_Midterm_Demo/scripts/color_demo.py` 视觉教师控制器，自动重置 Gazebo 场景、启动 ROS Bag、执行规则控制、发送停车指令、关闭录制并审核动作。然后将 **人工核实过任务结果** 的轨迹转换为 LeRobot 0.6.1，准备微调 SmolVLA 的二维速度动作 `[v, omega]`。

**边界**：仅用于 Gazebo Classic `my_bot` 的仿真；需要确认没有实体机器人连接在同一个 ROS Domain。每条实验**需要人工输入 `DRIVE` 授权**。这不是 VLA 在线训练；脚本绝不会把未验证轨迹自动当作成功、自动启动 GPU 微调，也不包含学习型策略的闭环驾驶。

## A. 前提（已在学校电脑验证过）

- Ubuntu 22.04、ROS2 Humble、Gazebo Classic `gzserver`，现有 `articubot_one` `my_bot`；
- `~/smartcam_vla/SmartCam_Midterm_Demo/demo.sh` 与 `scripts/color_demo.py` 存在；
- `/camera/image_raw`、`/diff_cont/odom`、`/cmd_vel`、`/scan`、`/clock` 正常；
- 若 `/diff_cont/cmd_vel_unstamped` 存在，也会录制用于控制链诊断；
- 用于训练/转换的独立 Conda `smartcam_smolvla` 和 `lerobot==0.6.1`（不是 ROS2 的 `/usr/bin/python3`）。

**不要同时运行**任何人工 teleop、其他 VLA 控制器或 RL 控制器向同一机器人发送速度命令。先启动已有 Gazebo 仿真，再运行以下指令。不要启动第二个 `gzserver`。

## B. 安装与只读检查

将 ZIP 下载到学校电脑的 `~/Downloads`。

```bash
unzip -n ~/Downloads/SmartCam_AutoTeacher_Loop.zip -d ~/smartcam_vla/
cd ~/smartcam_vla/SmartCam_AutoTeacher_Loop
./auto_teacher.sh check
```

若没有 Gazebo 运行，在其他终端先启动（保留启动窗口）：

```bash
cd ~/smartcam_vla/SmartCam_Midterm_Demo
./demo.sh gazebo
```

`check` 只检查 Gazebo Classic、`my_bot`、必要 ROS Topic、`/clock` 和是否有已知竞争控制节点；不会重置世界、运动或录制。

## C. 一条命令完成自动教师驾驶 + ROS Bag + 动作审核

```bash
cd ~/smartcam_vla/SmartCam_AutoTeacher_Loop
./auto_teacher.sh collect --scene B --target blue --episode B_blue_auto_001 --duration 55
```

按提示人工检查 Gazebo 目标与第一视角、确保这是仿真且没有其他控制源，再输入 `DRIVE`。**程序自动完成**：

1. 执行 `demo.sh scene B` 并重置 `my_bot`，红蓝方块固定 Scene B 坐标；
2. 采集开始前监听 `/clock`，执行 `ros2 bag record --use-sim-time`；
3. 自动运行原有教师 `color_demo.py --target blue --drive --duration 55`，不需要 W/A/S/D 键盘驾驶；
4. 教师视觉转向 + 前进 + LiDAR 安全停/时间停，结束后显式发送零速度；
5. 正常关闭 rosbag，保存语言/场景元数据，运行只读的 ROS Bag 动作分析；
6. 给 Episode `outcome=unknown`，**等你人工审核任务是否真的到达目标且主动停车**。

如果意外运动：立即暂停 Gazebo；`Ctrl+C` 也会尝试中止教师并发布零速度。**暂停仿真是安全兜底，不能用于真实机器人。**

默认写到：

```
~/smartcam_vla/datasets/rosbags/B_blue_auto_001/
  metadata.yaml
  B_blue_auto_001_0.db3
~/smartcam_vla/datasets/rosbags/B_blue_auto_001.manifest.json
~/smartcam_vla/datasets/rosbags/B_blue_auto_001.teacher.log
~/smartcam_vla/datasets/rosbags/B_blue_auto_001.recorder.log
~/smartcam_vla/datasets/reports/B_blue_auto_001_audit.json
```

没有覆盖机制。换场景/目标时，使用唯一 Episode ID：

```
./auto_teacher.sh collect --scene A --target red  --episode A_red_auto_001  --duration 55
./auto_teacher.sh collect --scene A --target blue --episode A_blue_auto_001 --duration 55
./auto_teacher.sh collect --scene B --target red  --episode B_red_auto_001  --duration 55
./auto_teacher.sh collect --scene B --target blue --episode B_blue_auto_002 --duration 55
```

上面每次都要重新授权；**每条轨迹重置同一个位置，不能仅凭重复采样说明模型可泛化**。之后还需要不同起点/布局、正向和反向动作、人工核实的到达停车。

## D. 审核、标注、导出训练样本

**ROS 系统终端**：

```bash
cd ~/smartcam_vla/SmartCam_AutoTeacher_Loop
BAG="$HOME/smartcam_vla/datasets/rosbags/B_blue_auto_001"
./auto_teacher.sh audit --bag "$BAG"
```

主要看 `forward` 是否大于零、转向是否正确、相机和里程计是否有数据，不能只看 ROS Topic 消息数量。

**是否成功必须人工确定**：当前 `color_demo.py` 可能只是因为 55 秒到期或前方 LiDAR 小于 0.72m 而停止。这不等于真的到蓝色目标且主动停车。证据不足时：

```bash
./auto_teacher.sh label --bag "$BAG" --outcome partial --notes 'Observed alignment and approach, but verified target arrival is missing.'
```

若录像、Gazebo 末位姿、目标距离与日志共同证明任务完成，才可以：

```bash
./auto_teacher.sh label --bag "$BAG" --outcome success --notes 'Verified robot reached designated target and stopped under defined goal condition.'
```

程序会再要求输入 `VERIFIED`。不要为了训练集条数伪造成功标签。

导出 10Hz 图像+状态+动作：

```bash
./auto_teacher.sh export --bag "$BAG" --fps 10 --max-frames 800
```

生成 `~/smartcam_vla/datasets/raw/B_blue_auto_001/metadata.json`、`samples.csv` 和 `rgb/*.png`。转换器以 ROS Bag **仿真接收时间**做对齐；运动控制受感知处理延迟影响，请检查图像时间戳和动作标签对应性。导出默认不覆盖。

## E. 数据送入模型：LeRobot 离线数据集 → SmolVLA 微调

**新开 Conda 终端**（不要在这个终端 `source /opt/ros/humble/setup.bash`）：

```bash
source ~/miniforge3/etc/profile.d/conda.sh
conda activate smartcam_smolvla
unset PYTHONPATH
export PYTHONNOUSERSITE=1
cd ~/smartcam_vla/SmartCam_AutoTeacher_Loop
./auto_teacher.sh model env
```

正式数据转换默认**只包含 `split=train` 且 `outcome=success`** 的轨迹：

```bash
./auto_teacher.sh convert \
  --raw-root "$HOME/smartcam_vla/datasets/raw" \
  --output "$HOME/smartcam_vla/datasets/lerobot/velocity_train_v1" \
  --repo-id smartcam/velocity_train_v1
```

如果只是**验证代码流程**，可选 `--include-partial`，但这样生成的数据不能代表成功任务数据，也不能用于报告成功导航率。完整训练建议至少有多个场景、多起点、多次人工验证的成功轨迹，并且训练/验证/测试划分按整条 Episode 分开。

准备 SmolVLA 二维动作配置：

```bash
./auto_teacher.sh model prepare \
  --dataset-root "$HOME/smartcam_vla/datasets/lerobot/velocity_train_v1" \
  --repo-id smartcam/velocity_train_v1 \
  --output "$HOME/smartcam_vla/plans/smolvla_auto_001" \
  --training-only --steps 100
```

打印训练命令（不执行）：

```bash
./auto_teacher.sh model train --plan "$HOME/smartcam_vla/plans/smolvla_auto_001/plan.json"
```

经过数据集审核、磁盘空间和 GPU 显存检查之后，再单独运行：

```bash
./auto_teacher.sh model train --plan "$HOME/smartcam_vla/plans/smolvla_auto_001/plan.json" --execute
```

模型默认来自 Hugging Face `lerobot/smolvla_base`（如本机没有缓存则需要联网下载）。RTX 3070 8GiB **不保证** SmolVLA 微调能成功，即使 batch=1；OOM 时应停下来调整资源/模型策略，不要混用 ROS Python 与 Conda 环境。100 步只验证训练链路，不代表学会导航。必须保存真实 checkpoint，再用 `model verify` 在未见轨迹上验证。

## F. “反馈给模型”的正确闭环

```
rule-based Teacher in Gazebo  -> ROS Bag + task & outcome
  -> timestamp audit -> LeRobot Dataset -> SmolVLA fine-tuning
  -> OFFLINE action evaluation -> SHADOW predictions (no driving)
  -> [future] Gazebo model drives within independent LiDAR safety layer
  -> collect failures and human/teacher corrections -> retrain (DAgger-style)
```

**本包实现了**“教师自动跑 + 录制 + 审核 + 导出 + 本地 LeRobot 转换 + 训练命令”；
**没有实现**不受监管的自动驾驶、真实机器人部署、模型实时在线权重更新、DAgger 干预控制或训练完成后的性能保证。你可以先用一条试验数据把 pipeline 走通，明天展示时讲清楚完成的层级。

## G. 质量验证与常见问题

```bash
python3 -m unittest discover -s tests -v
```

若只看到 `/clock` 没有 `/camera/image_raw`，说明 Gazebo World 或 ROS Domain 不匹配。**不要启动第二个 Gazebo**。

如果 ROS Bag 里 `/cmd_vel` 大部分为零，看看 `*.teacher.log` 有没有 `APPROACH TARGET`、Bag audit 里 `forward` 是否大于零；也应对比 `/diff_cont/cmd_vel_unstamped` 以诊断 mux。注意 `cmd_vel` 是请求动作，不代表底盘准确执行，执行状态来自 `/diff_cont/odom`。

**验证状态**：本文件包可在当前容器环境测试 Python 语法、包内容、纯函数，不能连接你的学校 Gazebo ROS 网络。需要先在学校电脑运行一次真实 `collect` 并看 `audit` 输出后再称为工作流验证。
