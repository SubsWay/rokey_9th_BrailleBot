#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
로봇 공정 통합 Launch 파일
- 마스터 노드를 가장 먼저 실행한 후, 제어 노드들을 지연 실행
"""

from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import TimerAction


def generate_launch_description():
    """Launch 설명 생성"""

    '''# 1. 마스터 노드 (가장 먼저 실행되어 통신망 총괄 대기)
    master_node = Node(
        package='braille_pkg',
        executable='master',
        name='master_node',
        output='screen',
        emulate_tty=True,
    )'''

    # 2. 글쓰기 제어 노드 (마스터 시작 2초 후 실행)
    write_node = TimerAction(
        period=2.0,
        actions=[
            Node(
                package='braille_pkg',
                executable='writed',
                name='write_node',
                namespace='dsr01',
                output='screen',
                emulate_tty=True,
            )
        ]
    )

    # 3. 점자 타각 제어 노드 (마스터 시작 4초 후 실행)
    braille_node = TimerAction(
        period=4.0,
        actions=[
            Node(
                package='braille_pkg',
                executable='braille',
                name='braille_node',
                namespace='dsr01',
                output='screen',
                emulate_tty=True,
            )
        ]
    )

    return LaunchDescription([
        #master_node,
        write_node,
        braille_node,
    ])
