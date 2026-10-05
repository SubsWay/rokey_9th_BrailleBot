import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient

# 방금 만든 액션 인터페이스 임포트
from custom_interfaces.action import PrintBraille

# 작성해주셨던 번역 함수 임포트 (파일 경로에 맞춰 수정하세요)
from translate_to_braile import braille_text_to_bits, reverse_braille
from KorToBraille.KorToBraille import KorToBraille

class BrailleActionClient(Node):
    def __init__(self):
        super().__init__('braille_action_client')
        self._action_client = ActionClient(self, PrintBraille, 'print_braille_action')

    def send_goal(self, bit_b_2d):
        """2차원 배열(bit_b)을 받아 1차원으로 평탄화 후 전송"""
        self.get_logger().info('Action 서버 연결 대기 중...')
        self._action_client.wait_for_server()

        # [[1,0,0,1,1,0], [0,1,...]] 형태의 2차원 배열을 1차원으로 평탄화 (Flatten)
        flat_bits = [bit for block in bit_b_2d for bit in block]

        goal_msg = PrintBraille.Goal()
        goal_msg.braille_data = flat_bits

        self.get_logger().info(f'작업 전송 중... 총 {len(flat_bits)//6} 글자')

        # 피드백 콜백 지정
        self._send_goal_future = self._action_client.send_goal_async(
            goal_msg, 
            feedback_callback=self.feedback_callback
        )
        self._send_goal_future.add_done_callback(self.goal_response_callback)

    def feedback_callback(self, feedback_msg):
        """로봇에서 점자 하나를 찍을 때마다 실시간으로 날아오는 피드백"""
        feedback = feedback_msg.feedback
        self.get_logger().info(
            f"[GUI 진행률 표시용] 진행: {feedback.progress_percentage:.1f}% "
            f"({feedback.current_character} / {feedback.total_characters} 글자 완료)"
        )

    def goal_response_callback(self, future):
        """서버가 요청을 수락했는지 거절했는지 확인"""
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().error('로봇이 요청을 거절했습니다.')
            return

        self.get_logger().info('로봇이 작업을 수락했습니다. 출력을 시작합니다.')
        self._get_result_future = goal_handle.get_result_async()
        self._get_result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        """작업 최종 완료 시 결과 수신"""
        result = future.result().result
        if result.success:
            self.get_logger().info(f'작업 최종 성공: {result.message}')
            # TODO: DB의 translate_result 를 TRUE로 업데이트 하는 로직 연동 가능
        else:
            self.get_logger().error(f'작업 실패 또는 취소됨: {result.message}')
        
        # 테스트 종료용
        rclpy.shutdown()

def main(args=None):
    rclpy.init(args=args)
    action_client = BrailleActionClient()

    # --- 기존 번역 스크립트(translate_to_braile.py) 로직 ---
    text_k = "나는 로키"
    b = KorToBraille()
    text_b = b.korTranslate(text_k)
    text_b_reverse = reverse_braille(text_b)
    bit_b = braille_text_to_bits(text_b_reverse)

    if len(bit_b) > 0 and bit_b[0] == [0, 0, 0, 0, 0, 0]:
        bit_b.pop(0)
    # --------------------------------------------------------

    # 클라이언트 노드를 통해 전송
    action_client.send_goal(bit_b)

    # 비동기 실행을 위한 스핀
    rclpy.spin(action_client)

if __name__ == '__main__':
    main()