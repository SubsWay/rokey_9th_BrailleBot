import rclpy
import DR_init

# 로봇 설정 상수
ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"
ROBOT_TOOL = "Tool Weight"
ROBOT_TCP = "GripperDA"

# 이동 속도 및 가속도
VELOCITY = 30
ACC = 30

# DR_init 설정
DR_init.__dsr__id = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL

# robot star setting 
def initialize_robot():
    """로봇의 Tool과 TCP를 설정"""
    from DSR_ROBOT2 import set_tool, set_tcp


    # 설정된 상수 출력
    print("-" * 50)
    print("Initializing robot with the following settings:")
    print(f"ROBOT_ID: {ROBOT_ID}")
    print(f"ROBOT_MODEL: {ROBOT_MODEL}")
    print(f"ROBOT_TCP: {ROBOT_TCP}")
    print(f"ROBOT_TOOL: {ROBOT_TOOL}")
    print(f"VELOCITY: {VELOCITY}")
    print(f"ACC: {ACC}")
    print("-" * 50)

    # Tool과 TCP 설정
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
    node = rclpy.create_node("gripper", namespace=ROBOT_ID)

    # DR_init에 노드 설정
    DR_init.__dsr__node = node
    from DSR_ROBOT2 import wait, movej, movel, DR_SSTOP
    from DR_common2 import posx, posj
    Q1 = posj(0.0, 0.0, 90.0, 0.0, 90.0, 0.0)
    try:
            
        initialize_robot()
        node.get_logger().info(f"Moving to joint position: {Q1}")
        movej(Q1, vel=VELOCITY, acc=ACC)
        grip_close()
        node.get_logger().info(f"griper open")
        wait(1.0)
        grip_open()
        node.get_logger().info(f"griper close")

        DR_SSTOP
        node.get_logger().info(f"STOP")
    except KeyboardInterrupt:
        print("\nNode interrupted by user. Shutting down...")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        movej(Q1, vel=VELOCITY, acc=ACC)
        rclpy.shutdown()
if __name__ == "__main__":
    main()
