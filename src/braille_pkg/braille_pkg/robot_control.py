import json
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Int32MultiArray, Bool
import DR_init
import time
from braille_pkg.device import Device
from braille_pkg.rg2 import RG
import threading
from braille_pkg.hangul_engine import HangulEngine

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"
ROBOT_TOOL = "Tool Weight"
ROBOT_TCP = "GripperDA_v1"

DR_init.__dsr__id = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL

# ==========================================
# [0] 하드웨어 전역 초기화 함수
# ==========================================
def initialize_robot():
    """로봇의 Tool과 TCP 및 초기 모드를 설정"""
    from DSR_ROBOT2 import set_tool, set_tcp, release_force, release_compliance_ctrl, set_robot_mode, ROBOT_MODE_AUTONOMOUS
    try:
        set_robot_mode(ROBOT_MODE_AUTONOMOUS)
        release_force(time=0.0)
        release_compliance_ctrl()
    except Exception:
        pass
    


# ==========================================
# [2] 글쓰기 작업
# ==========================================
class WriteTask:
    def __init__(self, movej_vel=200.0, movej_acc=200.0, draw_vel=50.0, draw_acc=50.0, z_vel=100.0, z_acc=100.0):
        self.MOVEJ_VEL = movej_vel
        self.MOVEJ_ACC = movej_acc
        self.DRAW_VEL = draw_vel
        self.DRAW_ACC = draw_acc
        self.Z_VEL = z_vel
        self.Z_ACC = z_acc
        self.EPS = 1e-3
        self.pen_state = "down"
        
        # 안전 제어를 위한 플래그
        self.is_running = False
        self.pen_dropped = False

        # OnRobot RG2 그리퍼 초기화
        # 주의: OnRobot Compute Box의 실제 IP로 변경해야 할 수 있습니다. (기본값: 192.168.1.1)
        self.cb_ip = '192.168.1.1' 
        self.dev = Device(Global_cbip=self.cb_ip)
        self.gripper = RG(self.dev)
        
        # t_index는 보통 단일 그리퍼일 경우 0을 사용합니다.
        self.t_index = 0



    def execute(self, data, logger):
        from DSR_ROBOT2 import (movej, movel, wait, DR_TOOL, DR_MV_MOD_REL, 
                                get_current_posx, DR_BASE, DR_QSTOP)
        from DR_common2 import posx, posj

        text = data.get("text", "")
        letter_size = float(data.get("size", 20.0))
        
        if letter_size == 15.0:
            letter_space = 18.0
        elif letter_size == 40.0:
            letter_space = 47.0
        else:
            letter_size = 20.0
            letter_space = 25.0
            
        self.LETTER_SIZE = letter_size
        self.LETTER_SPACE = letter_space

        
        success = False
        self.is_running = True
        self.pen_dropped = False

        # 통신 연결 확인
        if not self.gripper.isConnected(self.t_index):
            logger.error("RG2 그리퍼와 통신할 수 없습니다. IP 주소나 랜선 연결을 확인하세요.")
            return False

        # --- [모니터링 스레드: RG2 너비 및 그립 상태 감시] ---
        def monitor_grip():
            while self.is_running:
                try:
                    # 현재 너비(mm)와 파지 상태(True/False)를 가져옵니다.
                    current_width = self.gripper.get_width(self.t_index)
                    is_gripped = self.gripper.isGripped(self.t_index)
                    
                    # 이쑤시개(3mm)와 붓펜(10mm) 모두 20.0mm 이하로 닫히면 놓친 것으로 판단
                    # 또는 isGripped 센서가 False(놓침)로 변하면 즉시 정지
                    if current_width < 15.0 or not is_gripped: 
                        logger.error(f"[경고] 펜 놓침 감지! (현재 너비: {current_width:.1f}mm) 즉시 정지합니다.")
                        self.pen_dropped = True
                        print("펜 놓침 감지: 모션 강제 종료")
                        break
                except Exception as e:
                    pass
                time.sleep(0.1) # 0.1초마다 검사

        try:
            Q1 = posj([13.2, -5.7, 96.5, 0.0, 90.0, 13.4])
            
            # 1. 좌표 정의
            pos_pen_above = posx([323.75, -171.5, 250.0, 0.0, 180.0, 0.0])
            pos_pen_pick  = posx([323.75, -171.5, 152, 0.0, 180.0, 0.0])
            pos_pen_drop  = posx([323.75, -171.5, 170, 0.0, 180.0, 0.0])

            # 디지털 출력 대신 라이브러리로 그리퍼 열기 (100mm 너비로 열기, 힘 40N, 대기)
            self.gripper.move(self.t_index, twidth=50.0, tforce=40.0, fwait=True)
            
            # 2. 붓펜 잡으러 가기
            logger.info("픽업 위치로 이동 중...")
            movel(pos_pen_above, vel=self.MOVEJ_VEL, acc=self.MOVEJ_ACC, ref=DR_BASE)
            movel(pos_pen_pick, vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_BASE)
            
            # 그리퍼로 펜 잡기 (목표 너비 0mm로 세팅하면 펜(3mm/10mm)을 만날 때까지 닫힙니다)
            # fwait=True 로 설정하여 파지가 끝날 때까지 코드가 대기합니다.
            self.gripper.grip(self.t_index, twidth=0.0, tforce=40.0, fwait=True)
            
            # 안전 높이로 복귀
            movel(pos_pen_above, vel=self.MOVEJ_VEL, acc=self.MOVEJ_ACC, ref=DR_BASE)

            # --- [모니터링 스레드 시작] ---
            # 허공으로 올라온 시점부터 펜을 떨어뜨리는지 감시 시작
            monitor_thread = threading.Thread(target=monitor_grip)
            monitor_thread.daemon = True
            monitor_thread.start()

            # 3. 글쓰기 시작 위치 계산 및 이동
            # (calculate_start_positions 함수는 외부에 정의되어 있다고 가정)
            text_start, _ = calculate_start_positions(len(text), 0, self.LETTER_SIZE, self.LETTER_SPACE)
            target_x, target_y = text_start[0], text_start[1]
    
            pos_write_above = posx([target_x, target_y, 250.0, 0.0, 180.0, 0.0])
            pos_write_start = posx([target_x, target_y, 223.5, 0.0, 180.0, 0.0])
            
            logger.info(f"글쓰기 위치로 이동 중 (X: {target_x:.2f}, Y: {target_y:.2f})")
            movel(pos_write_above, vel=self.MOVEJ_VEL, acc=self.MOVEJ_ACC, ref=DR_BASE)
            movel(pos_write_start, vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_BASE)
            
            self.pen_state = "up"
            
            # [중요] 펜이 떨어졌으면(self.pen_dropped == True) 명령을 무시하도록 방어 코드 추가
            def move_rel(dx, dy, dz=0.0, v=self.DRAW_VEL, a=self.DRAW_ACC):
                if self.pen_dropped: raise Exception("펜 놓침: 모션 강제 종료")
                if abs(dx) < self.EPS and abs(dy) < self.EPS and abs(dz) < self.EPS: return
                movel(posx([-dx, -dy, dz, 0.0, 0.0, 0.0]), vel=v, acc=a, ref=DR_TOOL, mod=DR_MV_MOD_REL)
            
            def pen_up():
                if self.pen_dropped: raise Exception("펜 놓침: 모션 강제 종료")
                if self.pen_state == "down": 
                    move_rel(0.0, 0.0, -10.0, v=self.Z_VEL, a=self.Z_ACC)
                    self.pen_state = "up"
                    
            def pen_down():
                if self.pen_dropped: raise Exception("펜 놓침: 모션 강제 종료")
                if self.pen_state == "up": 
                    move_rel(0.0, 0.0, 10.0, v=self.Z_VEL, a=self.Z_ACC)
                    self.pen_state = "down"

            logger.info("글쓰기 타각 시작!")
            engine = HangulEngine() # 외부에 정의되어 있다고 가정
            
            for i, char in enumerate(text):
                if self.pen_dropped: break # 강제 탈출

                if char == " ":
                    move_rel(self.LETTER_SPACE, 0.0, v=self.Z_VEL, a=self.Z_ACC)
                    continue
                    
                strokes = engine.get_char_strokes(char, box_width=self.LETTER_SIZE, box_height=self.LETTER_SIZE)
                cur_x, cur_y = 0.0, 0.0
                first = True
                
                for stroke in strokes:
                    sx, sy = stroke[0]
                    
                    pen_up()
                    move_rel(sx - cur_x, sy - cur_y, v=self.Z_VEL, a=self.Z_ACC) 
                    pen_down()
                    
                    cur_x, cur_y = sx, sy
                    first = False
                    for x, y in stroke[1:]:
                        move_rel(x - cur_x, y - cur_y)
                        cur_x, cur_y = x, y
                        
                pen_up()
                if i != len(text) - 1: 
                    move_rel(self.LETTER_SPACE - cur_x, -cur_y, v=self.Z_VEL, a=self.Z_ACC)

            # 정상 종료 처리
            self.is_running = False 
            
            if not self.pen_dropped:
                # 4. 글쓰기 완료 후 붓펜 반납
                logger.info("글쓰기 완료, 붓펜 반납 중...")
                
                curr_pos = get_current_posx(ref=DR_BASE)[0]
                curr_pos[2] = 250.0
                movel(curr_pos, vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_BASE)
                
                movel(pos_pen_above, vel=self.MOVEJ_VEL, acc=self.MOVEJ_ACC, ref=DR_BASE)
                movel(pos_pen_drop, vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_BASE)
                
                # 다 쓰고 나서 그리퍼 열어서 놓기
                self.gripper.move(self.t_index, twidth=50.0, tforce=40.0, fwait=True)
                
                movel(pos_pen_above, vel=self.MOVEJ_VEL, acc=self.MOVEJ_ACC, ref=DR_BASE)
                movej(Q1, vel=self.MOVEJ_VEL, acc=self.MOVEJ_ACC)

                success = True

        except Exception as e:
            if self.pen_dropped:
                logger.error("동작 중 펜을 놓쳐서 작업을 안전하게 중단하고 홈으로 복귀합니다.")
                try:
                    curr_pos = get_current_posx(ref=DR_BASE)[0]
                    curr_pos[2] = 250.0
                    movel(curr_pos, vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_BASE)
                    movej(Q1, vel=self.MOVEJ_VEL, acc=self.MOVEJ_ACC)
                except Exception:
                    pass
            else:
                logger.error(f"글쓰기 중 에러: {e}")
        finally:
            self.is_running = False
        return success


