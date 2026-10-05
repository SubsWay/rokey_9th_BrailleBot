import socket
import threading
import queue
import tkinter as tk
from tkinter import messagebox, ttk
from datetime import datetime


# ============================================================
# 서버 설정
# ============================================================

PORT = 5000

sock = None
connected = False
logged_in = False
current_user = None
current_user_name = None
response_queue = queue.Queue()


# ============================================================
# 통신
# ============================================================

def send_request(action, content):
    global sock

    if sock is None:
        return None

    try:
        sock.sendall(
            f"{action} : {content}".encode("utf-8")
        )

        while True:
            response = response_queue.get()
            if response is None:
                return None

            if handle_server_disconnect_message(response):
                return None

            return response

    except Exception as e:
        messagebox.showerror("통신 오류", str(e))
        return None


def parse_response(response):

    if response is None:
        return None, None

    if " : " not in response:
        return None, None

    action, content = response.split(
        " : ",
        1
    )

    return action, content


def handle_server_disconnect_message(response):
    global sock
    global connected
    global logged_in
    global current_user

    action, content = parse_response(response)

    if action != "접속종료":
        return False

    try:
        if sock:
            sock.close()
    except Exception:
        pass

    sock = None
    connected = False
    logged_in = False
    current_user = None

    message = content
    if message.startswith("TIMEOUT|"):
        message = message.split("|", 1)[1]

    def show_disconnect():
        messagebox.showinfo("자동 접속 해제", message)
        show_connect_screen()

    root.after(0, show_disconnect)
    return True


def handle_server_connection_lost(current_sock):
    global sock
    global connected
    global logged_in
    global current_user
    global current_user_name

    # 이미 다른 연결로 변경되었거나 사용자가 직접 접속을 해제한 경우 무시
    if sock is not current_sock or not connected:
        return

    try:
        current_sock.close()
    except Exception:
        pass

    sock = None
    connected = False
    logged_in = False
    current_user = None
    current_user_name = None

    def show_server_closed():
        messagebox.showinfo("서버 종료", "서버가 종료되었습니다.")
        show_connect_screen()

    root.after(0, show_server_closed)


def server_receiver():
    global sock

    while True:
        current_sock = sock
        if current_sock is None:
            return

        try:
            current_sock.settimeout(1)
            data = current_sock.recv(4096)

            if not data:
                handle_server_connection_lost(current_sock)
                return

            response = data.decode("utf-8")

            if handle_server_disconnect_message(response):
                return

            response_queue.put(response)

        except socket.timeout:
            continue
        except Exception:
            handle_server_connection_lost(current_sock)
            return


def start_server_receiver():
    threading.Thread(target=server_receiver, daemon=True).start()


# ============================================================
# 날짜 표시
# ============================================================

def update_date(label):

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    label.config(
        text=today
    )

    label.after(
        1000,
        lambda: update_date(label)
    )


# ============================================================
# 공통 화면
# ============================================================

def clear_screen():

    for widget in root.winfo_children():
        widget.destroy()


def create_date_header(logout_command=None):

    header = tk.Frame(root)
    header.pack(fill="x", padx=10, pady=(10, 5))

    date_label = tk.Label(
        header,
        text="",
        font=("Arial", 13, "bold")
    )
    date_label.place(relx=0.5, rely=0.5, anchor="center")

    if logout_command is not None:
        logout_frame = tk.Frame(header)
        logout_frame.pack(side="right")
        tk.Button(
            logout_frame,
            text="로그아웃",
            width=10,
            command=logout_command
        ).pack()
        if current_user_name:
            tk.Label(
                logout_frame,
                text=f"사용자 : {current_user_name}",
                font=("Arial", 10)
            ).pack(pady=(2, 0))

    update_date(date_label)


# ============================================================
# 접속 화면
# ============================================================

