import rclpy
from rclpy.node import Node
import DR_init
import time

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"
ROBOT_TOOL = "Tool Weight"
ROBOT_TCP = "GripperDA_v1"

DR_init.__dsr__id = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL

# 테스트용 점자 데이터 (1: 타각, 0: 통과)
BRAILLE_DATA = [
    [1, 0, 0, 1, 0, 0], 
    [0, 1, 0, 0, 1, 0], 
    [0, 0, 1, 0, 0, 1], 
    [1, 0, 0, 0, 1, 0],
    [0, 0 ,0 ,0 ,0 ,0],
    [1, 0, 0, 0, 0, 1],
    [0, 1, 0 ,1 ,0 ,0],
    [0, 1, 0, 0, 0, 1]
]

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
    print("로봇 Tool/TCP 초기화 완료")

def calculate_braille_start_position(braille_len, braille_offset=5.5):
    """종이의 중앙 좌표를 계산하여 점자 시작 위치를 반환합니다."""
    x_center = (281.0 + 566.0) / 2.0  
    y_max = 97.0                      
    
    braille_cell_width = 2.5
    braille_width = (braille_len - 1) * braille_offset + braille_cell_width if braille_len > 0 else 0.0
    braille_start_x = x_center - (braille_width / 2.0)
    
    lowest_text_y = y_max - 20.0
    braille_start_y = lowest_text_y - 20.0
    
    return braille_start_x, braille_start_y

