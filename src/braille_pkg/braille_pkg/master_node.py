import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Int32MultiArray, Bool
from KorToBraille.KorToBraille import KorToBraille
import threading
import time
import psycopg2

class MasterNode(Node):
    def __init__(self):
        super().__init__('master_node')
        
        # 1. 퍼블리셔 (각 제어 노드에 명령 하달)
        self.write_cmd_pub = self.create_publisher(String, "/write_cmd", 10)
        self.braille_cmd_pub = self.create_publisher(Int32MultiArray, "/braille_cmd", 10)
        
        # 2. 서브스크라이버 (제어 노드들로부터 완료 신호 수신)
        self.create_subscription(Bool, "/write_done", self.write_done_callback, 10)
        self.create_subscription(Bool, "/braille_done", self.braille_done_callback, 10)
        
        # 상태 관리 변수
        self.is_working = False
        self.current_text = ""
        self.flat_bits = []
        
        self.waiting_for_write = False
        self.waiting_for_braille = False

        self.get_logger().info("마스터 노드(테스트 모드) 가동 완료")

    # ==========================================
    # 점자 변환 및 반전 알고리즘 (server.py 기준)
    # ==========================================
    def reverse_braille(self, text: str) -> str:
        """점자 유니코드 좌우 반전 및 문자열 순서 반전"""
        result = []
        for char in text:
            code = ord(char)
            if 0x2800 <= code <= 0x283F:
                value = code - 0x2800
                p1 = (value >> 0) & 1
                p2 = (value >> 1) & 1
                p3 = (value >> 2) & 1
                p4 = (value >> 3) & 1
                p5 = (value >> 4) & 1
                p6 = (value >> 5) & 1

                reversed_value = (
                    (p4 << 0) | (p5 << 1) | (p6 << 2) |
                    (p1 << 3) | (p2 << 4) | (p3 << 5)
                )
                result.append(chr(0x2800 + reversed_value))
            else:
                result.append(char)
        return ''.join(result[::-1])

    def braille_text_to_bits(self, text: str) -> list:
        """점자 유니코드를 6비트 리스트로 변환"""
        result = []
        for char in text:
            code = ord(char)
            if 0x2800 <= code <= 0x283F:
                value = code - 0x2800
                bits = [
                    (value >> 0) & 1, (value >> 1) & 1, (value >> 2) & 1,
                    (value >> 3) & 1, (value >> 4) & 1, (value >> 5) & 1
                ]
                result.append(bits)
            else:
                result.append(char)
        return result

    # ==========================================
    # 작업 시작 함수
    # ==========================================
    def process_user_input(self, user_text: str):
        self.is_working = True
        self.current_text = user_text
        self.get_logger().info(f"입력 텍스트 처리 시작: '{self.current_text}'")

        # 1. 한글 -> 점자 변환 -> 반전 -> 비트 평탄화
        b = KorToBraille()
        text_b = b.korTranslate(self.current_text)
        text_b_reverse = self.reverse_braille(text_b)
        bit_b_2d = self.braille_text_to_bits(text_b_reverse)

        # 맨 앞 EOL 빈 블록 제거
        if bit_b_2d and bit_b_2d[0] == [0, 0, 0, 0, 0, 0]:
            bit_b_2d.pop(0)

        # 1차원 배열로 평탄화
        self.flat_bits = [bit for block in bit_b_2d for bit in block]
        self.get_logger().info(f"점자 비트 생성 완료 (총 {len(self.flat_bits)//6}글자)")

        # 2. 글쓰기 노드로 명령 토픽 발행
        msg = String()
        msg.data = self.current_text
        self.waiting_for_write = True
        self.write_cmd_pub.publish(msg)
        self.get_logger().info("[1단계] 글쓰기 명령 토픽(/write_cmd) 발행")

    # ==========================================
    # 콜백 함수들
    # ==========================================
    def write_done_callback(self, msg):
        if self.waiting_for_write:
            self.waiting_for_write = False
            if msg.data:
                self.get_logger().info("글쓰기 완료 수신 이어서 점자 타각 시작")
                
                # 3. 점자 타각 노드로 명령 토픽 발행
                braille_msg = Int32MultiArray()
                braille_msg.data = self.flat_bits
                self.waiting_for_braille = True
                self.braille_cmd_pub.publish(braille_msg)
                self.get_logger().info("[2단계] 점자 타각 명령 토픽(/braille_cmd) 발행")
            else:
                self.get_logger().error("글쓰기 실패. 공정을 중단합니다.")
                self.is_working = False

    def braille_done_callback(self, msg):
        if self.waiting_for_braille:
            self.waiting_for_braille = False
            if msg.data:
                self.get_logger().info("[최종 완료] 글쓰기 및 점자 타각 공정이 모두 성공적으로 끝났습니다!")
            else:
                self.get_logger().error("점자 타각 실패.")
            
            # 다음 입력을 받을 수 있도록 상태 초기화
            self.is_working = False
            print("\n" + "="*50)


# ==========================================
# 사용자 터미널 입력 스레드
# ==========================================
def terminal_input_thread(node: MasterNode):
    time.sleep(1.0)
    while rclpy.ok():
        if not node.is_working:
            try:
                text = input("\n작성할 한글 문장을 입력하세요 (종료: q) : ").strip()
                if text.lower() == 'q':
                    print("테스트를 종료합니다.")
                    rclpy.shutdown()
                    break
                if not text:
                    continue
                
                node.process_user_input(text)
            except (KeyboardInterrupt, EOFError):
                break
        else:
            time.sleep(0.5)


def main(args=None):
    rclpy.init(args=args)
    node = MasterNode()

    # 터미널 input을 위한 백그라운드 스레드 가동
    input_t = threading.Thread(target=terminal_input_thread, args=(node,), daemon=True)
    input_t.start()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == '__main__':
    main()