from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'braille_pkg'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='rokey',
    maintainer_email='omver5669@gmail.com',
    description='TODO: Package description',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'test = braille_pkg.gripper_test:main',
            'force = braille_pkg.force_test:main',
            'write = braille_pkg.test:main',
            'brai = braille_pkg.brill_test:main',
            'master = braille_pkg.master_node:main',
            'writed = braille_pkg.write_node:main',
            'braille = braille_pkg.braille_node:main',
            'control = braille_pkg.robot_control:main',
            'flip = braille_pkg.flip_test:main',
            'dozang = braille_pkg.dozang:main',
            'master_DB=braille_pkg.master_node_DB:main'

        ],
    },
)
