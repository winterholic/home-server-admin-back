# 홈서버 관리 대시보드 프로젝트 기획서

## 1. 프로젝트 개요

### 1.1 프로젝트명
**HomeServer Dashboard** (또는 적절한 이름으로 변경 가능)

### 1.2 목적
개인 홈서버(Ubuntu 24.04 LTS)의 시스템 상태를 실시간으로 모니터링하고, 주요 서비스를 관리할 수 있는 웹 기반 대시보드 구축

### 1.3 배경
- 현재 운영 중인 홈서버: Ubuntu 24.04 LTS (i5-12500T, 32GB RAM)
- 구축된 인프라: Nginx, MariaDB, Redis, Cloudflare Tunnel
- 여러 프로젝트 배포 중 (Ariari 등)
- 서버 상태를 효율적으로 모니터링하고 관리할 필요성

---

## 2. 기술 스택

### 2.1 백엔드
- **프레임워크**: FastAPI
- **Python 버전**: 3.10+
- **데이터베이스**: SQLite (간편성 및 배포 편의성)
- **ORM**: SQLAlchemy
- **비동기 처리**: asyncio
- **모니터링 라이브러리**: psutil, subprocess

### 2.2 프론트엔드
- **프레임워크**: React 18+
- **상태 관리**: React Context API (또는 필요시 Zustand)
- **UI 라이브러리**: TailwindCSS + shadcn/ui
- **차트 라이브러리**: Recharts 또는 Chart.js
- **HTTP 클라이언트**: Axios
- **실시간 통신**: WebSocket (선택사항)

### 2.3 배포 환경
- **서버**: Ubuntu 24.04 LTS 홈서버
- **웹서버**: Nginx (리버스 프록시)
- **도메인**: Cloudflare Tunnel 활용
- **프로세스 관리**: systemd 또는 PM2

---

## 3. 주요 기능

### 3.1 시스템 모니터링
#### 실시간 모니터링
- CPU 사용률 (전체 및 코어별)
- 메모리 사용량 (RAM, Swap)
- 디스크 사용률 (파티션별)
- 네트워크 트래픽 (수신/송신)
- 시스템 업타임
- 현재 프로세스 개수

#### 히스토리 데이터
- 최근 24시간/7일/30일 추이 그래프
- 5분 간격으로 데이터 수집 및 저장
- 시간대별 리소스 사용 패턴 분석

### 3.2 서비스 관리
#### 서비스 상태 모니터링
- systemd 서비스 목록 및 상태 조회
    - nginx
    - mariadb
    - redis-server
    - 배포된 애플리케이션들
- 각 서비스별 상태: Active, Inactive, Failed
- 서비스 시작 시간 및 메모리 사용량

#### 서비스 제어
- 서비스 시작/중지/재시작
- Nginx 설정 리로드
- 권한 관리 (중요 작업 확인 절차)

### 3.3 로그 관리
#### 실시간 로그 조회
- Nginx 접속 로그 (access.log)
- Nginx 에러 로그 (error.log)
- 시스템 로그 (syslog)
- 애플리케이션별 로그

#### 로그 히스토리 및 분석
- 브루트포스 시도 감지 및 기록
    - SSH 로그인 실패 패턴
    - 반복적인 HTTP 403/404 요청
- 에러 로그 집계 및 분류
- 시간대별 로그 발생 추이
- 필터링 및 검색 기능

### 3.4 알림 시스템
#### 알림 설정
- CPU 사용률 임계값 설정
- 메모리 사용률 임계값 설정
- 디스크 사용률 임계값 설정
- 서비스 다운 감지
- 보안 이벤트 감지 (브루트포스 등)

#### 알림 전송
- 이메일 알림 (SMTP 연동)
- 알림 발송 기록
- 알림 수신 설정 (활성화/비활성화)

### 3.5 대시보드
- 주요 지표 한눈에 보기
- 시스템 상태 요약 카드
- 최근 알림 내역
- 서비스 상태 요약
- 주요 로그 이벤트

---

## 4. 시스템 아키텍처

