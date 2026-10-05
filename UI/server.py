#python
import socket
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk, font as tkfont
import logging
import os
import hashlib
import secrets
from datetime import datetime

import psycopg2
#from deep_translator import GoogleTranslator
from KorToBraille.KorToBraille import KorToBraille



# ============================================================
# 서버 설정
# ============================================================

HOST = "0.0.0.0"
PORT = 5000

# PostgreSQL 설정
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "translation_db",
    "user": "postgres",
    "password": "postgres"
}


# ============================================================
# 로그 설정
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "server.log")

logger = logging.getLogger("server_logger")
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler(
    LOG_FILE,
    encoding="utf-8"
)

formatter = logging.Formatter(
    "%(asctime)s - %(message)s"
)

file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


# ============================================================
# 서버 상태
# ============================================================

server_socket = None
server_running = False

# 접속 중인 IP
connected_ips = set()

# 로그인 중인 사용자
logged_in_users = {}

# 최대 로그인 인원
MAX_USERS = 5

state_lock = threading.Lock()

TASKS_PAGE_SIZE = 5
tasks_page_combo = None
tasks_table = None
tasks_total_pages_label = None
tasks_request_button = None


# ============================================================
# 비밀번호 암호화
# ============================================================

def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000
    ).hex()

    return salt, password_hash


def verify_password(password, salt, stored_hash):
    _, password_hash = hash_password(password, salt)
    return password_hash == stored_hash


