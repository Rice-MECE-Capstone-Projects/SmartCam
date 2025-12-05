# ROS 2 Leader Car & SLAM Setup

This documentation outlines the steps to build the workspace, run the leader car controller, and perform LiDAR-based SLAM.

## 1. Build and Install
Run these commands inside the `ros2_ws` directory to build the packages and source the environment.

```zsh
# Build the workspace with symlink installation
colcon build --symlink-install

# To run the leader car run below commands in the terminal
ros2 launch controller controller.launch.py
ros2 run teleop_ctrl teleop_ctrl	# Control the robot with the help of keyboard keys as instructed in the same terminal

# Source the overlay (using ZSH)
source install/setup.zsh

# To run LiDAR based SLAM, follow the commands in the terminal
sudo apt install ros-humble-toolbox		# to install SLAM toolbox
ros2 launch slam slam.launch.py			# to launch slam file
ros2 launch slam rviz_slam.launch 		# to visualize the slam map in rviz2