def show_connect_screen():

    clear_screen()

    create_date_header()

    title = tk.Label(
        root,
        text="서버 접속",
        font=("Arial", 22, "bold")
    )

    title.pack(pady=20)

    ip_label = tk.Label(
        root,
        text="서버 IP"
    )

    ip_label.pack()

    ip_entry = tk.Entry(
        root,
        width=30,
        font=("Arial", 14)
    )

    ip_entry.pack(pady=10)

    # 기본값
    ip_entry.insert(
        0,
        "127.0.0.1"
    )

    def connect():

        global sock
        global connected

        ip = ip_entry.get().strip()

        if not ip:
            messagebox.showwarning(
                "입력 오류",
                "서버 IP를 입력하세요."
            )

            return

        try:

            sock = socket.socket(
                socket.AF_INET,
                socket.SOCK_STREAM
            )

            sock.connect(
                (ip, PORT)
            )

            start_server_receiver()

            response = send_request(
                "접속",
                "접속 요청"
            )

            action, content = parse_response(
                response
            )

            if (
                action == "접속"
                and content.startswith("OK|")
            ):

                connected = True

                messagebox.showinfo(
                    "접속",
                    "서버에 접속했습니다."
                )

                show_login_screen()

            else:

                messagebox.showerror(
                    "접속 실패",
                    content.replace(
                        "FAIL|",
                        ""
                    )
                    if content
                    else "접속 실패"
                )

                sock.close()
                sock = None

        except Exception as e:

            messagebox.showerror(
                "접속 실패",
                str(e)
            )

            sock = None


    connect_button = tk.Button(
        root,
        text="서버 접속",
        width=20,
        font=("Arial", 13),
        command=connect
    )

    connect_button.pack(
        pady=20
    )


# ============================================================
# 로그인 화면
# ============================================================

def show_login_screen():

    clear_screen()

    create_date_header()

    title = tk.Label(
        root,
        text="로그인",
        font=("Arial", 22, "bold")
    )

    title.pack(pady=20)


    # ID
    id_label = tk.Label(
        root,
        text="ID"
    )

    id_label.pack()

    id_entry = tk.Entry(
        root,
        width=30,
        font=("Arial", 14)
    )

    id_entry.pack(pady=2)

    tk.Label(
        root,
        text="※ 영문 소문자(a-z) + 숫자(0-9)만 허용 / 1~10자 / 띄어쓰기 불가",
        font=("Arial", 9)
    ).pack()

    # PW
    pw_label = tk.Label(
        root,
        text="PW"
    )

    pw_label.pack()

    pw_entry = tk.Entry(
        root,
        width=30,
        font=("Arial", 14),
        show="*"
    )

    pw_entry.pack(pady=5)


    def login():

        global logged_in
        global current_user
        global current_user_name

        user_id = id_entry.get()
        password = pw_entry.get()

        if not user_id or not password:

            messagebox.showwarning(
                "입력 오류",
                "ID와 PW를 모두 입력하세요."
            )

            return

        response = send_request(
            "로그인",
            f"{user_id}|{password}"
        )

        action, content = parse_response(
            response
        )

        if action != "로그인":
            return

        if content.startswith("OK|"):

            parts = content.split("|")

            current_user = parts[1]
            current_user_name = parts[2] if len(parts) > 2 else current_user

            logged_in = True

            messagebox.showinfo(
                "로그인",
                "로그인 성공"
            )

            show_work_screen()

        else:

            messagebox.showerror(
                "로그인 실패",
                content.replace(
                    "FAIL|",
                    ""
                )
            )


    login_button = tk.Button(
        root,
        text="로그인",
        width=20,
        font=("Arial", 13),
        command=login
    )

    login_button.pack(pady=15)


    signup_button = tk.Button(
        root,
        text="회원가입",
        width=20,
        font=("Arial", 13),
        command=show_signup_screen
    )

    signup_button.pack(pady=5)


    def disconnect():
        global sock
        global connected
        global logged_in
        global current_user

        try:
            if sock:
                sock.close()
        except Exception:
            pass

        sock = None
        connected = False
        logged_in = False
        current_user = None
        current_user_name = None

        # 접속 해제 후 이전 페이지(서버 접속 화면)로 이동
        show_connect_screen()


    disconnect_button = tk.Button(
        root,
        text="접속 해제",
        width=20,
        font=("Arial", 13),
        command=disconnect
    )

    disconnect_button.pack(pady=5)