# ============================================================
# PostgreSQL
# ============================================================

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def initialize_database():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id VARCHAR(10) NOT NULL,
            user_pw VARCHAR(10) NOT NULL,
            user_name VARCHAR(10) NOT NULL,
            registry_date DATE NOT NULL,
            recent_enter_date DATE NOT NULL,

            -- 기본키
            CONSTRAINT pk_info_users
                PRIMARY KEY (user_id),

            -- user_id:
            -- 영어 소문자(a-z)와 숫자(0-9)만 허용
            -- 1~10자, 띄어쓰기 불가
            CONSTRAINT chk_info_users_user_id
                CHECK (user_id ~ '^[a-z0-9]{1,10}$'),

            -- user_pw:
            -- 영어 소문자(a-z)와 숫자(0-9)만 허용
            -- 1~10자, 띄어쓰기 불가
            CONSTRAINT chk_info_users_user_pw
                CHECK (user_pw ~ '^[a-z0-9]{1,10}$'),

            -- user_name:
            -- 한글 또는 영어만 허용
            -- 1~10자
            CONSTRAINT chk_info_users_user_name
                CHECK (user_name ~ '^[가-힣A-Za-z]{1,10}$')
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            exec_id BIGINT NOT NULL,
            user_id VARCHAR(10) NOT NULL,
            text TEXT NOT NULL,
            font_size INT NOT NULL,
            request_date DATE NOT NULL,
            translate_status INT NOT NULL DEFAULT 0,

            -- 기본키
            CONSTRAINT pk_exec_translations
                PRIMARY KEY (exec_id),

            -- 외래키
            -- exec_translations.user_id
            --     → info_users.user_id
            CONSTRAINT fk_exec_translations_user
                FOREIGN KEY (user_id)
                REFERENCES users(user_id),

            -- user_id:
            -- 영어 소문자(a-z)와 숫자(0-9)만 허용
            -- 1~10자, 띄어쓰기 불가
            CONSTRAINT chk_exec_translations_user_id
                CHECK (user_id ~ '^[a-z0-9]{1,10}$'),

            -- text:
            -- 한글과 공백만 허용
            -- 1~10자
            CONSTRAINT chk_exec_translations_text
                CHECK (text ~ '^[가-힣 ]{1,50}$'),

            -- 번역 상태: 정수형, 기본값 0
            CONSTRAINT chk_exec_translations_status
                CHECK (translate_status >= 0)
        )
    """)

    # 기존 DB에서도 text / font_size에 별도의 입력 제한을 두지 않는다.
    cur.execute("ALTER TABLE tasks DROP CONSTRAINT IF EXISTS chk_exec_translations_text")
    cur.execute("ALTER TABLE tasks DROP CONSTRAINT IF EXISTS chk_exec_translations_font_size")
    cur.execute("ALTER TABLE tasks ALTER COLUMN text TYPE TEXT")
    cur.execute("ALTER TABLE tasks ALTER COLUMN font_size DROP DEFAULT")
    cur.execute("ALTER TABLE tasks ALTER COLUMN font_size SET NOT NULL")

    # 기존 DB에도 translate_status 컬럼을 적용한다.
    cur.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS translate_result")
    cur.execute("""
        ALTER TABLE tasks
        ADD COLUMN IF NOT EXISTS translate_status INT NOT NULL DEFAULT 0
    """)
    cur.execute("ALTER TABLE tasks DROP CONSTRAINT IF EXISTS chk_exec_translations_result")
    cur.execute("ALTER TABLE tasks DROP CONSTRAINT IF EXISTS chk_exec_translations_status")
    cur.execute("""
        ALTER TABLE tasks
        ADD CONSTRAINT chk_exec_translations_status
        CHECK (translate_status >= 0)
    """)

    conn.commit()

    cur.close()
    conn.close()


# ============================================================
# 서버 IP
# ============================================================

def get_local_ip():
    try:
        temp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        temp_socket.connect(("8.8.8.8", 80))
        ip = temp_socket.getsockname()[0]
        temp_socket.close()
        return ip

    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


# ============================================================
# 로그 처리
# ============================================================

def get_tasks_page_data(page=1):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM tasks")
        total_rows = cur.fetchone()[0]
        total_pages = max(1, (total_rows + TASKS_PAGE_SIZE - 1) // TASKS_PAGE_SIZE)
        page = max(1, min(page, total_pages))
        offset = (page - 1) * TASKS_PAGE_SIZE
        cur.execute("""
            SELECT exec_id, user_id, text, font_size, request_date, translate_status
            FROM tasks
            ORDER BY exec_id ASC
            LIMIT %s OFFSET %s
        """, (TASKS_PAGE_SIZE, offset))
        return cur.fetchall(), total_pages
    except Exception as e:
        write_log(f"tasks 조회 실패 - 오류={e}")
        return [], 1
    finally:
        if cur: cur.close()
        if conn: conn.close()


def refresh_tasks_table(event=None):
    if tasks_table is None or tasks_page_combo is None:
        return
    try:
        page = int(tasks_page_combo.get())
    except (ValueError, TypeError):
        page = 1
    rows, total_pages = get_tasks_page_data(page)
    if page > total_pages:
        page = total_pages
        tasks_page_combo.set(str(page))
        rows, total_pages = get_tasks_page_data(page)
    for item in tasks_table.get_children():
        tasks_table.delete(item)
    for row in rows:
        tasks_table.insert("", tk.END, values=row)
    if tasks_total_pages_label is not None:
        tasks_total_pages_label.config(text=f"총 {total_pages} 페이지")


def write_log(message):
    if server_running:
        logger.info(message)

    root.after(0, refresh_log_screen)


def refresh_log_screen():
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

        recent = lines[-10:]

        log_text.config(state="normal")
        log_text.delete("1.0", tk.END)

        for line in recent:
            log_text.insert(tk.END, line)

        log_text.config(state="disabled")

        if tasks_page_combo is not None:
            _, total_pages = get_tasks_page_data(1)
            current = tasks_page_combo.get() or "1"
            tasks_page_combo["values"] = [str(i) for i in range(1, total_pages + 1)]
            try:
                current = min(int(current), total_pages)
            except ValueError:
                current = 1
            tasks_page_combo.set(str(current))
            refresh_tasks_table()

    except Exception:
        pass


# ============================================================
# 메시지 프로토콜
# ============================================================

def make_response(action, content):
    return f"{action} : {content}"


def parse_message(message):
    if " : " not in message:
        return None, None

    action, content = message.split(" : ", 1)

    return action.strip(), content.strip()


# ============================================================
# 회원가입
# ============================================================

def signup(content):
    try:
        # ID|PW|이름
        parts = content.split("|")

        if len(parts) != 3:
            return make_response("회원가입", "FAIL|입력 형식 오류")

        user_id = parts[0]
        password = parts[1]
        user_name = parts[2]

        if not user_id or not password or not user_name:
            return make_response("회원가입", "FAIL|모든 항목을 입력하세요")

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            "SELECT user_id FROM users WHERE user_id = %s",
            (user_id,)
        )

        if cur.fetchone():
            cur.close()
            conn.close()

            return make_response(
                "회원가입",
                "FAIL|이미 존재하는 ID입니다"
            )

        # 현재 CREATE TABLE의 user_pw VARCHAR(10) 및 CHECK 조건에 맞춰 저장
        cur.execute("""
            INSERT INTO users
            (user_id, user_pw, user_name, registry_date, recent_enter_date)
            VALUES (%s, %s, %s, CURRENT_DATE, CURRENT_DATE)
        """, (
            user_id,
            password,
            user_name
        ))

        conn.commit()

        cur.close()
        conn.close()

        write_log(
            f"회원가입 성공 - ID={user_id}, 이름={user_name}"
        )

        return make_response(
            "회원가입",
            "OK|회원가입이 완료되었습니다"
        )

    except Exception as e:
        return make_response(
            "회원가입",
            f"FAIL|DB 오류: {e}"
        )


# ============================================================
# 로그인
# ============================================================

def login(content, client_ip):
    try:
        parts = content.split("|")
        if len(parts) != 2:
            return make_response("로그인", "FAIL|입력 형식 오류")

        user_id, password = parts

        with state_lock:
            if len(logged_in_users) >= MAX_USERS:
                return make_response(
                    "로그인",
                    "FAIL|현재 최대 5명까지 로그인할 수 있습니다"
                )

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT user_id, user_pw, user_name
            FROM users
            WHERE user_id = %s
        """, (user_id,))
        row = cur.fetchone()

        if row is None:
            cur.close()
            conn.close()
            return make_response("로그인", "FAIL|ID 또는 PW가 잘못되었습니다")

        db_id, stored_password, user_name = row

        if password != stored_password:
            cur.close()
            conn.close()
            return make_response("로그인", "FAIL|ID 또는 PW가 잘못되었습니다")

        cur.execute("""
            UPDATE users
            SET recent_enter_date = CURRENT_DATE
            WHERE user_id = %s
        """, (user_id,))
        conn.commit()
        cur.close()
        conn.close()

        with state_lock:
            logged_in_users[user_id] = client_ip

        write_log(f"로그인 성공 - ID={user_id}, IP={client_ip}")
        return make_response("로그인", f"OK|{user_id}|{user_name}")

    except Exception as e:
        return make_response("로그인", f"FAIL|DB 오류: {e}")


