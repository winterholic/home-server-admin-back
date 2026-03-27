# 이전 작업 내용 요약

## 작업 개요

`home-server-admin-back` (FastAPI) 프로젝트의 CI/CD를 `new-facereview` 프로젝트 방식으로 전면 재구성.

---

## 생성/수정된 파일

### 신규 생성

| 파일 | 설명 |
|------|------|
| `Dockerfile` | multi-stage build, gunicorn + UvicornWorker, 포트 5004 |
| `docker-compose.yml` | 단일 app 서비스, healthcheck 포함 |
| `scripts/deploy.sh` | 빌드 → 재시작 → 헬스체크 → 로그 기록 |
| `.github/workflows/main.yml` | test → .env생성 → scp → deploy → verify → cleanup |

### 수정된 파일

| 파일 | 변경 내용 |
|------|----------|
| `requirements.txt` | `gunicorn==23.0.0` 추가 |
| `app/config.py` | `fail2ban_log` 필드 추가 (기본값: `/var/log/fail2ban.log`) |
| `app/services/service_manager.py` | 서비스 자동 감지로 전면 교체 |
| `app/services/log_analyzer.py` | fail2ban 파서 추가 |
| `.github/workflows/deploy.yml` | 삭제 (main.yml로 대체) |

---

## 주요 설계 결정

### 포트
- 앱 포트: **5004**
- 헬스체크 엔드포인트: `GET /api/health` (`main.py:194`에 정의됨)
- Gunicorn CMD: `gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:5004`

### ORM 방식
- `Base.metadata.create_all` 사용 → **테이블 없으면 생성, 있으면 skip**
- Spring JPA `update`보다 보수적 (기존 테이블 컬럼 변경 불가)
- 운영 환경 안전. 스키마 변경 시 Alembic 도입 필요

### SMTP
- 네이버 SMTP: `smtp.naver.com:465` (main.yml에 하드코딩)
- `SMTP_TLS` 제거 — `email.py:35`에서 포트 465이면 자동으로 implicit SSL 사용
- 시크릿 필요: `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`

### 모니터링 설정 (MONITOR_INTERVAL, DATA_RETENTION_DAYS)
- `.env` 시크릿 **불필요** — `config.py` 기본값(300초, 30일) 사용
- 프론트 UI에서 변경 시 `app_config` 테이블에 저장 (DB 우선, .env 폴백 방식)
- **주의**: `monitor_interval`은 앱 시작 시 스케줄러에 고정됨 → 변경 후 재시작 필요
- `data_retention_days`는 cleanup 태스크가 매번 DB에서 읽으므로 즉시 반영

### 서비스 자동 감지 (`service_manager.py`)
- **Systemd**: `systemctl list-units --type=service --all`로 전체 자동 감지
- **Docker**: `docker ps -a`로 전체 자동 감지 (원래도 됐음)
- **Nohup**: PPID=1 + uid≥1000 조건으로 사용자 백그라운드 프로세스 자동 감지
- `SYSTEMD_SERVICES`, `DOCKER_CONTAINERS`, `NOHUP_SERVICES` 시크릿/설정 완전 제거

### Fail2ban 로그
- 파서 추가: Ban → `log_type: bruteforce / severity: critical`, Unban → `log_type: info`
- 기본 경로: `/var/log/fail2ban.log` (표준 경로면 시크릿 불필요)

---

## GitHub Secrets 최종 목록

```
# 서버 접속
SERVER_HOST
SERVER_USER
SERVER_SSH_KEY
SERVER_PORT

# DB
DB_HOST
DB_PORT
DB_USER
DB_PASSWORD
DB_NAME

# 앱
APP_PORT          (5004)
SECRET_KEY
CORS_ORIGINS

# SMTP (네이버)
SMTP_USER         (네이버 아이디)
SMTP_PASSWORD     (네이버 앱 비밀번호)
SMTP_FROM

# 로그 경로 (기본값과 다를 경우만 등록)
NGINX_ACCESS_LOG  (기본: /var/log/nginx/access.log)
NGINX_ERROR_LOG   (기본: /var/log/nginx/error.log)
AUTH_LOG          (기본: /var/log/auth.log)
SYSLOG            (기본: /var/log/syslog)
FAIL2BAN_LOG      (기본: /var/log/fail2ban.log)
```

---

## 배포 경로

서버 내 배포 경로: `/home/winterholic/projects/services/home-server-admin/backend`

## 첫 배포 전 서버에서 실행

```bash
mkdir -p /home/winterholic/projects/services/home-server-admin/backend
```