# ==========================================
# [3] 종이 뒤집기 작업
# ==========================================
class FlipTask:
    def __init__(self, movej_vel=150.0, movej_acc=150.0, movel_vel=100.0, movel_acc=100.0, slow_vel=50.0, slow_acc=50.0):
        self.MOVEJ_VEL = movej_vel; self.MOVEJ_ACC = movej_acc
        self.MOVEL_VEL = movel_vel; self.MOVEL_ACC = movel_acc
        self.SLOW_VEL = slow_vel; self.SLOW_ACC = slow_acc

    def execute(self, logger):
        from DSR_ROBOT2 import movej, movel, set_digital_output, wait
        from DR_common2 import posx, posj
        
        success = False
        try:
            Q1 = posj([0.0, 0.0, 90.0, 0.0, 90.0, 0.0])
            
            # [진입 및 빠져나오는 'ㄷ'자 경로 좌표]
            p1 = posx([422.25, 230.0,   200.0,  164.4, 180.0, 164.24])
            p2 = posx([422.25, 230.0,   99.1,   90.0, -90.0,   -0.1])
            p3 = posx([422.25, 145.53,  99.15,  90.0, -90.0,   -0.1])
            
            # [들고 뒤집고 내리는 위치 좌표]
            pos_lift = posx([422.25, 145.53, 300.0, 90.0, -90.0, -0.1])
            pos_rot  = posx([422.25, 145.53, 300.0, 90.0, -90.0, 180.0])
            pos_down = posx([422.25, 145.53,  99.15, 90.0, -90.0, 180.0])

            # 시작 시 열려있도록 보장
            set_digital_output(1, 0)
            set_digital_output(2, 1)

            logger.info("-> 'ㄷ'자 궤적으로 종이 잡는 위치로 접근")
            movel(p1, vel=self.MOVEL_VEL, acc=self.MOVEL_ACC)
            movel(p2, vel=self.MOVEL_VEL, acc=self.MOVEL_ACC)
            movel(p3, vel=self.SLOW_VEL, acc=self.SLOW_ACC)
            
            logger.info("-> 종이 잡기")
            set_digital_output(1, 1); set_digital_output(2, 0)
            wait(1.0)

            logger.info("-> 종이 들고 180도 회전")
            movel(pos_lift, vel=self.MOVEL_VEL, acc=self.MOVEL_ACC)
            movel(pos_rot, vel=self.MOVEL_VEL, acc=self.MOVEL_ACC)
            wait(0.5)

            logger.info("-> 뒤집은 상태로 내려놓기")
            movel(pos_down, vel=self.SLOW_VEL, acc=self.SLOW_ACC)
            set_digital_output(1, 0); set_digital_output(2, 1)
            wait(1.0)
            
            logger.info("-> 'ㄷ'자 궤적으로 빠져나와 홈 복귀")
            movel(p2, vel=self.MOVEL_VEL, acc=self.MOVEL_ACC)
            movel(p1, vel=self.MOVEL_VEL, acc=self.MOVEL_ACC)
            movej(Q1, vel=self.MOVEJ_VEL, acc=self.MOVEJ_ACC)

            logger.info("종이 뒤집기 완료!")
            success = True
            
        except Exception as e:
            logger.error(f"종이 뒤집기 중 에러: {e}")
            
        return success


