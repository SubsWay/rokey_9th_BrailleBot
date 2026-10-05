import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32MultiArray, Bool
import DR_init

# 로봇 설정 상수
ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"
ROBOT_TOOL = "Tool Weight"
ROBOT_TCP = "GripperDA"

VELOCITY, ACC = 100, 100
PEN_Z_VELOCITY, PEN_Z_ACC = 20, 20
EPS = 1e-3
NEXT_CHAR_OFFSET_X = 10.0
NEXT_CHAR_OFFSET_Y = 0.0

class BrailleNode(Node):
    def __init__(self):
        super().__init__('braille_node', namespace=ROBOT_ID)
        self.sub = self.create_subscription(Int32MultiArray, '/braille_cmd', self.cmd_callback, 10)
        self.pub = self.create_publisher(Bool, '/braille_done', 10)
        self.received_bits = None

    def initialize_robot_hardware(self):
        from DSR_ROBOT2 import set_tool, set_tcp, movej, movel, set_digital_output, wait, DR_TOOL
        from DR_common2 import posj, posx
        
        self.Q1 = posj(0.0, 25.0, 55.0, 0.0, 100.0, 0.0)
        set_tool(ROBOT_TOOL)
        set_tcp(ROBOT_TCP)
        
        # 그리퍼 초기화
        set_digital_output(1, 0)
        set_digital_output(2, 1) # open
        self.get_logger().info("초기 위치 이동 중...")
        movej(self.Q1, vel=VELOCITY, acc=ACC)
        
        print("점필을 쥐어주세요 (5초 대기)")
        wait(5.0)
        set_digital_output(1, 1)
        set_digital_output(2, 0) # close
        wait(1.0)
        
        # 핀 올리기 (대기 모드)
        movel(posx(0.0, 0.0, -35.0, 0.0, 0.0, 0.0), vel=PEN_Z_VELOCITY, acc=PEN_Z_ACC, ref=DR_TOOL)
        self.get_logger().info("점자 타각 대기 모드 진입 완료.")

    def cmd_callback(self, msg):
        self.received_bits = list(msg.data)
        self.get_logger().info(f"점자 명령 수신: 총 {len(self.received_bits)//6}글자")

    def do_braille_task(self, flat_bits):
        from DSR_ROBOT2 import (movel, set_ref_coord, task_compliance_ctrl, set_desired_force, 
                                release_force, release_compliance_ctrl, check_force_condition, 
                                DR_TOOL, DR_BASE, DR_AXIS_Z)
        from DR_common2 import posx, get_current_posx
        
        success = False

        def move_tool(dx, dy, dz=0.0):
            if abs(dx) < EPS and abs(dy) < EPS and abs(dz) < EPS:
                return
            movel(posx(dx, dy, dz, 0.0, 0.0, 0.0), vel=VELOCITY, acc=ACC, ref=DR_TOOL)

        def punch_dot(force, hold_time):
            safe_pos = get_current_posx(ref=DR_BASE)[0]
            try:
                move_tool(0.0, 0.0, 34.0)
                set_ref_coord(DR_TOOL)
                task_compliance_ctrl([3000.0, 3000.0, 1000.0, 200.0, 200.0, 200.0], time=0.2)
                set_desired_force([0.0, 0.0, force, 0.0, 0.0, 0.0], dir=[0, 0, 1, 0, 0, 0], time=0.2, mod=0)
                
                fcon = check_force_condition(DR_AXIS_Z, min=2.75, max=30.0, ref=DR_TOOL)
                if fcon == 0:
                    pass
                else:
                    self.get_logger().warn("힘 감지 타임아웃 또는 오버로드")
            finally:
                release_force(time=0.2)
                release_compliance_ctrl()
                set_ref_coord(DR_BASE)
                movel(safe_pos, vel=PEN_Z_VELOCITY, acc=PEN_Z_ACC, ref=DR_BASE)

        def print_braille_character(bits, offset_x=0.0, offset_y=0.0, advance=True):
            GAP_X, GAP_Y = 5, 5
            char_cur_x, char_cur_y = 0.0, 0.0

            for i, val in enumerate(bits):
                if val == 1:
                    col, row = i // 3, i % 3
                    target_x, target_y = col * GAP_X, row * GAP_Y
                    move_tool(target_x - char_cur_x, target_y - char_cur_y, 0.0)
                    punch_dot(force=15, hold_time=0.5)
                    char_cur_x, char_cur_y = target_x, target_y

            if advance:
                move_tool(offset_x - char_cur_x, offset_y - char_cur_y, 0.0)

        try:
            num_chars = len(flat_bits) // 6
            for i in range(num_chars):
                bits = flat_bits[i*6 : (i+1)*6]
                is_last = (i == num_chars - 1)
                print_braille_character(bits, offset_x=NEXT_CHAR_OFFSET_X, offset_y=NEXT_CHAR_OFFSET_Y, advance=not is_last)
            success = True
        except Exception as e:
            self.get_logger().error(f"점자 타각 중 오류: {e}")
        finally:
            res_msg = Bool()
            res_msg.data = success
            self.pub.publish(res_msg)


def main(args=None):
    rclpy.init(args=args)

    DR_init.__dsr__id = ROBOT_ID
    DR_init.__dsr__model = ROBOT_MODEL

    node = BrailleNode()
    DR_init.__dsr__node = node

    from DSR_ROBOT2 import release_force, release_compliance_ctrl
    release_force(time=0.0)
    release_compliance_ctrl()

    node.initialize_robot_hardware()

    try:
        while rclpy.ok():
            if node.received_bits is not None:
                bits = node.received_bits
                node.received_bits = None
                node.do_braille_task(bits)
            
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()