### 4.1 전체 구조
```
┌─────────────────┐
│   React SPA     │ ← 사용자 인터페이스
└────────┬────────┘
         │ HTTPS
         ↓
┌─────────────────┐
│  Nginx (Proxy)  │ ← 리버스 프록시
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  FastAPI Server │ ← REST API + WebSocket
└────────┬────────┘
         │
    ┌────┴────┬──────────┬─────────┐
    ↓         ↓          ↓         ↓
┌────────┐ ┌──────┐  ┌──────┐  ┌──────┐
│ SQLite │ │psutil│  │ logs │  │SMTP  │
└────────┘ └──────┘  └──────┘  └──────┘
```

### 4.2 백엔드 모듈 구조
```
backend/
├── app/
│   ├── main.py                 # FastAPI 앱 진입점
│   ├── config.py               # 설정 관리
│   ├── database.py             # DB 연결 설정
│   ├── models/                 # SQLAlchemy 모델
│   │   ├── monitoring.py
│   │   ├── log.py
│   │   └── alert.py
│   ├── routers/                # API 라우터
│   │   ├── system.py           # 시스템 모니터링
│   │   ├── services.py         # 서비스 관리
│   │   ├── logs.py             # 로그 관리
│   │   └── alerts.py           # 알림 관리
│   ├── services/               # 비즈니스 로직
│   │   ├── monitor.py          # 모니터링 수집
│   │   ├── log_analyzer.py     # 로그 분석
│   │   └── notification.py     # 알림 발송
│   └── utils/                  # 유틸리티
│       ├── system_info.py
│       └── email.py
├── requirements.txt
└── .env.example
```

### 4.3 프론트엔드 모듈 구조
```
frontend/
├── src/
│   ├── components/
│   │   ├── Dashboard/
│   │   ├── Monitoring/
│   │   ├── Services/
│   │   ├── Logs/
│   │   └── Alerts/
│   ├── pages/
│   │   ├── DashboardPage.jsx
│   │   ├── MonitoringPage.jsx
│   │   ├── ServicesPage.jsx
│   │   ├── LogsPage.jsx
│   │   └── SettingsPage.jsx
│   ├── api/
│   │   └── client.js           # API 호출 함수
│   ├── hooks/
│   │   └── useSystemData.js    # 커스텀 훅
│   └── App.jsx
├── package.json
└── vite.config.js
```

---

## 5. 데이터베이스 설계

### 5.1 ERD
```
monitoring_history     log_history          alert_settings
  ├─ id               ├─ id                ├─ id
  ├─ timestamp        ├─ timestamp         ├─ metric_type
  ├─ cpu_usage        ├─ log_type          ├─ threshold
  ├─ memory_usage     ├─ severity          ├─ enabled
  ├─ disk_usage       ├─ source            └─ created_at
  ├─ network_rx       ├─ message
  └─ network_tx       └─ count
                      
alert_history
  ├─ id
  ├─ timestamp
  ├─ alert_type
  ├─ message
  ├─ metric_value
  └─ sent_email
```

### 5.2 테이블 상세 설계

#### monitoring_history
| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| id | INTEGER | PK, Auto Increment |
| timestamp | DATETIME | 수집 시간 |
| cpu_usage | FLOAT | CPU 사용률 (%) |
| cpu_per_core | JSON | 코어별 사용률 |
| memory_total | BIGINT | 전체 메모리 (bytes) |
| memory_used | BIGINT | 사용 중 메모리 (bytes) |
| memory_percent | FLOAT | 메모리 사용률 (%) |
| swap_used | BIGINT | Swap 사용량 (bytes) |
| disk_usage | JSON | 파티션별 사용률 |
| network_rx_bytes | BIGINT | 수신 바이트 |
| network_tx_bytes | BIGINT | 송신 바이트 |

#### log_history
| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| id | INTEGER | PK, Auto Increment |
| timestamp | DATETIME | 로그 발생 시간 |
| log_type | VARCHAR(50) | 로그 유형 (bruteforce, error, etc) |
| severity | VARCHAR(20) | 심각도 (info, warning, error) |
| source | VARCHAR(100) | 로그 소스 (nginx, ssh, app) |
| message | TEXT | 로그 메시지 |
| ip_address | VARCHAR(50) | 관련 IP (선택) |
| count | INTEGER | 발생 횟수 (집계용) |