# ============================================================
# 회원가입 화면
# ============================================================

def show_signup_screen():

    clear_screen()

    create_date_header()

    title = tk.Label(
        root,
        text="회원가입",
        font=("Arial", 22, "bold")
    )

    title.pack(pady=20)


    # ID
    tk.Label(
        root,
        text="ID"
    ).pack()

    id_entry = tk.Entry(
        root,
        width=30,
        font=("Arial", 14)
    )

    id_entry.pack(pady=2)

    tk.Label(
        root,
        text="※ 영문 소문자(a-z) + 숫자(0-9)만 허용 / 1~10자 / 띄어쓰기 불가",
        font=("Arial", 9)
    ).pack()

    # PW
    tk.Label(
        root,
        text="PW"
    ).pack()

    pw_entry = tk.Entry(
        root,
        width=30,
        font=("Arial", 14),
        show="*"
    )

    pw_entry.pack(pady=2)

    tk.Label(
        root,
        text="※ 영문 소문자(a-z) + 숫자(0-9)만 허용 / 1~10자 / 띄어쓰기 불가",
        font=("Arial", 9)
    ).pack()

    # 사용자명
    tk.Label(
        root,
        text="사용자명"
    ).pack()

    name_entry = tk.Entry(
        root,
        width=30,
        font=("Arial", 14)
    )

    name_entry.pack(pady=2)

    tk.Label(
        root,
        text="※ 한글 또는 영문만 허용 / 1~10자 / 띄어쓰기 불가",
        font=("Arial", 9)
    ).pack()

    def signup():

        user_id = id_entry.get().strip()
        password = pw_entry.get()
        user_name = name_entry.get().strip()

        if not user_id or not password or not user_name:

            messagebox.showwarning(
                "입력 오류",
                "모든 항목을 입력하세요."
            )

            return

        if not (
            1 <= len(user_id) <= 10
            and all(("a" <= ch <= "z") or ("0" <= ch <= "9") for ch in user_id)
        ):
            messagebox.showwarning(
                "입력 오류",
                "ID는 영문 소문자(a-z)와 숫자(0-9)만 사용하여 1~10자로 입력하세요."
            )
            return

        if not (
            1 <= len(password) <= 10
            and all(("a" <= ch <= "z") or ("0" <= ch <= "9") for ch in password)
        ):
            messagebox.showwarning(
                "입력 오류",
                "PW는 영문 소문자(a-z)와 숫자(0-9)만 사용하여 1~10자로 입력하세요."
            )
            return

        if not (
            1 <= len(user_name) <= 10
            and all(
                ("가" <= ch <= "힣")
                or ("A" <= ch <= "Z")
                or ("a" <= ch <= "z")
                for ch in user_name
            )
        ):
            messagebox.showwarning(
                "입력 오류",
                "사용자명은 한글 또는 영문만 사용하여 1~10자로 입력하세요."
            )
            return

        response = send_request(
            "회원가입",
            f"{user_id}|{password}|{user_name}"
        )

        action, content = parse_response(
            response
        )

        if action != "회원가입":
            return

        if content.startswith("OK|"):

            messagebox.showinfo(
                "회원가입",
                content.replace(
                    "OK|",
                    ""
                )
            )

            show_login_screen()

        else:

            messagebox.showerror(
                "회원가입 실패",
                content.replace(
                    "FAIL|",
                    ""
                )
            )


    signup_button = tk.Button(
        root,
        text="회원가입",
        width=20,
        font=("Arial", 13),
        command=signup
    )

    signup_button.pack(
        pady=20
    )


    back_button = tk.Button(
        root,
        text="뒤로",
        width=20,
        command=show_login_screen
    )

    back_button.pack()

