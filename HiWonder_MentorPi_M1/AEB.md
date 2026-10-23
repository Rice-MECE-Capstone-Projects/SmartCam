# Automatic Emergency Braking

This project implements an **Autonomous Emergency Braking (AEB)** system on a HiWonder MentorPi M1 (Mecanum) robot. It uses a hybrid architecture to bridge high-frequency ultrasonic sensor data from the host OS (Raspberry Pi 5) into a ROS 2 Humble Docker container for safety-critical teleoperation.

## 🏗 System Architecture

The project is divided into two primary layers to handle the Raspberry Pi 5's hardware architecture efficiently:

1.  **Host Layer (Debian):** Directly accesses the RP1 chip via the `lgpio` library to measure distance from the HC-SR04 ultrasonic sensor. It broadcasts this data over a local UDP socket.
2.  **Docker Layer (ROS 2 Humble):** A containerized environment running the robot's control stack. A safety node listens for UDP packets and overrides teleoperation commands (AEB) if an obstacle is detected within 20cm.

---

## 🛠 Setup Instructions

### Phase 1: Host Side Setup (Data Collection)
The Raspberry Pi 5 requires specific libraries to interact with the new GPIO registers.

```bash
# Install dependencies
sudo apt update && sudo apt install -y python3-pip libgpiod-dev python3-lgpio
pip3 install rpi-lgpio

# Run the socket bridge
python3 SmartCam/HiWonder_MentorPi_M1/host/socket_ultra_data.py
```

### Phase 2: Docker Side: ROS 2 Safety Controller
To avoid "Environment Poisoning" (mixing ROS 1 Noetic and ROS 2 Humble), ensure our container is built correctly.

```bash
# Clean Workspace
cd ~/ros2_ws
rm -rf build/ install/ log/

# Build
source /opt/ros/humble/setup.zsh
colcon build --symlink-install
source install/setup.zsh
```

### Phase 3: Running the System
```bash
# Run the chassis
ros2 launch controller controller.launch.py

# Run the teleoperation control with AEB stopping feature
ros2 run teleop_ctrl tele_ultra
```

### AEB Logic
Safe Zone: Distance > 20cm. Keyboard teleop works normally.

Danger Zone: Distance ≤ 20cm. The tele_ultra node intercepts the signal and publishes 0.0 velocity, stopping the car immediately even if keys are pressed.
