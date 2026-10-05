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

# 힘제어 함수
def force_control(): 
    #힙제어 필요 명령어
    from DSR_ROBOT2 import task_compliance_ctrl, set_stiffnessx, set_desired_force, DR_FC_MOD_REL
    

    task_compliance_ctrl()
    set_stiffnessx([10, 10, 10, 200 ,200 ,200], time =0) #강도 조절 가능
    print("순응 제어 시작")
    set_desired_force([0,0,-1, 0, 0, 0], [0, 0, 1, 0, 0, 0], time=0.0,mod=DR_FC_MOD_REL) #힘은 쓰면서 테스트 필요
    print("힘 제어 시작")

def grip_close():
    from DSR_ROBOT2 import set_digital_output, wait
    
    set_digital_output(1, 1)
    set_digital_output(2, 0)
    wait(1.0)
#메인 함수
def main(args=None):
    rclpy.init(args=args)
    #노드 이름 설정
    node = rclpy.create_node("gripper", namespace=ROBOT_ID)

    # DR_init에 노드 설정
    DR_init.__dsr__node = node
    #메인 명령어
    from DSR_ROBOT2 import (
            task_compliance_ctrl, set_stiffnessx, set_desired_force, amove_periodic, DR_FC_MOD_REL, DR_AXIS_Z, DR_TOOL, DR_MV_MOD_REL,
            check_position_condition, release_force, release_compliance_ctrl, check_force_condition, wait, movej, movel
        )
    from DR_common2 import posx, posj
    Q1 = posj(0.0, 0.0, 90.0, 0.0, 90.0, 0.0)
    Q2 = posx(0, 0, 0, 0, 0, 0) #작업 시작위치 이동
    draw_point1 = posx(-50, 0, 0, 0, 0, 0)
    draw_point2 = posx(0, 50, 0, 0, 0, 0)
    draw_point3 = posx(-10, 0, 0, 0, 0, 0)
    draw_point4 = posx(0, -50, 0, 0, 0, 0)
    draw_point5 = posx(0, 0, 0, 0, 0, 0)

    draw = check_force_condition(DR_AXIS_Z, min=2.5, max=5)


    try:
            
        initialize_robot()
        node.get_logger().info(f"Moving to joint position: {Q1}")
        movej(Q1, vel=VELOCITY, acc=ACC)
        print("1")
        movel(Q2, vel=VELOCITY, acc=ACC, ref = DR_TOOL)
        print("2")
        #force_control() #힘제어 없는 상태
        print("3")
        grip_close()
        node.get_logger().info(f"그리퍼 닫기")
        wait(5.0)
        movel(draw_point1, vel=VELOCITY, acc=ACC, mod=DR_MV_MOD_REL)
        print("1번")
        movel(draw_point2, vel=VELOCITY, acc=ACC, mod=DR_MV_MOD_REL)
        print("2번")
        movel(draw_point3, vel=VELOCITY, acc=ACC, mod=DR_MV_MOD_REL)
        print("4")
        movel(draw_point4, vel=VELOCITY, acc=ACC, mod=DR_MV_MOD_REL)
        print("5")
        movel(draw_point5, vel=VELOCITY, acc=ACC, mod=DR_MV_MOD_REL)
        #release_force(time=0.0) #힘제어 다시 구현시 켜야됨
        #release_compliance_ctrl()
        
       
            




    except KeyboardInterrupt:
        print("\nNode interrupted by user. Shutting down...")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        movej(Q1, vel=VELOCITY, acc=ACC)
        rclpy.shutdown()

if __name__ == "__main__":
    main()






