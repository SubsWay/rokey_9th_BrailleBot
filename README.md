# 🤖 DOT.ON: 점자 및 한글 캘리그라피 로봇 콘텐츠 서비스

> **Force/Compliance Control 기반 협동로봇 시스템 구성**

---

## 📌 프로젝트 개요

| 항목 | 내용 |
| ------------- | ----------------------------------------------------------------------------------------------- |
| 🎯 **목표** | 협동로봇을 활용해 점자 타각과 한글 캘리그라피를 동시에 구현하여, **시각장애인과 비장애인이 함께 즐길 수 있는 체험형 콘텐츠**를 제작하고 정밀 작업 적용 가능성을 검증 |
| ⚙️ **주요 기능** | 한글 문장 점자 변환 · 점자 타각(Force Control) · 한글 캘리그라피 필기 · Topic 기반 진행률 피드백                            |
| 🦾 **사용 장비** | Doosan Robotics **M0609** (GripperDA 그리퍼, 점필/펜 교체 사용)                                           |
| 💻 **개발 환경** | Ubuntu 24.04 LTS · ROS2 Jazzy · Python 3.12.3 |
| 🛠️ **기술 스택** | ROS2 Topic · Compliance Control · Force Control · KorToBraille · HangulEngine |
| 📅 **기간** | 2026.08.14 ~ 2026.08.28 |

---

## 🎬 시연 영상

> 🔗 [발표 시연 영상 링크 삽입](https://drive.google.com/file/d/1XctRZDlalCx3erfI6DE-vuEc5Dla5cA8/view?usp=drive_link)

---

## 🏗️ 시스템 아키텍처

<img width="1354" height="668" alt="system_architecture_" src="https://github.com/user-attachments/assets/ae2b9d41-dd61-40c5-a27b-fe08ab9ab5aa" />

---

## 📖 상세 설명

### ❗ 문제정의

* 시각장애인을 위한 점자 콘텐츠 제작은 대부분 **수작업 또는 별도 인쇄 설비**에 의존
* 시각장애인과 비장애인이 **함께 접근할 수 있는** 로봇 기반 콘텐츠 사례가 드묾
* 협동로봇의 **정밀 작업(접촉 기반 타각) 적용 가능성**이 충분히 검증되지 않음

### 💡 해결방안

* M0609 협동로봇과 그리퍼로 점필/펜을 교체하며 **타각과 필기 두 가지 작업**을 하나의 시스템에서 수행
* **Compliance Control + Force Control**을 조합해 종이 두께 편차에도 안정적인 타각 구현
* 한글 유니코드를 실시간 분해해 폰트 없이 캘리그라피 궤적을 동적으로 생성 (`HangulEngine`)
* ROS2 **Topic 통신**으로 문장 입력부터 로봇 실행, 진행률 피드백까지 전 과정 자동화

### ✨ 주요기능

| 기능 | 설명 |
| --------------- | ------------------------------------------------------------------- |
| 🔤 한글 점자 변환 | `KorToBraille`로 입력 문장을 점자 데이터로 변환 후 6비트 단위로 평탄화 |
| ✒️ 점자 타각 | Compliance Control + Force Control 기반으로 종이에 0.2N 단위로 정밀하게 점자를 타각 |
| 🖋️ 한글 캘리그라피 | `HangulEngine`이 초성/중성/종성을 실시간 분해해 벡터 궤적 생성 후 필기 |
| 📡 Topic 기반 통신 | 필요 데이터를 Topic으로 전달 -> 완료 결과를 Topic으로 전달 |
| 🛡️ 안전 설계 | 그리퍼 물건 모니터링 스레드 (강제 중단), 이쑤시게 관통 방지, 무한 대기 방지 |

---

## 🖥️ 운영체제 환경 (OS Environment)
```
정섭님 추가분
```

---
### 워크스페이스 빌드 (터미널에서 nano .bashrc 구성)

```
export PATH=/home/rokey/.opencode/bin:$PATH
source /opt/ros/jazzy/setup.bash

export PYTHONPATH=$PYTHONPATH:~/ws_cobot_pjt/ws_dsr/install/dsr_common2/lib/dsr>

export ROS_DOMAIN_ID=70  ## 조별로 번호가 다름
alias sod='source ~/ws_cobot_pjt/ws_dsr/install/setup.bash && source ~/drb3/ins>
```


## ⚙️ 실행 방법

**Step 1 — 로봇 초기화**

```bash
ros2 launch dsr_bringup2 dsr_bringup2_rviz.launch.py mode:=real host:=192.168.1.100 port:=12345 model:=m0609
```

**Step 2 — 기능 실행**

```bash
ros2 run drb3 master_DB # GUI와 연결하여 글자를 받고 점자로 번역하는 노드
ros2 run drb3 control # master node로 부터 글자를 받고 실제 로봇을 움직이는 노드
```

---

## 📦 의존성

* `rclpy`, `std_msgs`
* `dsr_common2`, `dsr_msgs`
* `custom_interfaces` (PrintBraille Topic 정의)

* `python3-venv` (Python 가상환경 설치와 pip install 용도)
* `KorToBraille` (한글 → 점자 변환)
* `psycopg2-binary` (파이썬 코드로 PostSQL DB 제어)
* `rg2` (OnRobot rg2 그리퍼 API)

---

## 👥 프로젝트 기여자

| 이름  | 연락처 |
| --- | ------------------------- |
| 이동준 | `omver5669@gmail.com` |
| 이정섭 | `jungsub27@gmail.com` |
| 박세준 | `sejun000220@gmail.com` |
| 백승주 | `raybaeksj@gmail.com` |

---

## 🎓 교육과정 및 참고자료

### 교육과정

| 주차 | 기간 | 구분 | 강의실 |
| ------- | ----------------------------- | ------- | ---------- |
| `[1~2주차]` | 2026.08.14(금) ~ 2026.08.28(금) | `[협동1]` | `[구로디지털단지 대륭포스트 8차]` |

| 차시 | 구분 | 세부사항 | 평가 | 팀구성 |
| -- | --------------- | -------------------------------- | -- | ----- |
| 1 | 프로젝트 계획 및 환경 구축 | 개발 환경 구축, 로봇 초기 세팅 | ✅ | 4인 1팀 |
| 2 | 기술 탐색 및 검증 | Compliance/Force Control 탐색 및 검증 | | 4인 1팀 |
| 3 | 기술 탐색 및 검증 | 점필/펜 도구 선정 및 파라미터 튜닝 | ✅ | 4인 1팀 |
| 4 | 프로젝트 설계 | 시스템 설계 및 Topic 통신 구조 구성 | | 4인 1팀 |
| 5 | 개발 | HangulEngine 및 점자 타각 기능 구현 | | 4인 1팀 |
| 6 | 개발 | 통합 시스템 구축 및 테스트 | | 4인 1팀 |
| 7 | 프로젝트 발표 | 프로젝트 발표 및 시연, 산출물 정리 | ✅ | 4인 1팀 |

### 참고자료

* 🔗 [두산로보틱스 튜토리얼](https://robotlab.doosanrobotics.com/ko/Training/OnlineCourses)
* 🔗 [두산로보틱스 M0609 API](https://v2-manual.scroll.site/ko/v2-programming-manual/2.12.1/publish)
* 🔗 [한글에서 점자로 번역 GitHub 라이브러리](github.com/Bridge-NOONGIL/KorToBraille_Python)

* 🔗 [서울 시각장애인 복지관](https://bokji.or.kr/)