# ============================================================
# 번역
# ============================================================
def braille_text_to_bits(text: str) -> list:
    result = []

    for char in text:
        code = ord(char)

        # 점자 유니코드 범위: U+2800 ~ U+283F
        if 0x2800 <= code <= 0x283F:
            value = code - 0x2800

            bits = [
                (value >> 0) & 1,  # 점 1
                (value >> 1) & 1,  # 점 2
                (value >> 2) & 1,  # 점 3
                (value >> 3) & 1,  # 점 4
                (value >> 4) & 1,  # 점 5
                (value >> 5) & 1   # 점 6
            ]

            result.append(bits)

        else:
            result.append(char)

    return result


def reverse_braille(text: str) -> str:
    """점자 문자열을 좌우반전"""

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

            # 점자 좌우반전
            reversed_value = (
                (p4 << 0) |
                (p5 << 1) |
                (p6 << 2) |
                (p1 << 3) |
                (p2 << 4) |
                (p3 << 5)
            )

            result.append(chr(0x2800 + reversed_value))

        else:
            result.append(char)

    # 문자열의 글자 순서도 반전
    return ''.join(result[::-1])


def translate(content, user_id):
    try:
        # 번역 요청 형식: 번역할 텍스트|폰트 크기
        parts = content.split("|", 1)

        if len(parts) != 2:
            return make_response("번역", "FAIL|번역 요청 형식 오류")

        text = parts[0]
        font_size_text = parts[1]

        try:
            font_size = int(font_size_text)
        except ValueError:
            return make_response("번역", "FAIL|폰트 크기 형식 오류")

        if not text:
            return make_response("번역", "FAIL|번역할 내용을 입력하세요")

        if any(not ("가" <= char <= "힣") and char != " " for char in text):
            return make_response("번역", "FAIL|번역 내용은 한글과 공백만 입력할 수 있습니다")

        if not any("가" <= char <= "힣" for char in text):
            return make_response("번역", "FAIL|번역 내용에는 한글이 포함되어야 합니다")

        text_k = text #입력된 한글 텍스트
        b = KorToBraille() #점자 번역 객체
        text_b = b.korTranslate(text_k) #점자 번역 수행
        result = text_b # 화면상 점자 출력은 반전 없이
        #어차피 로봇 내부에서 점자 번역 수행하므로 굳이 반전 및 bit 화까지는 진행 x
        #text_b_reverse = reverse_braille(text_b) #점자 반전 수행
        #bit_b = braille_text_to_bits(text_b_reverse) # 유니코드 점자 bit 화
    
        ##원래는 맨 끝 eol 문자였으나, 반전으로 앞으로 왔으니 날려줌.
        #if bit_b[0] == [0, 0, 0, 0, 0, 0]:
        #    bit_b.pop(0)

        #########
        '''
        여기서 로봇 동작 시키고
        결과까지 리턴 받아야 함(성공/실패 여부) <- 논의 후 구현 여부 결정.
        -> 서버에서 로봇 동장시키지 않고, DB 상태 값을 이용하는 방식으로 결정
        '''
        #########

        conn = get_db_connection()
        cur = conn.cursor()

        # exec_id는 1부터 시작하는 오름차순 번호로 생성한다.
        # 동시 요청에서도 중복되지 않도록 tasks 테이블을 잠근다.
        cur.execute("LOCK TABLE tasks IN EXCLUSIVE MODE")
        cur.execute("SELECT COALESCE(MAX(exec_id), 0) + 1 FROM tasks")
        exec_id = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO tasks
            (exec_id, user_id, text, font_size, request_date, translate_status)
            VALUES (%s, %s, %s, %s, CURRENT_DATE, %s)
        """, (exec_id, user_id, text, font_size, 0))
        # translate_status value
        # 0 : 클라 -> 서버 요청 상태
        # 1 : 서버 -> 로봇 요청 상태
        # 2 : 로봇 작업 수행 중 상태
        # 3 : 로봇 작업 완료 상태 ; 성공
        # 4 : 로봇 작업 완료 상태 ; 실패

        conn.commit()
        cur.close()
        conn.close()

        write_log(
            f"번역 작업 - ID={user_id}, 폰트크기={font_size}, "
            f"입력={text}, 결과={result}"
        )
        return make_response("번역", f"OK|{result}")

    except Exception as e:
        write_log(f"번역 실패 - ID={user_id}, 오류={e}")
        return make_response("번역", f"FAIL|번역 오류: {e}")


# ============================================================
# 작업 요청
# ============================================================

def request_task(exec_id):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # 선택한 작업을 잠근 뒤 현재 상태를 확인한다.
        cur.execute("""
            SELECT translate_status
            FROM tasks
            WHERE exec_id = %s
            FOR UPDATE
        """, (exec_id,))
        row = cur.fetchone()

        if row is None:
            conn.rollback()
            return False, "선택한 작업을 찾을 수 없습니다."

        selected_status = row[0]

        if selected_status != 0:
            conn.rollback()
            return False, "상태가 0 인 작업을 선택해 주세요"

        # 전체 tasks에서 status=1인 작업을 확인한다.
        cur.execute("""
            SELECT exec_id
            FROM tasks
            WHERE translate_status = 1
            ORDER BY exec_id ASC
            LIMIT 1
        """)
        running_row = cur.fetchone()

        if running_row is not None:
            running_exec_id = running_row[0]
            conn.rollback()
            return False, (
                f"exec_id {running_exec_id} 의 작업이 진행 중입니다. "
                "잠시 후 다시 시도해 주세요"
            )

        cur.execute("""
            UPDATE tasks
            SET translate_status = 1
            WHERE exec_id = %s AND translate_status = 0
        """, (exec_id,))

        if cur.rowcount != 1:
            conn.rollback()
            return False, "상태가 0 인 작업을 선택해 주세요"

        conn.commit()
        write_log(f"작업 요청 - exec_id={exec_id}, status=0 -> 1")
        return True, f"로봇에 exec_id {exec_id} 를 작업 요청하였습니다."

    except Exception as e:
        if conn:
            conn.rollback()
        write_log(f"작업 요청 실패 - exec_id={exec_id}, 오류={e}")
        return False, f"작업 요청 중 오류가 발생했습니다: {e}"
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ============================================================
# 사용자 작업내역 조회
# ============================================================

def get_user_tasks(user_id, page=1):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM tasks WHERE user_id = %s", (user_id,))
        total_rows = cur.fetchone()[0]
        total_pages = max(1, (total_rows + TASKS_PAGE_SIZE - 1) // TASKS_PAGE_SIZE)
        page = max(1, min(page, total_pages))
        offset = (page - 1) * TASKS_PAGE_SIZE
        cur.execute("""
            SELECT exec_id, text, font_size, request_date, translate_status
            FROM tasks
            WHERE user_id = %s
            ORDER BY exec_id ASC
            LIMIT %s OFFSET %s
        """, (user_id, TASKS_PAGE_SIZE, offset))
        rows = cur.fetchall()
        content = ";;".join("|".join(str(v) for v in row) for row in rows)
        write_log(f"상태 조회 - ID={user_id}, page={page}, 작업수={len(rows)}")
        return True, f"{total_pages}|{content}"
    except Exception as e:
        write_log(f"상태 조회 실패 - ID={user_id}, 오류={e}")
        return False, f"DB 오류: {e}"
    finally:
        if cur: cur.close()
        if conn: conn.close()


# ============================================================
# 작업 거절
# ============================================================

def reject_task(exec_id):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT translate_status
            FROM tasks
            WHERE exec_id = %s
            FOR UPDATE
        """, (exec_id,))
        row = cur.fetchone()

        if row is None:
            conn.rollback()
            return False, "선택한 작업을 찾을 수 없습니다."

        if row[0] != 0:
            conn.rollback()
            return False, "상태가 0 인 작업을 선택해 주세요"

        cur.execute("""
            UPDATE tasks
            SET translate_status = 2
            WHERE exec_id = %s AND translate_status = 0
        """, (exec_id,))

        if cur.rowcount != 1:
            conn.rollback()
            return False, "상태가 0 인 작업을 선택해 주세요"

        conn.commit()
        write_log(f"작업 거절 - exec_id={exec_id}, status=0 -> 2")
        return True, f"exec_id {exec_id} 의 작업을 거절하였습니다."

    except Exception as e:
        if conn: conn.rollback()
        write_log(f"작업 거절 실패 - exec_id={exec_id}, 오류={e}")
        return False, f"작업 거절 중 오류가 발생했습니다: {e}"
    finally:
        if cur: cur.close()
        if conn: conn.close()