#### alert_settings
| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| id | INTEGER | PK, Auto Increment |
| metric_type | VARCHAR(50) | 메트릭 타입 (cpu, memory, disk) |
| threshold | FLOAT | 임계값 |
| enabled | BOOLEAN | 알림 활성화 여부 |
| email_recipients | TEXT | 이메일 수신자 (JSON) |
| created_at | DATETIME | 생성 시간 |
| updated_at | DATETIME | 수정 시간 |

#### alert_history
| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| id | INTEGER | PK, Auto Increment |
| timestamp | DATETIME | 알림 발생 시간 |
| alert_type | VARCHAR(50) | 알림 유형 |
| message | TEXT | 알림 메시지 |
| metric_value | FLOAT | 해당 메트릭 값 |
| sent_email | BOOLEAN | 이메일 발송 여부 |
| resolved_at | DATETIME | 해결 시간 (선택) |

---

## 6. API 설계

### 6.1 시스템 모니터링 API

#### GET /api/system/status
실시간 시스템 상태 조회
```json
{
  "cpu": {
    "percent": 45.2,
    "per_core": [40.1, 50.3, 42.8, 48.5]
  },
  "memory": {
    "total": 34359738368,
    "used": 16106127360,
    "percent": 46.9,
    "swap_used": 0
  },
  "disk": [
    {
      "mountpoint": "/",
      "total": 512110190592,
      "used": 153632972800,
      "percent": 30.0
    }
  ],
  "network": {
    "rx_bytes": 1234567890,
    "tx_bytes": 987654321
  },
  "uptime": 259200
}
```

#### GET /api/system/history
히스토리 데이터 조회
- Query Parameters: `period` (1h, 24h, 7d, 30d)
```json
{
  "data": [
    {
      "timestamp": "2024-02-16T10:00:00",
      "cpu": 45.2,
      "memory": 46.9,
      "disk": 30.0
    }
  ]
}
```

### 6.2 서비스 관리 API

#### GET /api/services
서비스 목록 및 상태 조회
```json
{
  "services": [
    {
      "name": "nginx",
      "status": "active",
      "uptime": "3 days",
      "memory": 52428800
    }
  ]
}
```

#### POST /api/services/{service_name}/control
서비스 제어
- Request Body: `{"action": "start|stop|restart"}`
```json
{
  "success": true,
  "message": "Service restarted successfully"
}
```

### 6.3 로그 관리 API

#### GET /api/logs/recent
최근 로그 조회
- Query Parameters: `source`, `severity`, `limit`
```json
{
  "logs": [
    {
      "timestamp": "2024-02-16T10:30:00",
      "type": "bruteforce",
      "severity": "warning",
      "source": "ssh",
      "message": "Failed login attempt from 192.168.1.100",
      "ip_address": "192.168.1.100"
    }
  ]
}
```

#### GET /api/logs/statistics
로그 통계 조회
- Query Parameters: `period` (24h, 7d, 30d)
```json
{
  "bruteforce_attempts": 15,
  "errors": 3,
  "by_type": {
    "bruteforce": 15,
    "error": 3
  },
  "timeline": [...]
}
```

### 6.4 알림 관리 API

#### GET /api/alerts/settings
알림 설정 조회
```json
{
  "settings": [
    {
      "id": 1,
      "metric_type": "cpu",
      "threshold": 80.0,
      "enabled": true,
      "email_recipients": ["admin@example.com"]
    }
  ]
}
```

#### PUT /api/alerts/settings/{id}
알림 설정 수정
- Request Body:
```json
{
  "threshold": 85.0,
  "enabled": true,
  "email_recipients": ["admin@example.com"]
}
```

#### GET /api/alerts/history
알림 히스토리 조회
- Query Parameters: `limit`, `offset`
```json
{
  "alerts": [
    {
      "id": 1,
      "timestamp": "2024-02-16T10:00:00",
      "alert_type": "cpu_high",
      "message": "CPU usage exceeded 80%",
      "metric_value": 85.3,
      "sent_email": true
    }
  ],
  "total": 25
}
```

---

## 7. 주요 화면 구성

### 7.1 대시보드 (/)
- 전체 시스템 상태 요약
- 주요 메트릭 카드 (CPU, 메모리, 디스크, 네트워크)
- 최근 알림 3개
- 서비스 상태 요약
- 최근 로그 이벤트 5개

### 7.2 모니터링 (/monitoring)
- 실시간 메트릭 그래프
- 히스토리 데이터 차트 (시간대 선택 가능)
- 상세 시스템 정보

