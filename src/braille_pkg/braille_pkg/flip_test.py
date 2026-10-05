#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import rclpy
import DR_init
import time

# ========================================
# 로봇 설정 및 전역 변수
# ========================================
ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"
ROBOT_TOOL = "Tool Weight"
ROBOT_TCP = "GripperDA"  # 현재 사용 중인 TCP 이름 확인 필요

DR_init.__dsr__id = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL

# 동작 속도 / 가속도
VELJ, ACCJ = 50.0, 50.0   # 관절(홈) 이동
VELX, ACCX = 50.0, 50.0   # 일반 직선 이동
VELX_SLOW, ACCX_SLOW = 50.0, 50.0 # 정밀 접근 직선 이동

def initialize_robot():
    """로봇의 Tool과 TCP 및 초기 모드를 설정"""
    from DSR_ROBOT2 import set_tool, set_tcp, release_force, release_compliance_ctrl, set_robot_mode, ROBOT_MODE_AUTONOMOUS
    try:
        set_robot_mode(ROBOT_MODE_AUTONOMOUS)
        release_force(time=0.0)
        release_compliance_ctrl()
    except Exception:
        pass
    
    set_tool(ROBOT_TOOL)
    set_tcp(ROBOT_TCP)

def grip_open():
    from DSR_ROBOT2 import set_digital_output, wait
    set_digital_output(1, 0)
    set_digital_output(2, 1)
    wait(1.0)

def grip_close():
    from DSR_ROBOT2 import set_digital_output, wait
    set_digital_output(1, 1)
    set_digital_output(2, 0)
    wait(1.0)

def main(args=None):
    rclpy.init(args=args)
    node = rclpy.create_node("flip_test_node", namespace=ROBOT_ID)
    DR_init.__dsr__node = node

    # ⭐️ movesx 제거하고 movel만 임포트
    from DSR_ROBOT2 import movej, movel, wait
    from DR_common2 import posx, posj

    # 1. 위치 정의
    Q1 = posj([0.0, 25.0, 60.0, 0.0, 94.5, 0.0])
    
    # [진입 및 빠져나오는 'ㄷ'자 경로 좌표]
    p1 = posx([422.25, 230.0,   200.0,  164.4, 179.89, 164.24])
    p2 = posx([422.25, 230.0,   99.1,   90.0, -90.0,   -0.1])
    p3 = posx([422.25, 145.53,  99.15,  90.1, -90.0,   -0.1])
    
    # [들고 뒤집고 내리는 위치 좌표]
    pos_lift = posx([422.25, 145.53, 300.0, 90.1, -90.0, -0.1])
    pos_rot  = posx([422.25, 145.53, 300.0, 90.1, -90.0, 180.0])
    pos_down = posx([422.25, 145.53,  99.15, 90.1, -90.0, 180.0])

    try:
        # 하드웨어 초기화
        initialize_robot()
        grip_open()

        node.get_logger().info("1. 초기 대기 위치(Q1)로 이동")
        movej(Q1, vel=VELJ, acc=ACCJ)


        # ========================================
        # [1단계] 'ㄷ'자 궤적으로 진입 (movel 연속 사용)
        # ========================================
        node.get_logger().info("2. 'ㄷ'자 궤적으로 종이 잡는 위치로 접근 (movel)")
        
        node.get_logger().info(" -> p1 위치로 이동")
        movel(p1, vel=VELX, acc=ACCX)
        
        node.get_logger().info(" -> p2 위치로 이동")
        movel(p2, vel=VELX, acc=ACCX)
        
        node.get_logger().info(" -> p3 위치로 이동 (잡기 위치)")
        movel(p3, vel=VELX_SLOW, acc=ACCX_SLOW) # 종이에 닿기 직전은 살짝 느리게
        
        node.get_logger().info("-> 종이 잡기")
        grip_close()

        # ========================================
        # [2단계] 종이 들고 180도 회전
        # ========================================
        node.get_logger().info("3. 종이 들기 (movel: Z=300)")
        movel(pos_lift, vel=VELX, acc=ACCX)
        
        node.get_logger().info("4. 공중에서 180도 뒤집기 (movel: Rz=180)")
        movel(pos_rot, vel=VELX, acc=ACCX)
        wait(0.5)

        # ========================================
        # [3단계] 내려놓기 및 역순 복귀 (movel 연속 사용)
        # ========================================
        node.get_logger().info("5. 뒤집은 상태로 내려놓기 (movel: Z=99.15)")
        movel(pos_down, vel=VELX_SLOW, acc=ACCX_SLOW) # 내려놓을 때도 살짝 느리게

        node.get_logger().info("-> 종이 놓기")
        grip_open()
        
        node.get_logger().info("6. 'ㄷ'자 궤적으로 빠져나와 홈 복귀 (movel 역순)")
        
        # 꼬였던 팔을 풀기 위해 p2 -> p1 순서로 되돌아감
        node.get_logger().info(" -> p2 위치로 후퇴")
        movel(p2, vel=VELX, acc=ACCX)
        
        node.get_logger().info(" -> p1 위치로 후퇴")
        movel(p1, vel=VELX, acc=ACCX)
        
        node.get_logger().info("7. 홈(Q1)으로 최종 복귀")
        movej(Q1, vel=VELJ, acc=ACCJ)

        node.get_logger().info("✅ 종이 뒤집기 테스트 완료!")

    except KeyboardInterrupt:
        print("\n사용자에 의해 테스트가 중단되었습니다.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        node.get_logger().error(f"테스트 중 에러 발생: {e}")
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()