def main(args=None):
    rclpy.init(args=args)
    node = rclpy.create_node("braille_test_node", namespace=ROBOT_ID)
    DR_init.__dsr__node = node

    # 양식에 맞추어 set_stiffnessx, get_tool_force 추가 임포트
    from DSR_ROBOT2 import (wait, movej, movel, DR_TOOL, DR_BASE, set_digital_output,
                            set_ref_coord, task_compliance_ctrl, set_desired_force, DR_FC_MOD_REL,
                            release_force, release_compliance_ctrl, check_force_condition, DR_AXIS_Z,
                            get_current_posx, DR_MV_MOD_REL, set_stiffnessx, get_tool_force)
    from DR_common2 import posx, posj

    # 속도 및 가속도 설정
    MOVEJ_VEL, MOVEJ_ACC = 200.0, 200.0
    MOVE_VEL, MOVE_ACC = 100.0, 100.0
    Z_VEL, Z_ACC = 20.0, 20.0 
    
    # 수정: 요청하신 점자 타각 힘 2.0N
    PUNCH_FORCE = 15.0 
    CHAR_OFFSET = 5.5
    EPS = 1e-3

    try:
        initialize_robot()
        
        Q1 = posj([0.0, 25.0, 55.0, 0.0, 100.0, 0.0])
        
        # 1. 툴 픽업 좌표
        pos_tool_above = posx([494.0, -183.5, 242.5, 0.0, 180.0, 0.0])
        pos_tool_pick  = posx([494.0, -183.5, 95.0,  0.0, 180.0, 0.0])
        pos_tool_drop  = posx([494.0, -183.5, 105.0, 0.0, 180.0, 0.0])

        # 2. 이쑤시개 픽업하러 가기
        set_digital_output(1, 0); set_digital_output(2, 1) # 그리퍼 열기
        node.get_logger().info("점자 툴(이쑤시개) 픽업 중...")
        
        movej(Q1, vel=MOVEJ_VEL, acc=MOVEJ_ACC)
        movel(pos_tool_above, vel=MOVEJ_VEL, acc=MOVEJ_ACC, ref=DR_BASE)
        movel(pos_tool_pick, vel=Z_VEL, acc=Z_ACC, ref=DR_BASE)
        
        set_digital_output(1, 1); set_digital_output(2, 0) # 그리퍼 닫기
        wait(1.0)
        
        # 안전 높이로 복귀
        movel(pos_tool_above, vel=MOVEJ_VEL, acc=MOVEJ_ACC, ref=DR_BASE)

        # 3. 점자 시작 좌표 계산 및 이동
        num_chars = len(BRAILLE_DATA)
        target_x, target_y = calculate_braille_start_position(num_chars, braille_offset=CHAR_OFFSET)
        
        # 안전 높이(242.5)를 유지하며 타각 위치로 이동
        pos_braille_start = posx([target_x, target_y, 242.5, 0.0, 180.0, 0.0])
        node.get_logger().info(f"타각 시작 위치로 이동 완료 (X: {target_x:.2f}, Y: {target_y:.2f})")
        movel(pos_braille_start, vel=MOVEJ_VEL, acc=MOVEJ_ACC, ref=DR_BASE)
        
        # 도구 길이 등을 보정하기 위해 Z축 방향으로 기본 접근
        movel(posx([0.0, 0.0, 40.5, 0.0, 0.0, 0.0]), vel=Z_VEL, acc=Z_ACC, ref=DR_TOOL, mod=DR_MV_MOD_REL)

        # ==========================================
        # 상대 이동 및 도장과 동일한 힘 제어 펀치 함수
        # ==========================================
        def move_rel(dx, dy, v=MOVE_VEL, a=MOVE_ACC):
            if abs(dx) < EPS and abs(dy) < EPS: return
            movel(posx([-dx, -dy, 0.0, 0.0, 0.0, 0.0]), vel=v, acc=a, ref=DR_TOOL, mod=DR_MV_MOD_REL)

        def punch_dot():
            safe_pos = get_current_posx(ref=DR_BASE)[0]
            try:
                # 1. 컴플라이언스 켜기 (유연한 상태로 진입 준비)
                set_ref_coord(DR_TOOL)
                task_compliance_ctrl()
                set_stiffnessx([3000.0, 3000.0, 500.0, 100.0, 100.0, 200.0])
                
                # 2. 컴플라이언스 켜진 상태로 하강 (충격 흡수)
                movel(posx([0.0, 0.0, 10.0, 0.0, 0.0, 0.0]), vel=Z_VEL, acc=Z_ACC, ref=DR_TOOL, mod=DR_MV_MOD_REL)
                
                # 3. 목표 힘(10.0N) 인가
                set_desired_force([0.0, 0.0, PUNCH_FORCE, 0.0, 0.0, 0.0], dir=[0, 0, 1, 0, 0, 0], mod=1)
                
                # 4. 힘 감지 루프 시작 (목표 8  .0N)
                target_force = 15 * 0.8
                force_check_count = 0
                start_time = time.time()
                
                while True:
                    current_force = get_tool_force()
                    force_check_count += 1
                    
                    # 로그가 너무 많아지는 것을 방지하기 위해 10주기마다 출력
                    if force_check_count % 10 == 0:
                        print(f"[FORCE 점자] Fx={current_force[0]:.2f}, Fy={current_force[1]:.2f}, Fz={current_force[2]:.2f}")
                        
                    # 감지 기준인 min=1.0N 도달 여부 체크
                    if not check_force_condition(DR_AXIS_Z, min=target_force, ref=DR_TOOL):
                        print(f"[FORCE 점자] 타각 접촉 감지! Fz={current_force[2]:.2f}N")
                        break
                        
                    # 점자는 타각 횟수가 많으므로 타임아웃을 3초로 짧게 설정
                    if time.time() - start_time > 3.0:
                        print("[ERROR] 점자 타각 타임아웃!")
                        break
                    time.sleep(0.05)
                
                # 확실한 타각을 위해 0.5초 뜸 들이기
                wait(0.5)

            finally:
                # 5. 힘 제어 해제 및 안전 높이로 복귀
                release_force(time=0.0)
                release_compliance_ctrl()
                set_ref_coord(DR_BASE)
                movel(safe_pos, vel=Z_VEL, acc=Z_ACC, ref=DR_BASE)
                print("--- 다음 점자로 이동 ---")

        # ==========================================
        # 점자 출력 실행
        # ==========================================
        node.get_logger().info(f"점자 테스트 시작! (총 {num_chars}글자)")
        for i, bits in enumerate(BRAILLE_DATA):
            char_cur_x, char_cur_y = 0.0, 0.0
            
            for j, val in enumerate(bits):
                if val == 1:
                    target_x_char, target_y_char = (j // 3) * 2.5, (j % 3) * 2.5
                    dx, dy = target_x_char - char_cur_x, target_y_char - char_cur_y
                    
                    move_rel(dx, dy)
                    punch_dot() 
                    char_cur_x, char_cur_y = target_x_char, target_y_char
                    
            if i != num_chars - 1:
                move_rel(CHAR_OFFSET - char_cur_x, -char_cur_y)

        # 4. 완료 후 툴 반납
        node.get_logger().info("점자 타각 완료, 툴 반납 중...")
        
        curr_pos = get_current_posx(ref=DR_BASE)[0]
        curr_pos[2] = 242.5
        movel(curr_pos, vel=Z_VEL, acc=Z_ACC, ref=DR_BASE)
        
        movel(pos_tool_above, vel=MOVEJ_VEL, acc=MOVEJ_ACC, ref=DR_BASE)
        movel(pos_tool_drop, vel=Z_VEL, acc=Z_ACC, ref=DR_BASE)
        
        set_digital_output(1, 0); set_digital_output(2, 1) # 그리퍼 열기 (내려놓기)
        wait(1.0)
        
        movel(pos_tool_above, vel=MOVEJ_VEL, acc=MOVEJ_ACC, ref=DR_BASE)
        movej(Q1, vel=MOVEJ_VEL, acc=MOVEJ_ACC)
        
        node.get_logger().info("✅ 점자 단독 테스트가 성공적으로 종료되었습니다.")

    except Exception as e:
        node.get_logger().error(f"테스트 중 에러 발생: {e}")
    finally:
        rclpy.shutdown()

if __name__ == "__main__":
    main()