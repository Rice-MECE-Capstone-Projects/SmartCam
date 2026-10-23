import os
from ament_index_python.packages import get_package_share_directory

from launch_ros.actions import Node
from launch.conditions import IfCondition
from launch import LaunchDescription, LaunchService
from launch.substitutions import Command, LaunchConfiguration
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.parameter_descriptions import ParameterValue

def generate_launch_description():
    # 更健壮：不要强依赖环境变量（避免 KeyError）
    # compiled = os.getenv('need_compile', 'False')

    use_gui = LaunchConfiguration('use_gui', default='true')
    use_rviz = LaunchConfiguration('use_rviz', default='true')
    namespace = LaunchConfiguration('namespace', default='')
    use_namespace = LaunchConfiguration('use_namespace', default='false')
    frame_prefix = LaunchConfiguration('frame_prefix', default='')
    use_sim_time = LaunchConfiguration('use_sim_time', default='true')

    use_gui_arg = DeclareLaunchArgument('use_gui', default_value=use_gui)
    use_rviz_arg = DeclareLaunchArgument('use_rviz', default_value=use_rviz)
    frame_prefix_arg = DeclareLaunchArgument('frame_prefix', default_value=frame_prefix)
    use_sim_time_arg = DeclareLaunchArgument('use_sim_time', default_value=use_sim_time)
    namespace_arg = DeclareLaunchArgument('namespace', default_value=namespace)
    use_namespace_arg = DeclareLaunchArgument('use_namespace', default_value=use_namespace)

    # 始终从已安装（或 symlink-install）路径拿资源
    simulator_share = get_package_share_directory('simulator')
    urdf_path = os.path.join(simulator_share, 'urdf', 'mentorpi.xacro')
    rviz_config_file = os.path.join(simulator_share, 'rviz', 'view.rviz')

    robot_description = ParameterValue(
        Command(['xacro ', urdf_path]),
        value_type=str
    )

    # —— Joint State Publisher（仅用于可视化与手动拖关节）——
    # 如果你没有跑 ros2_control，这里可以不订阅 controller_manager 的 joint_states；
    # 简单起见保留你原来的设置：
    joint_state_publisher_node = Node(
        package='joint_state_publisher',
        executable='joint_state_publisher',
        name='joint_state_publisher',
        output='screen',
        parameters=[{
            'source_list': ['/controller_manager/joint_states'],
            'rate': 20.0
        }]
    )

    joint_state_publisher_gui_node = Node(
        package='joint_state_publisher_gui',
        executable='joint_state_publisher_gui',
        name='joint_state_publisher_gui',
        output='screen',
        condition=IfCondition(use_gui),
        remappings=[('/joint_states', 'joint_controller')]
    )

    # —— Robot State Publisher（把 TF 广播出去）——
    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description,
            'frame_prefix': frame_prefix,
            'use_sim_time': use_sim_time
        }],
        # ROS 2 中不需要把 urdf 路径作为命令行参数传给 RSP；去掉更干净
        # arguments=[urdf_path],
        # 保持默认 /tf /tf_static 即可；如果你确实需要 remap 再开启
        # remappings=[('/tf', 'tf'), ('/tf_static', 'tf_static')]
    )

    rviz_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(simulator_share, 'launch', 'rviz.launch.py')),
        condition=IfCondition(use_rviz),
        launch_arguments={
            'namespace': namespace,
            'use_namespace': use_namespace,
            'rviz_config': rviz_config_file
        }.items()
    )

    return LaunchDescription([
        use_gui_arg,
        use_rviz_arg,
        frame_prefix_arg,
        use_sim_time_arg,
        namespace_arg,
        use_namespace_arg,
        joint_state_publisher_node,
        robot_state_publisher_node,
        joint_state_publisher_gui_node,
        rviz_launch,
    ])

if __name__ == '__main__':
    ld = generate_launch_description()
    ls = LaunchService()
    ls.include_launch_description(ld)
    ls.run()