# ============================================================
# 로그아웃
# ============================================================

def logout(content, client_ip):
    user_id = content.strip()

    with state_lock:

        if user_id in logged_in_users:
            del logged_in_users[user_id]

        connected_ips.discard(client_ip)

    write_log(
        f"로그아웃 - ID={user_id}, IP={client_ip}"
    )

    return make_response(
        "로그아웃",
        "OK|로그아웃 완료"
    )


# ============================================================
# 클라이언트 처리
# ============================================================

def handle_client(client_socket, client_address):
    client_ip = client_address[0]
    current_user = None
    ip_registered = False
    rejected_duplicate_ip = False

    try:
        client_socket.settimeout(600)

        while True:

            data = client_socket.recv(4096)

            if not data:
                break

            message = data.decode("utf-8").strip()

            action, content = parse_message(message)

            if action is None:
                response = make_response(
                    "접속",
                    "FAIL|잘못된 메시지 형식"
                )

                client_socket.sendall(
                    response.encode("utf-8")
                )

                continue

            # 서버 OFF
            if not server_running:
                response = make_response(
                    action,
                    "FAIL|현재 서버가 OFF 상태입니다"
                )

                client_socket.sendall(
                    response.encode("utf-8")
                )

                continue

            write_log(
                f"요청 - IP={client_ip}, "
                f"요청={action}, 내용={content}"
            )

            # ------------------------------------------------
            # 접속
            # ------------------------------------------------

            if action == "접속":

                with state_lock:

                    if client_ip in connected_ips:
                        # 이미 같은 IP가 접속 중이면 기존 연결은 그대로 유지한다.
                        rejected_duplicate_ip = True
                        response = make_response(
                            "접속",
                            "FAIL|동일 IP 접속 차단"
                        )
                        write_log(
                            f"동일 IP 접속 차단 - IP={client_ip}"
                        )

                    else:
                        # 로그인 여부와 관계없이 접속 시점에 IP 등록
                        connected_ips.add(client_ip)
                        ip_registered = True
                        response = make_response(
                            "접속",
                            "OK|서버 접속 성공"
                        )

                client_socket.sendall(
                    response.encode("utf-8")
                )

                # 중복 IP로 차단된 소켓은 즉시 종료한다.
                # 그래야 차단된 클라이언트가 로그인/번역 등의 요청을 계속 보낼 수 없다.
                if rejected_duplicate_ip:
                    break

            # ------------------------------------------------
            # 로그인
            # ------------------------------------------------

            elif action == "로그인":

                response = login(
                    content,
                    client_ip
                )

                if response.startswith("로그인 : OK|"):
                    current_user = content.split("|")[0]

                client_socket.sendall(
                    response.encode("utf-8")
                )

            # ------------------------------------------------
            # 회원가입
            # ------------------------------------------------

            elif action == "회원가입":

                response = signup(content)

                client_socket.sendall(
                    response.encode("utf-8")
                )

            # ------------------------------------------------
            # 번역
            # ------------------------------------------------

            elif action == "번역":

                if current_user is None:
                    response = make_response(
                        "번역",
                        "FAIL|로그인이 필요합니다"
                    )

                else:
                    response = translate(
                        content,
                        current_user
                    )

                client_socket.sendall(
                    response.encode("utf-8")
                )

            # ------------------------------------------------
            # 상태 조회
            # ------------------------------------------------

            elif action == "상태조회":

                if current_user is None:
                    response = make_response(
                        "상태조회",
                        "FAIL|로그인이 필요합니다"
                    )
                else:
                    parts = content.split("|", 1)
                    requested_user = parts[0].strip()
                    try:
                        page = int(parts[1]) if len(parts) == 2 else 1
                    except ValueError:
                        page = 1
                    if requested_user != current_user:
                        response = make_response(
                            "상태조회",
                            "FAIL|현재 로그인 사용자만 조회할 수 있습니다"
                        )
                    else:
                        success, result = get_user_tasks(current_user, page)
                        response = make_response(
                            "상태조회",
                            f"OK|{result}" if success else f"FAIL|{result}"
                        )

                client_socket.sendall(response.encode("utf-8"))

            # ------------------------------------------------
            # 로그아웃
            # ------------------------------------------------

            elif action == "로그아웃":

                response = logout(
                    content,
                    client_ip
                )

                current_user = None

                client_socket.sendall(
                    response.encode("utf-8")
                )

            else:

                response = make_response(
                    action,
                    "FAIL|지원하지 않는 요청입니다"
                )

                client_socket.sendall(
                    response.encode("utf-8")
                )

    except socket.timeout:
        try:
            response = make_response(
                "접속종료",
                "TIMEOUT|일정 시간 동안 요청이 없어 서버와의 접속이 자동 해제되었습니다."
            )
            client_socket.sendall(response.encode("utf-8"))
        except Exception:
            pass

        write_log(f"자동 접속 해제 - IP={client_ip}, 사유=소켓 timeout")

    except Exception as e:

        write_log(
            f"클라이언트 처리 오류 - "
            f"IP={client_ip}, 오류={e}"
        )

    finally:

        # 이 소켓이 실제로 IP를 등록한 경우에만 등록 정보를 해제한다.
        # 동일 IP 접속 차단으로 생성된 소켓은 기존 접속자의 IP를 건드리지 않는다.
        if ip_registered:
            with state_lock:
                if current_user is not None and current_user in logged_in_users:
                    del logged_in_users[current_user]
                connected_ips.discard(client_ip)

            try:
                client_socket.close()
            except Exception:
                pass

            write_log(
                f"접속 종료 - IP={client_ip}"
            )
        else:
            try:
                client_socket.close()
            except Exception:
                pass

            # 중복 IP 차단은 별도의 접속 종료 로그를 남기지 않는다.
            if not rejected_duplicate_ip:
                write_log(
                    f"접속 종료 - IP={client_ip}"
                )