### 7.3 서비스 관리 (/services)
- 서비스 목록 테이블
- 각 서비스별 상태 및 제어 버튼
- 서비스 로그 빠른 보기

### 7.4 로그 뷰어 (/logs)
- 로그 필터링 (소스, 타입, 심각도)
- 로그 검색
- 시간대별 로그 통계
- 브루트포스 시도 대시보드

### 7.5 설정 (/settings)
- 알림 설정 관리
- 이메일 설정
- 모니터링 수집 주기 설정
- 데이터 보관 정책

---

## 8. 구현 우선순위

### Phase 1: 기본 모니터링 (MVP)
1. 실시간 시스템 상태 조회 API
2. 기본 대시보드 UI
3. CPU/메모리/디스크 사용률 표시
4. SQLite DB 설정 및 히스토리 수집

### Phase 2: 서비스 관리
1. systemd 서비스 상태 조회
2. 서비스 제어 기능
3. 히스토리 데이터 차트

### Phase 3: 로그 관리
1. 로그 파일 파싱 및 조회
2. 로그 히스토리 저장
3. 브루트포스 감지 로직

### Phase 4: 알림 시스템
1. 알림 설정 관리
2. 임계값 모니터링 백그라운드 작업
3. 이메일 발송 기능

### Phase 5: 최적화 및 개선
1. 성능 최적화
2. UI/UX 개선
3. 추가 기능 (로그 검색, 통계 등)

---

## 9. 기술적 고려사항

### 9.1 보안
- API 인증/인가 (JWT 또는 Session)
- HTTPS 적용 (Cloudflare Tunnel 활용)
- 서비스 제어 권한 관리
- CORS 설정
- Rate Limiting

### 9.2 성능
- 모니터링 데이터 수집 주기: 5분
- 오래된 데이터 자동 삭제 (30일 이상)
- 로그 파일 파싱 최적화
- DB 인덱스 설정

### 9.3 안정성
- 에러 핸들링
- 로깅
- 백그라운드 작업 관리 (APScheduler)
- DB 백업 전략

---

## 10. 배포 계획

### 10.1 배포 환경
- **서버**: 홈서버 (Ubuntu 24.04 LTS)
- **도메인**: Cloudflare Tunnel을 통한 외부 접근
- **포트**: 내부 8000 (FastAPI), 외부 HTTPS

### 10.2 배포 절차
1. 프론트엔드 빌드 (`npm run build`)
2. 빌드된 정적 파일을 FastAPI static 디렉토리로 복사
3. systemd 서비스 등록
4. Nginx 리버스 프록시 설정
5. Cloudflare Tunnel 설정

### 10.3 systemd 서비스 예시
```ini
[Unit]
Description=HomeServer Dashboard
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/backend
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## 11. 개발 일정 (예상)

| 단계 | 작업 내용 | 예상 기간 |
|------|-----------|-----------|
| Phase 1 | 기본 모니터링 구현 | 1주 |
| Phase 2 | 서비스 관리 구현 | 3일 |
| Phase 3 | 로그 관리 구현 | 1주 |
| Phase 4 | 알림 시스템 구현 | 4일 |
| Phase 5 | 최적화 및 테스트 | 3일 |
| **총 예상 기간** | | **약 3-4주** |

---

## 12. 향후 확장 가능성

- Docker 컨테이너 모니터링
- 네트워크 트래픽 상세 분석
- 백업 자동화 관리
- 데이터베이스(MariaDB) 쿼리 모니터링
- Redis 메트릭 수집
- 모바일 앱 연동 (선택)
- Webhook 알림 (Discord, Slack 등)

---

## 부록

### A. 참고 라이브러리
- **FastAPI**: https://fastapi.tiangolo.com/
- **psutil**: https://github.com/giampaolo/psutil
- **SQLAlchemy**: https://www.sqlalchemy.org/
- **React**: https://react.dev/
- **Recharts**: https://recharts.org/
- **TailwindCSS**: https://tailwindcss.com/

### B. 유용한 명령어
```bash
# 시스템 정보 조회
htop
df -h
free -h

# 서비스 상태 확인
systemctl status nginx
journalctl -u nginx -n 50

# 로그 조회
tail -f /var/log/nginx/access.log
tail -f /var/log/auth.log
```