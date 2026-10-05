from lark import logger 
import rclpy
from rclpy.node import Node
import DR_init
import time

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"
ROBOT_TCP = "GripperDA_v1"
ROBOT_TOOL = "Tool Weight"
 

DR_init.__dsr__id = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL

class StampTask:
    def __init__(self, move_vel=150.0, move_acc=150.0, z_vel=50.0, z_acc=50.0, press_force=10.0):
        self.MOVE_VEL = move_vel
        self.MOVE_ACC = move_acc
        self.Z_VEL = z_vel
        self.Z_ACC = z_acc
        self.PRESS_FORCE = press_force

    def execute(self, logger):
        from DSR_ROBOT2 import (movej, movel, set_digital_output, wait, 
                                set_ref_coord, task_compliance_ctrl, set_desired_force, 
                                release_force, release_compliance_ctrl, check_force_condition,
                                set_stiffnessx, get_tool_force,
                                DR_TOOL, DR_BASE, DR_AXIS_Z)
        from DR_common2 import posx, posj
        
        success = False
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
            set_desired_force([0.0, 0.0, self.PRESS_FORCE, 0.0, 0.0, 0.0], dir=[0, 0, 1, 0, 0, 0], mod=1)

            target_force = self.PRESS_FORCE * 0.8
            force_check_count = 0
            start_time = time.time()
            
            while True:
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
            movel(pos_ink_above, vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_BASE)

# ==========================================
# [도장 찍기]
# ==========================================
            logger.info("도장 찍을 위치로 이동")
            movel(pos_stamp_above, vel=self.MOVE_VEL, acc=self.MOVE_ACC, ref=DR_BASE)

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
            movel(pos_stamp_above, vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_BASE)

            # 5. 종료 작업
            logger.info("도장 찍기 완료, 반납 후 홈 복귀")
            movel(pos_ink_above, vel=self.MOVE_VEL, acc=self.MOVE_ACC, ref=DR_BASE)
            movel(pos_ink, vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_BASE)
            
            set_digital_output(1, 0); set_digital_output(2, 1) # 도장 놓기
            wait(1.0)
            
            movel(pos_ink_above, vel=self.Z_VEL, acc=self.Z_ACC, ref=DR_BASE)
            movej(Q_HOME, vel=self.MOVE_VEL, acc=self.MOVE_ACC)
            success = True

        except Exception as e:
            logger.error(f"도장 찍기 에러: {e}")
            
        return success

def initialize_robot():
    """로봇의 Tool과 TCP 및 초기 모드를 설정"""
    from DSR_ROBOT2 import set_tool, set_tcp, release_force, release_compliance_ctrl, set_robot_mode, ROBOT_MODE_AUTONOMOUS 
    
    set_tool(ROBOT_TOOL) 
    set_tcp(ROBOT_TCP) 
    print("로봇 Tool/TCP 초기화 완료") 

def main(args=None):
    rclpy.init(args=args)
    # 네임스페이스 추가 완료
    node = Node('stamp_test_node', namespace=ROBOT_ID)
    DR_init.__dsr__node = node
    
    initialize_robot()
    stamper = StampTask()
    stamper.execute(node.get_logger())
    
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()