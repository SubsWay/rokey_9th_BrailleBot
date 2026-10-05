import rclpy
import threading
import DR_init

# ※ 서비스 메시지는 사용자의 패키지 환경에 맞춰 임포트 해주세요.
# 예시로 int32[] data를 받고 bool success를 반환하는 PrintBraille 서비스가 있다고 가정합니다.
# from custom_interfaces.srv import PrintBraille 

# 로봇 설정 상수
ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"
ROBOT_TOOL = "Tool Weight"
ROBOT_TCP = "GripperDA"


# 평상시 이동/그리기 속도 및 가속도
VELOCITY = 200
ACC = 200

# 펜을 종이에 대거나 뗄 때(Z축) 사용할 속도/가속도
# 접촉 충격을 줄이기 위해 평상시보다 느리게 설정
PEN_Z_VELOCITY = 200
PEN_Z_ACC = 200

# 평상시 이동 속도 및 가속도
VELOCITY = 50
ACC = 50

# 펜/핀 승강 속도/가속도
PEN_Z_VELOCITY = 20
PEN_Z_ACC = 20


# 상대 이동량이 이 값보다 작으면 이동 명령 자체를 보내지 않음 (0거리 이동 방지)
EPS = 1e-3

# DR_init 설정
DR_init.__dsr__id = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL


