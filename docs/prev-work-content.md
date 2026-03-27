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

---

## CI/CD 디버깅 작업 (2026-03-28)

### 발견된 문제 및 수정 내용

#### 1. SCP 실패 — `.git` 디렉토리 권한 오류 ✅ 수정됨
- **원인**: `scp-action`의 `source: "."` 이 `.git/objects` 파일까지 포함해 tar 생성 시도 → `.git/objects`는 git이 의도적으로 read-only로 관리하므로 `Permission denied`로 tar 실패
- **수정**: `main.yml` scp 단계에 `exclude: ".git"` 추가
- **파일**: `.github/workflows/main.yml`

#### 2. DB 연결 실패 — URL 특수문자 파싱 오류 ✅ 수정됨
- **원인**: `config.py`의 `database_url` 프로퍼티가 `db_user`/`db_password`를 URL에 그대로 삽입 → 비밀번호에 `@` 등 특수문자 포함 시 URL 파싱 오류 발생 (`@@192.168.0.3` 형태로 잘못 파싱됨)
- **수정**: `urllib.parse.quote_plus`로 user/password 인코딩 후 URL 조합
- **파일**: `app/config.py`
- **추가 확인 필요**: GitHub Secret `DB_HOST` 값이 `192.168.0.3` 형태인지 확인 (앞에 `@` 붙어있으면 제거)

#### 3. 헬스체크 실패 시 컨테이너 소멸 문제 ✅ 수정됨
- **원인**: `deploy.sh` 헬스체크 실패 경로에서 `docker compose down` 호출 → 컨테이너가 완전히 제거되어 `docker ps -a`에서도 안 보임 (디버깅 불가)
- **수정**: 실패 시 `docker compose down` 제거, 대신 로그 100줄 + `docker compose ps -a` 출력 후 `exit 1`
- **파일**: `scripts/deploy.sh`

#### 4. `docker image prune -f` 추가 ✅ 수정됨
- **백엔드**: `scripts/deploy.sh` 배포 성공 후 실행 (기존엔 `main.yml` Cleanup 스텝에만 있었음)
- **프론트엔드**: `deploy.yml` Deploy 스텝에 추가, `docker compose up -d --build` → `docker compose build --no-cache` + `docker compose up -d` 로 분리

#### 5. `.dockerignore` 신규 생성 ✅ 완료
- `venv/`, `.omc/`, `.git/`, `__pycache__`, `docs/`, `tests/` 등 제외
- **파일**: `.dockerignore`

### 현재 상태
- SCP 실패 문제는 수정 완료, 아직 재배포 미완료
- DB URL 파싱 문제 수정 완료, 아직 검증 안됨
- 다음 세션에서 커밋/푸시 후 GitHub Actions 재실행하여 확인 필요

### 수정된 파일 목록
| 파일 | 변경 내용 |
|------|----------|
| `.github/workflows/main.yml` | SCP `exclude: ".git"` 추가 |
| `app/config.py` | `quote_plus` import 및 DB URL 인코딩 적용 |
| `scripts/deploy.sh` | 헬스체크 실패 시 `docker compose down` 제거, `docker image prune -f` 추가 |
| `.dockerignore` | 신규 생성 |
| `home-server-admin-front/.github/workflows/deploy.yml` | `docker compose build --no-cache` 분리, `docker image prune -f` 추가 |