# ============================================================
# 서버 시작
# ============================================================

def start_socket_server():

    global server_socket

    try:
        server_socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        server_socket.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1
        )

        server_socket.bind(
            (HOST, PORT)
        )

        server_socket.listen(20)

        write_log(
            f"서버 소켓 시작 - PORT={PORT}"
        )

        while True:

            client_socket, client_address = (
                server_socket.accept()
            )

            thread = threading.Thread(
                target=handle_client,
                args=(
                    client_socket,
                    client_address
                ),
                daemon=True
            )

            thread.start()

    except Exception as e:

        write_log(
            f"서버 소켓 오류 - {e}"
        )


# ============================================================
# 서버 ON / OFF
# ============================================================

def toggle_server():

    global server_running

    server_running = not server_running

    if server_running:

        server_button.config(
            text="SERVER ON",
            bg="green",
            fg="white"
        )

        write_log("========== SERVER ON ==========")

    else:

        server_button.config(
            text="SERVER OFF",
            bg="red",
            fg="white"
        )

        write_log("========== SERVER OFF ==========")


# ============================================================
# GUI
# ============================================================

root = tk.Tk()
root.title("Translation Server")
root.geometry("700x550")

# 서버 IP
local_ip = get_local_ip()

top_header = tk.Frame(root)
top_header.pack(fill="x", padx=10, pady=(10, 5))

