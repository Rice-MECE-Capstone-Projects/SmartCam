import os
from ament_index_python.packages import get_package_share_directory

from launch_ros.actions import Node
from launch.conditions import IfCondition
from launch import LaunchDescription, LaunchService
from launch.substitutions import Command, LaunchConfiguration, FindExecutable
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.parameter_descriptions import ParameterValue

def _pkg_exists(name: str) -> bool:
    try:
        get_package_share_directory(name)
        return True
    except Exception:
        return False

def generate_launch_description():
    # 环境变量不再强依赖，避免 KeyError
    # compiled = os.getenv('need_compile', 'False')

    use_gui = LaunchConfiguration('use_gui', default='false')   # 默认关闭 GUI，避免未安装时报错
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

    share = get_package_share_directory('simulator')
    urdf_path = os.path.join(share, 'urdf', 'mentorpi.xacro')
    rviz_config_file = os.path.join(share, 'rviz', 'view.rviz')

    robot_description = ParameterValue(
        Command(['xacro ', urdf_path]),
        value_type=str
    )

    # Joint State Publisher（无 ros2_control 时可视化/拖拽）
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

    # 仅在包存在时才创建 GUI 节点
    nodes = [
        use_gui_arg, use_rviz_arg, frame_prefix_arg, use_sim_time_arg, namespace_arg, use_namespace_arg,
        joint_state_publisher_node
    ]

    if _pkg_exists('joint_state_publisher_gui'):
        nodes.append(
            Node(
                package='joint_state_publisher_gui',
                executable='joint_state_publisher_gui',
                name='joint_state_publisher_gui',
                output='screen',
                condition=IfCondition(use_gui),
                remappings=[('/joint_states', 'joint_controller')]
            )
        )

    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        name='robot_state_publisher',
        parameters=[{
            'robot_description': robot_description,
            'frame_prefix': frame_prefix,
            'use_sim_time': use_sim_time
        }],
    )
    nodes.append(robot_state_publisher_node)

    rviz_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(share, 'launch', 'rviz.launch.py')),
        condition=IfCondition(use_rviz),
        launch_arguments={
            'namespace': namespace,
            'use_namespace': use_namespace,
            'rviz_config': rviz_config_file
        }.items()
    )
    nodes.append(rviz_launch)

    return LaunchDescription(nodes)

if __name__ == '__main__':
    ld = generate_launch_description()
    ls = LaunchService()
    ls.include_launch_description(ld)
    ls.run()

