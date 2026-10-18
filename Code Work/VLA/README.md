# SmartCam VLA Development

Rice University - ELEC 594 Capstone
Fall 2026

## Objective

Investigate lightweight Vision-Language-Action
models for autonomous robot navigation using
ROS 2, Gazebo, and MentorPi.

## Components

- Simulation: Gazebo and ROS 2 navigation baseline
- AutoTeacher: Rule-based demonstration collection
- Training: SmolVLA fine-tuning
- Inference: Offline and shadow-mode evaluation
- Evaluation: Teacher vs. SmolVLA benchmarks

## Current Progress

- ROS 2 / Gazebo simulation validated
- Automatic demonstration collection completed
- LeRobot dataset conversion tested
- SmolVLA 100-step BF16 training completed
- Checkpoint loading verified
- Offline action prediction tested

## Limitations

Results are preliminary and based on limited
simulation data.

The current dataset contains one partial episode.
Navigation success and generalization have not
been demonstrated.

Model weights and raw datasets are not stored
in this Git repository.

## Safety

Current development is simulation-focused.
Physical MentorPi control requires independent
safety validation.

## Status

Development in progress - October 2026.