date_label = tk.Label(
    top_header,
    text=datetime.now().strftime("%Y-%m-%d"),
    font=("Arial", 13, "bold")
)
date_label.place(relx=0.5, rely=0.5, anchor="center")

# 로그인 사용자 표기를 날짜칸 오른쪽 끝에 배치
status_label = tk.Label(
    top_header,
    text="로그인 사용자 : 0 / 5",
    font=("Arial", 12)
)
status_label.pack(side="right", anchor="e")

def update_server_date():
    date_label.config(text=datetime.now().strftime("%Y-%m-%d"))
    root.after(1000, update_server_date)

update_server_date()

ip_label = tk.Label(
    root,
    text=f"현재 서버 IP : {local_ip}",
    font=("Arial", 14)
)

ip_label.pack(pady=5)


port_label = tk.Label(
    root,
    text=f"PORT : {PORT}",
    font=("Arial", 12)
)

port_label.pack()


# 서버 ON/OFF 버튼
server_button = tk.Button(
    root,
    text="SERVER OFF",
    bg="red",
    fg="white",
    font=("Arial", 14, "bold"),
    width=20,
    command=toggle_server
)

server_button.pack(pady=15)


# 현재 로그인 인원
# 로그인 사용자 표기는 상단 날짜칸 오른쪽 끝으로 이동됨.
def update_status():

    with state_lock:
        count = len(logged_in_users)

    status_label.config(
        text=f"로그인 사용자 : {count} / {MAX_USERS}"
    )

    root.after(1000, update_status)