def initialize_robot():
    """로봇의 Tool과 TCP를 설정"""
    from DSR_ROBOT2 import set_tool, set_tcp
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
    node = rclpy.create_node("braille_printer", namespace=ROBOT_ID)
    DR_init.__dsr__node = node

    from DSR_ROBOT2 import (wait, movej, movel, DR_TOOL, DR_BASE, 
                            set_ref_coord, task_compliance_ctrl, set_desired_force, 
                            release_force, release_compliance_ctrl)
    from DR_common2 import posx, posj

    # 시작 기준점 (원하시는 위치로 자유롭게 변경하세요)
    Q1 = posj(0.0, 0.0, 90.0, 0.0, 90.0, 0.0)

    # --- 펜 이동 및 상태 관리 ---
    pen_state = "up"
    
    # 글자 내 현재 위치 상태 (원점 기준)
    current_x = 0.0
    current_y = 0.0

    def move_rel(dx, dy, dz=0.0, vel=VELOCITY, acc=ACC):
        if abs(dx) < EPS and abs(dy) < EPS and abs(dz) < EPS:
            return
        movel(posx(dx, dy, dz, 0.0, 0.0, 0.0), vel=vel, acc=acc, ref=DR_TOOL)

    def pen_up():
        nonlocal pen_state
        if pen_state == "down":
            move_rel(0.0, 0.0, -10.0, vel=PEN_Z_VELOCITY, acc=PEN_Z_ACC)
            pen_state = "up"

    def pen_down():
        nonlocal pen_state
        if pen_state == "up":
            move_rel(0.0, 0.0, 10.0, vel=PEN_Z_VELOCITY, acc=PEN_Z_ACC)
            pen_state = "down"

    # ==============================================================
    # 테스트를 위해 별도로 분리한 힘/순응 제어 기반 점자 타격 함수
    # ==============================================================
    def punch_dot(force=5.0, hold_time=0.5):
        """
        :param force: 핀을 아래로 누르는 힘 (N단위) 
                      방향 세팅에 따라 -5.0이 될 수도 있으니 테스트 필요
        :param hold_time: 힘을 유지하며 꾹 누르고 있는 시간 (초)
        """
        try:
            # 1. 핀을 종이 위치까지 내림 (접촉 충격 방지를 위해 속도 느림)
            pen_down()

            # 2. 기준 좌표계를 TOOL로 변경 (툴 Z축 방향으로 힘을 가하기 위함)
            set_ref_coord(DR_TOOL)

            # 3. Z축 강성 낮추기 (순응 제어) - [Kx, Ky, Kz, Krx, Kry, Krz]
            stx = [3000.0, 3000.0, 500.0, 200.0, 200.0, 200.0]
            task_compliance_ctrl(stx, time=0.0)

            # 4. Z축 방향으로 force 만큼 누르기
            fd = [0.0, 0.0, force, 0.0, 0.0, 0.0]
            fctrl_dir = [0, 0, 1, 0, 0, 0]
            set_desired_force(fd, dir=fctrl_dir)

            # 5. 설정한 시간만큼 꾹 눌러 점자 생성
            wait(hold_time)

        finally:
            # 6. 힘 제어 해제 및 좌표계 복귀
            release_force(time=0.0)
            release_compliance_ctrl()
            set_ref_coord(DR_BASE)
            
            # 7. 핀 들기
            pen_up()

    # ==============================================================
    # 점자 배열 데이터를 받아 그리는 메인 로직
    # ==============================================================
    def print_braille(dots, offset_x=0.0, offset_y=0.0):
        """
        dots : 점자 규격 데이터 (예: [1, 0, 0, 1, 1, 0])
        offset_x, offset_y : 다음 글자 시작점까지의 이동 간격
        """
        GAP_X = 2.5 # 점과 점 사이의 가로 간격
        GAP_Y = 2.5 # 점과 점 사이의 세로 간격
        
        nonlocal current_x, current_y
        
        for i, val in enumerate(dots):
            if val == 1:
                # 인덱스 위치 매핑: 1~3번 점은 0열, 4~6번 점은 1열
                col = i // 3
                row = i % 3
                
                target_x = col * GAP_X
                target_y = row * GAP_Y
                
                # 가야 할 상대 거리 계산
                dx = target_x - current_x
                dy = target_y - current_y
                
                # 해당 점의 위치 바로 위로 이동 후, 점 찍기 함수 호출
                move_rel(dx, dy, 0.0)
                punch_dot(force=5.0, hold_time=0.5)
                
                current_x = target_x
                current_y = target_y
        
        # 글자 작업이 끝나면 다음 글자 시작 위치로 이동
        move_rel(offset_x - current_x, offset_y - current_y, 0.0)
        current_x = 0.0
        current_y = 0.0

    is_printing = False

    # ==============================================================
    # 서비스 통신 콜백 관련 로직
    # ==============================================================
    def braille_service_callback(request, response):
        """서비스로 배열(int32[])을 요청받았을 때 실행되는 콜백"""
        nonlocal is_printing
        if is_printing:
            response.success = False
            response.message = "현재 다른 점자를 출력 중입니다."
            return response

        if len(request.data) != 6:
            response.success = False
            response.message = "수신 데이터 길이가 6이 아닙니다. (2x3 배열 필요)"
            return response

        node.get_logger().info(f"점자 데이터 수신: {list(request.data)}")
        
        # ROS2 콜백이 뻗는 걸(Blocking) 방지하기 위해 스레드 사용
        def task():
            nonlocal is_printing
            is_printing = True
            try:
                # 점자 출력 (예: 자간을 X축으로 10.0mm 띄움)
                print_braille(request.data, offset_x=10.0, offset_y=0.0)
                node.get_logger().info("점자 출력 완료")
            except Exception as e:
                node.get_logger().error(f"출력 에러: {e}")
            finally:
                is_printing = False

        threading.Thread(target=task).start()

        response.success = True
        response.message = "점자 출력 모션을 시작합니다."
        return response

    # ★ 사용하는 커스텀 서비스 형태에 맞춰 아래 주석을 해제하고 등록하세요.
    # srv = node.create_service(PrintBraille, 'print_braille_srv', braille_service_callback)

    try:
        initialize_robot()
        grip_open()
        node.get_logger().info(f"Moving to joint position: {Q1}")
        movej(Q1, vel=VELOCITY, acc=ACC)

        print("펜/점자핀을 쥐어주세요 (5초 대기)")
        wait(5.0)
        grip_close()

        # 점자는 기본적으로 종이에서 떨어져 있어야 하므로 미리 위로 들고 대기합니다.
        move_rel(0.0, 0.0, -10.0, vel=PEN_Z_VELOCITY, acc=PEN_Z_ACC)
        pen_state = "up"

        print("점자 출력 대기 중... 서비스 명령을 기다립니다.")
        
        # --- (서비스 호출 전 단독으로 동작 테스트를 하려면 아래 구문을 사용하세요) ---
        print("단독 동작 테스트: [1, 0, 0, 1, 1, 0] 출력 시작")
        print_braille([1, 0, 0, 1, 1, 0], offset_x=10.0, offset_y=0.0)
        # -------------------------------------------------------------------------

        # 서비스 통신을 활성화하고 외부 입력을 대기하려면 아래 주석을 푸세요.
        # rclpy.spin(node)

    except KeyboardInterrupt:
        print("\nNode interrupted by user. Shutting down...")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"An unexpected error occurred: {e}")
    finally:
        pen_up()
        movej(Q1, vel=VELOCITY, acc=ACC)
        grip_open()
        rclpy.shutdown()

if __name__ == "__main__":
    main()
