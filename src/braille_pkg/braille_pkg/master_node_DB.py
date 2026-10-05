import json
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Int32MultiArray, Bool
from KorToBraille.KorToBraille import KorToBraille
import psycopg2

# ==========================================
# DB 연결 설정 (사용하시는 환경에 맞게 테이블명/컬럼명 수정 필요)
# ==========================================
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "translation_db",
    "user": "postgres",
    "password": "postgres"
}

class MasterNode(Node):
    def __init__(self):
        super().__init__('master_node')
        
        # 1. 퍼블리셔 (통합 제어 노드에 명령 하달)
        self.write_cmd_pub = self.create_publisher(String, "/write_cmd", 10)
        self.braille_cmd_pub = self.create_publisher(Int32MultiArray, "/braille_cmd", 10)
        
        # 2. 서브스크라이버 (제어 노드로부터 완료 신호 수신)
        self.create_subscription(Bool, "/write_done", self.write_done_callback, 10)
        self.create_subscription(Bool, "/braille_done", self.braille_done_callback, 10)
        
        # 3. 상태 관리 변수
        self.is_working = False
        self.current_exec_id = None
        self.current_text = ""
        self.font_size = 20
        self.flat_bits = []
        
        self.waiting_for_write = False
        self.waiting_for_braille = False

        # 4. DB 폴링용 타이머 (1.0초마다 체크)
        self.check_count = 0
        self.db_timer = self.create_timer(1.0, self.check_database)

        self.get_logger().info("=" * 60)
        self.get_logger().info("마스터 노드 가동 완료: DB 작업 대기 중...")
        self.get_logger().info("=" * 60)

    # ==========================================
    # 점자 변환 및 반전 알고리즘
    # ==========================================
    def reverse_braille(self, text: str) -> str:
        """점자 유니코드 좌우 반전 및 문자열 순서 반전"""
        result = []
        for char in text:
            code = ord(char)
            if 0x2800 <= code <= 0x283F:
                value = code - 0x2800
                p1, p2, p3 = (value >> 0) & 1, (value >> 1) & 1, (value >> 2) & 1
                p4, p5, p6 = (value >> 3) & 1, (value >> 4) & 1, (value >> 5) & 1

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
    # DB 폴링 및 작업 시작
    # ==========================================
    def check_database(self):
        """주기적으로 DB를 확인하여 translate_result == 1 인 데이터를 가져옴"""
        if self.is_working:
            return  # 현재 로봇이 작업 중이면 대기
        if self.write_cmd_pub.get_subscription_count() == 0:
            # 아직 로봇 제어 노드가 통신 준비가 안 되었으므로 다음 주기로 넘김
            return

        self.check_count += 1

        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()
            
            # translate_result가 FALSE인 가장 오래된 작업 조회 (테이블명 tasks 가정)
            cur.execute("""
                SELECT exec_id, user_id,  text, font_size FROM tasks 
                WHERE translate_status = 1 
                ORDER BY request_date ASC LIMIT 1
            """)
            task = cur.fetchone()
            
            if task:
                self.is_working = True
                self.current_exec_id = task[0]
                self.current_text = task[2]
                self.font_size = int(task[3])

                self.get_logger().info("=" * 60)
                self.get_logger().info(f"[DB 작업 감지] ID: {self.current_exec_id}, 텍스트: '{self.current_text}', 폰트 사이즈: '{self.font_size}'")
                self.get_logger().info("=" * 60)
                
                # 1. 점자 번역 수행
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

                # 2. 글쓰기 제어 노드로 토픽 발행
                braille_msg = Int32MultiArray()
                braille_msg.data = self.flat_bits + [self.font_size]
                self.waiting_for_braille = True
                self.braille_cmd_pub.publish(braille_msg)
                self.get_logger().info("점자 타각 명령 토픽(/braille_cmd) 발행 완료")

            cur.close()
            conn.close()
        except Exception as e:
            # DB 연결 실패 등의 에러 출력
            self.get_logger().error(f"DB 폴링 오류: {e}")

    # ==========================================
    # 제어 완료 콜백
    # ==========================================
    def braille_done_callback(self, msg):
        if self.waiting_for_braille:
            self.waiting_for_braille = False
            if msg.data:
                self.get_logger().info("점자 타각과 종이 뒤집기 완료 수신! 이어서 글쓰기 시작")
                
                # 3. 점자가 끝나면 글쓰기 제어 노드로 명령 토픽 발행
                msg_write = String()
                payload = {"text": self.current_text, "size": self.font_size}
                msg_write.data = json.dumps(payload)


                self.waiting_for_write = True
                self.write_cmd_pub.publish(msg_write)
                self.get_logger().info("글쓰기 명령 토픽(/write_cmd) 발행 완료")
            else:
                self.get_logger().error("점자 타각 실패. 공정을 중단합니다.")
                self.finish_task(success=False)

    def write_done_callback(self, msg):
        if self.waiting_for_write:
            self.waiting_for_write = False
            if msg.data:
                self.get_logger().info("점자 타각 및 글쓰기과 도장 공정이 모두 성공적으로 끝났습니다!")
                self.finish_task(success=True)
            else:
                self.get_logger().error("글쓰기 실패.")
                self.finish_task(success=False)

    def finish_task(self, success):
        """모든 공정 종료 후 DB 업데이트 (성공: 3, 실패: 4)"""
        if self.current_exec_id:
            try:
                conn = psycopg2.connect(**DB_CONFIG)
                cur = conn.cursor()
                
                # 성공 여부에 따라 상태값 결정
                new_status = 3 if success else 4
                
                cur.execute("""
                    UPDATE tasks 
                    SET translate_status = %s
                    WHERE exec_id = %s
                """, (new_status, self.current_exec_id))
                
                conn.commit()
                cur.close()
                conn.close()
                status_str = "성공(3)" if success else "에러/실패(4)"
                self.get_logger().info(f"DB 상태 갱신 완료 (ID: {self.current_exec_id}, translate_status = {status_str})")
            except Exception as e:
                self.get_logger().error(f"DB 갱신 오류: {e}")
        
        self.is_working = False
        self.current_exec_id = None
        
        self.get_logger().info("=" * 60)
        self.get_logger().info("다음 DB 작업을 대기합니다...")


def main(args=None):
    rclpy.init(args=args)
    node = MasterNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\nCtrl+C 감지. 마스터 노드를 종료합니다.")
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == '__main__':
    main()