# tasks 제목 / 페이지 / 작업 요청
tasks_header_frame = tk.Frame(root)
tasks_header_frame.pack(fill="x", padx=10, pady=(10, 3))

# "Page: [combo box] 총 1 페이지"를 Tasks 제목의 왼쪽 끝에 배치한다.
tasks_page_frame = tk.Frame(tasks_header_frame)
tasks_page_frame.pack(side="left", anchor="w")

tk.Label(
    tasks_page_frame,
    text="Page:",
    font=("Arial", 11)
).pack(side="left", padx=(0, 5))

tasks_page_combo = ttk.Combobox(
    tasks_page_frame,
    state="readonly",
    width=6
)
tasks_page_combo.pack(side="left")
tasks_page_combo.bind("<<ComboboxSelected>>", refresh_tasks_table)

tasks_total_pages_label = tk.Label(
    tasks_page_frame,
    text="총 1 페이지",
    font=("Arial", 10)
)
tasks_total_pages_label.pack(side="left", padx=8)

tasks_title = tk.Label(
    tasks_header_frame,
    text="Tasks",
    font=("Arial", 13, "bold")
)
tasks_title.place(relx=0.5, rely=0.5, anchor="center")

def on_task_request():
    selected_items = tasks_table.selection()

    if not selected_items:
        messagebox.showwarning("작업 요청", "작업을 선택해 주세요")
        return

    values = tasks_table.item(selected_items[0], "values")
    exec_id = values[0]
    status = int(values[5])

    if status != 0:
        messagebox.showwarning(
            "작업 요청",
            "상태가 0 인 작업을 선택해 주세요"
        )
        return

    success, message = request_task(exec_id)

    if success:
        refresh_tasks_table()
        messagebox.showinfo("작업 요청", message)
    else:
        refresh_tasks_table()
        messagebox.showwarning("작업 요청", message)