# ==========================================
# [4] 점자 타각 작업
# ==========================================
class BrailleTask:
    def __init__(self, movej_vel=200.0, movej_acc=200.0, move_vel=150.0, move_acc=150.0, z_vel=200.0, z_acc=200.0, punch_force=15.0, char_offset=10.0):
        self.MOVEJ_VEL = movej_vel
        self.MOVEJ_ACC = movej_acc
        self.MOVE_VEL = move_vel
        self.MOVE_ACC = move_acc
        self.Z_VEL = z_vel
        self.Z_ACC = z_acc
        self.PUNCH_FORCE = punch_force
        self.CHAR_OFFSET = char_offset
        self.EPS = 1e-3

    def execute(self, data_list, logger):
        from DSR_ROBOT2 import (movej, movel, set_digital_output, wait, 
                                set_ref_coord, task_compliance_ctrl, set_desired_force, 
                                release_force, release_compliance_ctrl, check_force_condition, get_current_posx,
                                DR_TOOL, DR_BASE, DR_AXIS_Z, DR_MV_MOD_REL, set_stiffnessx, get_tool_force,
                                check_position_condition) # 💡 위치 검증을 위한 라이브러리 추가
        from DR_common2 import posx, posj

        self.braille_error = False

        if len(data_list) > 0 and data_list[-1] > 1: # 점자는 0과 1로만 이루어지므로 1 초과면 폰트 사이즈임
            letter_size = float(data_list.pop())
        else:
            letter_size = 20.0
            
        flat_bits = data_list
        num_chars = len(flat_bits) // 6
        success = False
        try:
            Q1 = posj([0.0, 25.0, 55.0, 0.0, 100.0, 0.0])
            
            # 1. 점자 툴(이쑤시개) 거치대 관련 좌표 정의 (self 적용)
            self.pos_tool_above = posx([494.0, -184.5, 242.5, 0.0, 180.0, 0.0])
            self.pos_tool_pick  = posx([494.0, -184.5, 95.0,  0.0, 180.0, 0.0])
            self.pos_tool_drop  = posx([494.0, -184.5, 105.0, 0.0, 180.0, 0.0])

            set_digital_output(1, 0); set_digital_output(2, 1) # 오픈
            
            # 2. 이쑤시개 잡으러 가기
            logger.info("점자 툴 픽업 위치로 이동 중...")
            # 홈(Q1)에서 안전 높이로 먼저 이동
            movel(self.pos_tool_above, vel=self.MOVEJ_VEL, acc=self.MOVEJ_ACC, ref=DR_BASE)
            movel(self.pos_tool_pick, vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_BASE)
            
            set_digital_output(1, 1); set_digital_output(2, 0) # 클로즈 (이쑤시개 잡기)
            wait(1.0)
            
            # 잡은 후 안전 높이로 복귀
            movel(self.pos_tool_above, vel=self.MOVEJ_VEL, acc=self.MOVEJ_ACC, ref=DR_BASE)

            # 3. 점자 타각 시작 위치 계산 및 이동
            num_chars = len(flat_bits) // 6
            _, braille_start = calculate_start_positions(0, num_chars, letter_size=letter_size, braille_offset=self.CHAR_OFFSET)
            target_x, target_y = braille_start[0], braille_start[1]
            
            # 242.5 높이를 유지하며 시작 X, Y로 이동
            pos_braille_start = posx([target_x, target_y, 242.5, 0.0, 180.0, 0.0])
            
            logger.info(f"점자 타각 시작 위치로 이동 중 (X: {target_x:.2f}, Y: {target_y:.2f})")
            movel(pos_braille_start, vel=self.MOVEJ_VEL, acc=self.MOVEJ_ACC, ref=DR_BASE)
            movel(posx([0.0, 0.0, 40.5, 0.0, 0.0, 0.0]), vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_TOOL, mod=DR_MV_MOD_REL)
            logger.info("점자 타각 시작!")

            def move_rel(dx, dy, v=self.MOVE_VEL, a=self.MOVE_ACC):
                if abs(dx) < self.EPS and abs(dy) < self.EPS: return
                dx_rot = -dx
                dy_rot = -dy
                movel(posx([dx_rot, dy_rot, 0.0, 0.0, 0.0, 0.0]), vel=v, acc=a, ref=DR_TOOL, mod=DR_MV_MOD_REL)

            def punch_dot():
                safe_pos = get_current_posx(ref=DR_BASE)[0]
                start_z = safe_pos[2]
                penetration_z = start_z - 16.0
                
                try:
                    # 1. 컴플라이언스 켜기 (유연한 상태로 진입 준비)
                    set_ref_coord(DR_TOOL)
                    task_compliance_ctrl()
                    set_stiffnessx([3000.0, 3000.0, 500.0, 100.0, 100.0, 200.0])
                    
                    # 2. 컴플라이언스 켜진 상태로 하강 (충격 흡수)
                    movel(posx([0.0, 0.0, 10.0, 0.0, 0.0, 0.0]), vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_TOOL, mod=DR_MV_MOD_REL)
                    
                    # 3. 목표 힘 인가
                    set_desired_force([0.0, 0.0, self.PUNCH_FORCE, 0.0, 0.0, 0.0], dir=[0, 0, 1, 0, 0, 0], mod=1)
                    
                    # 4. 힘 감지 루프 시작
                    target_force = self.PUNCH_FORCE * 0.8
                    force_check_count = 0
                    start_time = time.time()
                    
                    while True:
                        current_force = get_tool_force()
                        force_check_count += 1
                        
                        if force_check_count % 10 == 0:
                            print(f"[FORCE 점자] Fx={current_force[0]:.2f}, Fy={current_force[1]:.2f}, Fz={current_force[2]:.2f}")
                            
                        if not check_force_condition(DR_AXIS_Z, min=target_force, ref=DR_TOOL):
                            print(f"[FORCE 점자] 타각 접촉 감지! Fz={current_force[2]:.2f}N")
                            break

                        if not check_position_condition(DR_AXIS_Z, min=-1000.0, max=penetration_z, ref=DR_BASE):
                            print(f"[경고] 점자 관통 감지! (Z < {penetration_z:.1f}) 즉시 정지합니다.")
                            self.braille_error = True
                            raise Exception("점자 관통 발생: 모션 강제 종료")
                            
                        if time.time() - start_time > 3.0:
                            print("[ERROR] 점자 타각 타임아웃!")
                            break
                        time.sleep(0.05)
                    
                    wait(0.5)

                finally:
                    release_force(time=0.0)
                    release_compliance_ctrl()
                    set_ref_coord(DR_BASE)
                    movel(safe_pos, vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_BASE)
                    print("--- 다음 점자로 이동 ---")

            for i in range(num_chars):
                bits = flat_bits[i*6 : (i+1)*6]
                char_cur_x, char_cur_y = 0.0, 0.0
                
                for j, val in enumerate(bits):
                    if val == 1:
                        target_x_char, target_y_char = (j // 3) * 2.5, (j % 3) * 2.5 
                        dx, dy = target_x_char - char_cur_x, target_y_char - char_cur_y
                        move_rel(dx, dy)
                        punch_dot()
                        char_cur_x, char_cur_y = target_x_char, target_y_char
                        
                if i != num_chars - 1:
                    move_rel(self.CHAR_OFFSET - char_cur_x, -char_cur_y)

            # 4. 점자 타각 완료 후 이쑤시개 반납
            if not self.braille_error:
                logger.info("점자 타각 완료, 툴 반납 중...")
                curr_pos = get_current_posx(ref=DR_BASE)[0]
                curr_pos[2] = 242.5
                movel(curr_pos, vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_BASE)
                
                movel(self.pos_tool_above, vel=self.MOVEJ_VEL, acc=self.MOVEJ_ACC, ref=DR_BASE)
                movel(self.pos_tool_drop, vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_BASE)
                
                set_digital_output(1, 0); set_digital_output(2, 1)
                wait(1.0)
                
                movel(self.pos_tool_above, vel=self.MOVEJ_VEL, acc=self.MOVEJ_ACC, ref=DR_BASE)
                movej(Q1, vel=self.MOVEJ_VEL, acc=self.MOVEJ_ACC)
                success = True

        except Exception as e:
            if self.braille_error:
                logger.error("동작 중 점자 관통 또는 타임아웃이 발생하여 안전하게 중단하고 홈으로 복귀합니다.")
                try:
                    curr_pos = get_current_posx(ref=DR_BASE)[0]
                    curr_pos[2] = 250.0
                    movel(curr_pos, vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_BASE)
                    movej(Q1, vel=self.MOVEJ_VEL, acc=self.MOVEJ_ACC)
                except Exception:
                    pass
            else:
                logger.error(f"점자 에러: {e}")

        return success

# ==========================================
# [5] 도장 찍기 작업
# ==========================================


class StampTask:
    def __init__(self, move_vel=150.0, move_acc=150.0, z_vel=50.0, z_acc=50.0, press_force=10.0):
        self.MOVE_VEL = move_vel
        self.MOVE_ACC = move_acc
        self.Z_VEL = z_vel
        self.Z_ACC = z_acc
        self.PRESS_FORCE = press_force

        # 안전 제어를 위한 RG2 그리퍼 및 상태 플래그 초기화
        self.is_running = False
        self.stamp_dropped = False

        self.cb_ip = '192.168.1.1' 
        self.dev = Device(Global_cbip=self.cb_ip)
        self.gripper = RG(self.dev)
        self.t_index = 0

    def execute(self, logger):
        from DSR_ROBOT2 import (movej, movel, wait, 
                                set_ref_coord, task_compliance_ctrl, set_desired_force, set_digital_output, set_stiffnessx, 
                                release_force, release_compliance_ctrl, check_force_condition,
                                set_stiffnessx, get_tool_force, get_current_posx,
                                DR_TOOL, DR_BASE, DR_AXIS_Z)
        from DR_common2 import posx, posj
        
        success = False
        self.is_running = True
        self.stamp_dropped = False

        if not self.gripper.isConnected(self.t_index):
            logger.error("RG2 그리퍼와 통신할 수 없습니다. IP 주소나 랜선 연결을 확인하세요.")
            return False


        def monitor_grip():
            while self.is_running:
                try:
                    current_width = self.gripper.get_width(self.t_index)
                    is_gripped = self.gripper.isGripped(self.t_index)
                    # 도장 파지 감지 (도장이 15.0mm 이하로 닫히거나 놓치면 정지)
                    if current_width < 15.0 or not is_gripped: 
                        logger.error(f"[경고] 도장 놓침 감지! (현재 너비: {current_width:.1f}mm) 즉시 정지합니다.")
                        self.stamp_dropped = True
                        break
                except Exception:
                    pass
                time.sleep(0.1)
        
        try:
            Q_HOME = posj([0.0, 25.0, 55.0, 0.0, 100.0, 0.0])
            
            # 절대 좌표 기준 (목표 표면 Z값)
            pos_ink_above = posx([640.0, -2.0, 200.0, 0.0, 180.0, 0.0])
            pos_ink       = posx([640.0, -2.0, 157.0, 0.0, 180.0, 0.0])
            
            pos_stamp_above = posx([516.0, -43.0, 200.0, 90.0, 180.0, 0.0])
            pos_stamp       = posx([516.0, -43.0, 135.0, 90.0, 180.0, 0.0])

            # 1. 인주 묻히기 위치로 이동 (안전 높이)
            logger.info("도장 픽업 및 인주 묻히기 위치로 이동")
            set_digital_output(1, 0); set_digital_output(2, 1)
            movel(pos_ink_above, vel=self.MOVE_VEL, acc=self.MOVE_ACC, ref=DR_BASE)
            
            
            # ==========================================
            # [인주 묻히기]
            # ==========================================
            logger.info("힘 제어로 인주 묻히기 시작")
            set_ref_coord(DR_TOOL)
            task_compliance_ctrl()
            set_stiffnessx([3000.0, 3000.0, 500.0, 100.0, 100.0, 200.0])
            
            # 순응 제어(컴플라이언스)가 켜진 상태로 목표 위치까지 안전하게 하강
            movel(pos_ink, vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_BASE)
            set_digital_output(1, 1); set_digital_output(2, 0)
            wait(1.0)
            monitor_thread = threading.Thread(target=monitor_grip)
            monitor_thread.daemon = True
            monitor_thread.start()  
            if self.stamp_dropped: raise Exception("도장 놓침: 모션 강제 종료")

            set_desired_force([0.0, 0.0, self.PRESS_FORCE, 0.0, 0.0, 0.0], dir=[0, 0, 1, 0, 0, 0], mod=1)

            target_force = self.PRESS_FORCE * 0.8
            force_check_count = 0
            start_time = time.time()
            
            while True:
                if self.stamp_dropped: raise Exception("도장 놓침: 모션 강제 종료")
                current_force = get_tool_force()
                force_check_count += 1
                if force_check_count % 10 == 0:
                    logger.info(f"[FORCE 인주] Fx={current_force[0]:.2f}, Fy={current_force[1]:.2f}, Fz={current_force[2]:.2f}")

                if not check_force_condition(DR_AXIS_Z, min=target_force, max=150, ref=DR_TOOL):
                    logger.info(f"[FORCE 인주] 인주 누르기 감지! Fz={current_force[2]:.2f}N")
                    break

                if time.time() - start_time > 5.0:
                    logger.error("[ERROR] 인주 누르기 타임아웃!")
                    break
                time.sleep(0.05)

            wait(1.5) # 인주가 충분히 묻도록 대기
            release_force(time=0.0)
            release_compliance_ctrl()
            
            # 인주 찍고 다시 상승
            if self.stamp_dropped: raise Exception("도장 놓침: 모션 강제 종료")
            movel(pos_ink_above, vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_BASE)

            # ==========================================
            # [도장 찍기]
            # ==========================================
            if self.stamp_dropped: raise Exception("도장 놓침: 모션 강제 종료")
            logger.info("도장 찍을 위치로 이동")
            movel(pos_stamp_above, vel=self.MOVE_VEL, acc=self.MOVE_ACC, ref=DR_BASE)

            if self.stamp_dropped: raise Exception("도장 놓침: 모션 강제 종료")
            logger.info("힘 제어로 도장 찍기 시작")
            set_ref_coord(DR_TOOL)
            task_compliance_ctrl()
            set_stiffnessx([3000.0, 3000.0, 500.0, 100.0, 100.0, 200.0])
            
            # 순응 제어가 켜진 상태로 도장 위치까지 하강
            movel(pos_stamp, vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_BASE)
            set_desired_force([0.0, 0.0, self.PRESS_FORCE, 0.0, 0.0, 0.0], dir=[0, 0, 1, 0, 0, 0], mod=1)

            force_check_count = 0
            start_time = time.time()

            while True:
                if self.stamp_dropped: raise Exception("도장 놓침: 모션 강제 종료")
                current_force = get_tool_force()
                force_check_count += 1
                if force_check_count % 10 == 0:
                    logger.info(f"[FORCE 도장] Fx={current_force[0]:.2f}, Fy={current_force[1]:.2f}, Fz={current_force[2]:.2f}")

                if not check_force_condition(DR_AXIS_Z, min=target_force, max=150, ref=DR_TOOL):
                    logger.info(f"[FORCE 도장] 도장 누르기 감지! Fz={current_force[2]:.2f}N")
                    break

                if time.time() - start_time > 5.0:
                    logger.error("[ERROR] 도장 누르기 타임아웃!")
                    break
                time.sleep(0.05)

            wait(1.5) # 도장이 선명하게 찍히도록 대기
            release_force(time=0.0)
            release_compliance_ctrl()
            
            # 도장 찍고 상승
            if self.stamp_dropped: raise Exception("도장 놓침: 모션 강제 종료")
            movel(pos_stamp_above, vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_BASE)

            # 5. 종료 작업
            if self.stamp_dropped: raise Exception("도장 놓침: 모션 강제 종료")
            logger.info("도장 찍기 완료, 반납 후 홈 복귀")
            movel(pos_ink_above, vel=self.MOVE_VEL, acc=self.MOVE_ACC, ref=DR_BASE)
            movel(pos_ink, vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_BASE)
            
            set_digital_output(1, 0); set_digital_output(2, 1) # 도장 놓기
            wait(1.0)
            
            movel(pos_ink_above, vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_BASE)
            movej(Q_HOME, vel=self.MOVE_VEL, acc=self.MOVE_ACC)
            success = True

        except Exception as e:
            if self.stamp_dropped:
                logger.error("동작 중 도장을 놓쳐서 작업을 안전하게 중단하고 홈으로 복귀합니다.")
                try:
                    # 💡 진행중이던 힘 제어 상태를 강제 해제하고 위로 안전하게 회피
                    release_force(time=0.0)
                    release_compliance_ctrl()
                    curr_pos = get_current_posx(ref=DR_BASE)[0]
                    curr_pos[2] = 250.0
                    movel(curr_pos, vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_BASE)
                    movej(Q_HOME, vel=self.MOVE_VEL, acc=self.MOVE_ACC)
                except Exception:
                    pass
            else:
                logger.error(f"도장 찍기 에러: {e}")
        finally:
            self.is_running = False
            
        return success


# ==========================================
# [6] 통신 담당 메인 노드 
# ==========================================
class RobotControlNode(Node):
    def __init__(self, writer_obj, braille_obj, flipper_obj, stamper_obj):
        super().__init__('robot_control_node', namespace=ROBOT_ID)
        
        self.writer = writer_obj
        self.braille_printer = braille_obj
        self.flipper = flipper_obj
        self.stamper = stamper_obj
        
        self.sub_write = self.create_subscription(String, '/write_cmd', self.write_cmd_cb, 10)
        self.sub_braille = self.create_subscription(Int32MultiArray, '/braille_cmd', self.braille_cmd_cb, 10)
        self.pub_write_done = self.create_publisher(Bool, '/write_done', 10)
        self.pub_braille_done = self.create_publisher(Bool, '/braille_done', 10)
        
        self.task_queue = [] 

    def write_cmd_cb(self, msg):
        self.get_logger().info(f"[명령 수신] 글쓰기 데이터 수신")
        try:
            data = json.loads(msg.data)
        except Exception:
            data = {"text": msg.data, "size": 20.0}
        self.task_queue.append(('write', data))

    def braille_cmd_cb(self, msg):
        self.get_logger().info("[명령 수신] 점자 타각")
        self.task_queue.append(('braille', list(msg.data)))

    def process_queue(self):
        """큐에 담긴 작업을 하나씩 꺼내어 실행"""
        if self.task_queue:
            task_type, data     = self.task_queue.pop(0)

            if task_type == 'braille':
                # 4. MasterNode가 점자 명령을 쏘면 실행
                is_success = self.braille_printer.execute(data, self.get_logger())
                if is_success:
                    self.get_logger().info("점자 찍기 완료! 이어서 자동으로 종이 뒤집기를 시작합니다.")
                    is_success = self.flipper.execute(self.get_logger())

                res = Bool()
                res.data = is_success
                self.pub_braille_done.publish(res)

            
            
            elif task_type == 'write':
                # 1. 글쓰기 먼저 실행
                is_success = self.writer.execute(data, self.get_logger())
                
                # 2. 글쓰기가 성공했다면, "종이 뒤집기"를 통신 없이 내부적으로 바로 실행!
                if is_success:
                    self.get_logger().info("글자 쓰기 완료! 이어서 도장 찍기를 시작합니다.") 
                    is_success = self.stamper.execute(self.get_logger())
                
                # 3. 글쓰기 + 종이 뒤집기 + 도장 찍기 최종 결과를 MasterNode에게 보고
                res = Bool()
                res.data = is_success
                self.pub_write_done.publish(res)
                



# ==========================================
# [7] 중심 잡기 함수
# ==========================================

def calculate_start_positions(text_len, braille_len, letter_size=20.0, letter_space=25.0, braille_offset=10.0):
    # 1. 종이 영역 중심점 및 기준 Y 좌표[cite: 2]
    x_center = (281.0 + 566.0) / 2.0  # X 중심: 423.5[cite: 2]
    y_max = 97.0                      # 상단 기준 Y 좌표[cite: 2]
    
    # 2. 글자 전체 너비 및 시작점 계산
    # (글자수 - 1) * 띄어쓰기 간격 + 마지막 글자의 너비
    text_width = (text_len - 1) * letter_space + letter_size if text_len > 0 else 0.0
    text_start_x = x_center - (text_width / 2.0)
    text_start_y = y_max  # 상단 여백 확보 가능
    
    # 3. 점자 전체 너비 및 시작점 계산
    # 점자 1칸 너비는 5.0 (가로 최대 인덱스 기준)
    braille_cell_width = 2.5
    braille_width = (braille_len - 1) * braille_offset + braille_cell_width if braille_len > 0 else 0.0
    braille_start_x = x_center - (braille_width / 2.0)
    
    # 4. 점자 시작 Y 좌표: 글자의 제일 낮은 Y 좌표(text_start_y - letter_size)에서 20mm 아래
    lowest_text_y = y_max - letter_size
    braille_start_y = lowest_text_y - 20.0

    return [text_start_x, text_start_y], [braille_start_x, braille_start_y]

# ==========================================
# [8] 메인 실행 함수
# ==========================================
def main(args=None):
    rclpy.init(args=args)

    DR_init.__dsr__id = ROBOT_ID
    DR_init.__dsr__model = ROBOT_MODEL

    # 객체 생성 (속도/가속도 파라미터 세팅)
    my_writer = WriteTask(
        movej_vel=200.0, movej_acc=200.0,
        draw_vel=200.0,  draw_acc=200.0,
        z_vel=50.0,     z_acc=50.0
    )
    
    my_flipper = FlipTask(
        movej_vel=50.0, movej_acc=50.0, 
        movel_vel=50.0, movel_acc=50.0,
        slow_vel=50.0,   slow_acc=50.0
    )
    
    my_braille = BrailleTask(
        movej_vel=200.0, movej_acc=200.0,
        move_vel=100.0,  move_acc=100.0,
        z_vel=20.0,      z_acc=20.0, # 찍기 강도 영향있음 테스트 필요!!!!
        punch_force=20.0, char_offset=5.5
    )
    my_stamper = StampTask(
        move_vel=150.0, move_acc=150.0,
        z_vel=50.0, z_acc=50.0,
        press_force=10.0 # 약한 힘으로 시작 (테스트 후 증가)
    )

    # 3. 노드 생성 및 주입
    node = RobotControlNode(my_writer, my_braille, my_flipper, my_stamper)
    DR_init.__dsr__node = node

    # 4. 초기화!
    initialize_robot()
    node.get_logger().info(" 로봇 통합 제어 노드 가동 완료")

    try:
        while rclpy.ok():
            node.process_queue()
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()