# ============================================================
# 작업 화면
# ============================================================

def show_work_screen():

    clear_screen()

    def logout():
        global logged_in
        global current_user
        global current_user_name

        if current_user:
            send_request("로그아웃", current_user)

        logged_in = False
        current_user = None
        current_user_name = None
        show_login_screen()

    create_date_header(logout)


    font_frame = tk.Frame(root)
    font_frame.pack(pady=5)
    tk.Label(font_frame, text="폰트 크기 : ").pack(side="left")
    font_sizes = [15, 20, 40]
    input_limits = [15, 10, 5]
    font_size = tk.IntVar(value=font_sizes[0])

    restriction_frame = tk.Frame(root)
    restriction_frame.pack(pady=2)
    language_label = tk.Label(restriction_frame, text="언어 제한 : 한글", font=("Arial", 11))
    language_label.pack(side="left", padx=8)
    limit_label = tk.Label(restriction_frame, text=f"글자수 제한 : {input_limits[0]}자", font=("Arial", 11))
    limit_label.pack(side="left", padx=8)

    # 입력/출력 칸의 높이를 기존 150의 1/3인 50으로 고정
    input_label = tk.Label(root, text="번역할 내용", font=("Arial", 12, "bold"))
    input_label.pack(pady=(3, 1))

    input_frame = tk.Frame(root, width=520, height=50)
    input_frame.pack(padx=20, pady=5)
    input_frame.pack_propagate(False)
    input_text = tk.Text(input_frame, font=("Arial", 15), wrap="word")
    input_text.pack(fill="both", expand=True)

    result_label = tk.Label(root, text="번역 결과", font=("Arial", 12, "bold"))
    result_label.pack(pady=(3, 1))

    result_frame = tk.Frame(root, width=520, height=50)
    result_frame.pack(padx=20, pady=3)
    result_frame.pack_propagate(False)
    result_text = tk.Text(result_frame, font=("Arial", 15), state="disabled", wrap="word")
    result_text.pack(fill="both", expand=True)

    def change_font():
        size = font_size.get()
        index = font_sizes.index(size)

        # 폰트 크기 변경 시 입력 내용과 번역 결과 초기화
        input_text.delete("1.0", tk.END)

        result_text.config(state="normal")
        result_text.delete("1.0", tk.END)
        result_text.config(state="disabled")

        # 입력 칸의 변경된 폰트 크기는 적용안하고 15로 고정
        input_text.config(font=("Arial", 15))
        result_text.config(font=("Arial", 15))

        # 변경된 폰트 크기에 맞는 글자 수 제한 표시
        limit_label.config(text=f"글자수 제한 : {input_limits[index]}자")

    for size in font_sizes:
        tk.Radiobutton(
            font_frame, text=str(size), variable=font_size,
            value=size, command=change_font
        ).pack(side="left", padx=5)

    def validate_input(event=None):
        index = font_sizes.index(font_size.get())
        max_length = input_limits[index]
        text = input_text.get("1.0", "end-1c")
        filtered = "".join(
            ch for ch in text if ("가" <= ch <= "힣") or ch in " \t"
        )
        if filtered != text:
            input_text.delete("1.0", tk.END)
            input_text.insert("1.0", filtered)
            text = filtered
        if len(text) > max_length:
            input_text.delete("1.0", tk.END)
            input_text.insert("1.0", text[:max_length])
        return "break"

    input_text.bind("<KeyRelease>", validate_input)
    input_text.bind("<Return>", lambda event: "break")

    def translate():
        text = input_text.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("입력 오류", "번역할 한글을 입력하세요.")
            return
        response = send_request("번역", f"{text}|{font_size.get()}")
        action, content = parse_response(response)
        if action != "번역":
            return
        result_text.config(state="normal")
        result_text.delete("1.0", tk.END)
        result_text.insert("1.0", content[3:] if content.startswith("OK|") else content.replace("FAIL|", ""))
        result_text.config(state="disabled")

    tk.Button(root, text="번역", width=20, font=("Arial", 13), command=translate).pack(pady=5)

    # 상태 조회 결과
    tk.Label(root, text="상태 조회 결과", font=("Arial", 12, "bold")).pack(pady=(3, 1))

    status_header = tk.Frame(root, width=520)
    status_header.pack(fill="x", padx=20, pady=(0, 2))
    status_page_frame = tk.Frame(status_header)
    status_page_frame.pack(side="left")
    tk.Label(status_page_frame, text="Page:", font=("Arial", 10)).pack(side="left", padx=(0, 5))
    status_page_combo = ttk.Combobox(status_page_frame, state="readonly", width=6)
    status_page_combo.pack(side="left")
    status_total_pages = tk.Label(status_page_frame, text="총 1 페이지", font=("Arial", 10))
    status_total_pages.pack(side="left", padx=8)

    status_frame = tk.Frame(root, width=520, height=120)
    status_frame.pack(padx=20, pady=2)
    status_frame.pack_propagate(False)
    status_columns = ("exec_id", "text", "font_size", "request_date", "status")
    status_table = ttk.Treeview(status_frame, columns=status_columns, show="headings", height=5)
    titles = {"exec_id":"exec_id", "text":"text", "font_size":"font_size", "request_date":"request_date", "status":"status"}
    widths = {"exec_id":70, "text":220, "font_size":80, "request_date":110, "status":70}
    for col in status_columns:
        status_table.heading(col, text=titles[col])
        status_table.column(col, width=widths[col], minwidth=widths[col], anchor="center")
    status_scroll = ttk.Scrollbar(status_frame, orient="vertical", command=status_table.yview)
    status_table.configure(yscrollcommand=status_scroll.set)
    status_table.pack(side="left", fill="both", expand=True)
    status_scroll.pack(side="right", fill="y")

    def query_status(event=None):
        try:
            page = int(status_page_combo.get() or "1")
        except ValueError:
            page = 1
        response = send_request("상태조회", f"{current_user}|{page}")
        action, content = parse_response(response)
        if action != "상태조회":
            return
        for item in status_table.get_children():
            status_table.delete(item)
        if content.startswith("OK|"):
            data = content[3:]
            parts = data.split("|", 1)
            if len(parts) == 2:
                try:
                    total_pages = int(parts[0])
                except ValueError:
                    total_pages = 1
                total_pages = max(1, total_pages)
                status_page_combo["values"] = [str(i) for i in range(1, total_pages + 1)]
                page = min(max(1, page), total_pages)
                status_page_combo.set(str(page))
                status_total_pages.config(text=f"총 {total_pages} 페이지")
                rows = parts[1]
                if rows:
                    for row in rows.split(";;"):
                        values = row.split("|")
                        if len(values) == 5:
                            status_table.insert("", tk.END, values=values)
        else:
            messagebox.showwarning("상태 조회", content.replace("FAIL|", ""))

    status_page_combo.bind("<<ComboboxSelected>>", query_status)
    tk.Button(root, text="상태 조회", width=20, font=("Arial", 13), command=query_status).pack(pady=3)

# ============================================================
# 프로그램 종료
# ============================================================

def on_close():

    global sock
    global current_user_name

    if sock:

        try:

            if logged_in and current_user:

                send_request(
                    "로그아웃",
                    current_user
                )

            sock.close()

        except Exception:
            pass

    root.destroy()


# ============================================================
# 실행
# ============================================================

root = tk.Tk()

root.title(
    "Translation Client"
)

root.geometry(
    "600x700"
)

root.protocol(
    "WM_DELETE_WINDOW",
    on_close
)

show_connect_screen()

root.mainloop()