tasks_button_frame = tk.Frame(tasks_header_frame)
tasks_button_frame.pack(side="right", anchor="e")

tasks_request_button = tk.Button(
    tasks_button_frame,
    text="작업 요청",
    font=("Arial", 10, "bold"),
    command=on_task_request
)
tasks_request_button.pack(side="left", padx=(0, 5))

def on_task_reject():
    selected_items = tasks_table.selection()

    if not selected_items:
        messagebox.showwarning("작업 거절", "작업을 선택해 주세요")
        return

    values = tasks_table.item(selected_items[0], "values")
    exec_id = values[0]
    status = int(values[5])

    if status != 0:
        messagebox.showwarning(
            "작업 거절",
            "상태가 0 인 작업을 선택해 주세요"
        )
        return

    success, message = reject_task(exec_id)

    if success:
        refresh_tasks_table()
        messagebox.showinfo("작업 거절", message)
    else:
        refresh_tasks_table()
        messagebox.showwarning("작업 거절", message)

tasks_reject_button = tk.Button(
    tasks_button_frame,
    text="작업 거절",
    font=("Arial", 10, "bold"),
    command=on_task_reject
)
tasks_reject_button.pack(side="left")

tasks_frame = tk.Frame(root)
tasks_frame.pack(padx=10, pady=3, fill="both", expand=True)

tasks_columns = (
    "exec_id",
    "user_id",
    "text",
    "font_size",
    "request_date",
    "translate_status"
)
tasks_table = ttk.Treeview(
    tasks_frame,
    columns=tasks_columns,
    show="headings",
    height=5
)

# 칼럼 폭은 칼럼명의 표시 폭을 기준으로 하고 text를 가장 크게 설정한다.
header_font = tkfont.Font(family="Arial", size=10)
column_titles = {
    "exec_id": "exec_id",
    "user_id": "user_id",
    "text": "text",
    "font_size": "font_size",
    "request_date": "request_date",
    "translate_status": "translate_status"
}
base_widths = {
    col: max(80, header_font.measure(title) + 24)
    for col, title in column_titles.items()
}
base_widths["text"] = max(base_widths["text"] * 2, 180)

for col in tasks_columns:
    tasks_table.heading(col, text=column_titles[col])
    tasks_table.column(
        col,
        width=base_widths[col],
        minwidth=base_widths[col],
        anchor="center"
    )

tasks_scrollbar = ttk.Scrollbar(
    tasks_frame,
    orient="vertical",
    command=tasks_table.yview
)
tasks_table.configure(yscrollcommand=tasks_scrollbar.set)
tasks_table.pack(side="left", fill="both", expand=True)
tasks_scrollbar.pack(side="right", fill="y")

# 로그
log_title = tk.Label(root, text="최근 로그 10개", font=("Arial", 13, "bold"))
log_title.pack(pady=(5, 3))

log_text = scrolledtext.ScrolledText(
    root, width=80, height=7, state="disabled"
)
log_text.pack(padx=10, pady=3, fill="both", expand=True)


# DB 초기화
try:
    initialize_database()
except Exception as e:

    messagebox.showerror(
        "DB 오류",
        f"PostgreSQL 연결에 실패했습니다.\n\n{e}"
    )

    root.destroy()
    raise SystemExit


# 소켓 서버 스레드
server_thread = threading.Thread(
    target=start_socket_server,
    daemon=True
)

server_thread.start()

update_status()
refresh_log_screen()

root.mainloop()