from setuptools import find_packages, setup

package_name = 'teleop_ctrl'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', [
            'launch/teleop_ctrl.launch.py',
        ]),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='wentao',
    maintainer_email='93648557+wentaoj@users.noreply.github.com',
    description='TODO: Package description',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'teleop_ctrl = teleop_ctrl.teleop_ctrl:main',
	    'teleop_ultra = teleop_ctrl.tele_uta_data:main'
        ],
    },
)
