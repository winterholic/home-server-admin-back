# CI/CD 배포 디버깅 작업 기록

## 문제 상황
GitHub Actions CI/CD 파이프라인은 성공하지만, Docker 컨테이너 실행 중 DB 연결 실패로 앱이 크래시됨.

## 에러 메시지 (핵심)
```
sqlalchemy.exc.OperationalError: (pymysql.err.OperationalError) (2003, "Can't connect to MySQL server on '192.168.0.3'")
Application startup failed. Exiting.
gunicorn.errors.HaltServer: <HaltServer 'Worker failed to boot.' 3>
```

## 프로젝트 구조 파악

### 스택
- FastAPI + SQLAlchemy (async) + aiomysql
- gunicorn + uvicorn workers
- Docker + docker-compose
- pydantic-settings로 환경변수 로드

### 주요 파일 위치
- `app/config.py` - Settings (pydantic BaseSettings)
- `app/database.py` - SQLAlchemy engine 생성
- `app/main.py` - FastAPI lifespan에서 `init_db()` 호출
- `docker-compose.yml` - `network_mode: host`, `env_file: .env`
- `Dockerfile` - `COPY . .` → `.env`가 이미지에 포함됨
- `.github/workflows/main.yml` - GitHub Actions CI/CD
- `scripts/deploy.sh` - 서버에서 실행되는 배포 스크립트

### 환경변수 로딩 흐름
1. GitHub Actions에서 Secrets를 사용해 `.env` 파일 생성
2. `scp-action`으로 서버(`/home/winterholic/projects/services/home-server-admin/backend`)에 파일 복사
3. `deploy.sh`에서 `docker compose build --no-cache` → `COPY . .`로 `.env`가 이미지에 포함
4. `docker compose up -d` → `env_file: .env`로 환경변수가 컨테이너에 전달
5. pydantic BaseSettings가 환경변수 읽어서 `database_url` property로 MySQL URL 구성

### DB URL 구성 방식 (`config.py`)
```python
@property
def database_url(self) -> str:
    return (
        f"mysql+aiomysql://{quote_plus(self.db_user)}:{quote_plus(self.db_password)}"
        f"@{self.db_host}:{self.db_port}/{self.db_name}"
    )
```

## 분석 결과

### 코드는 정상
에러에서 `192.168.0.3`이 나온다는 것 자체가 `.env`에서 환경변수를 **정상적으로 읽고 있다**는 증거.
(기본값을 썼다면 `localhost`가 나왔어야 함)

### 실제 문제 원인 (미확정)
- `192.168.0.3`은 내부망의 DB 서버 IP (의도된 값)
- `network_mode: host`이므로 컨테이너는 호스트 네트워크를 그대로 사용
- 연결이 안 되는 원인은 현재 미확정 → **재배포 후 로그 확인 중**

가능성:
1. MySQL 서버(192.168.0.3)의 방화벽이 앱 서버 IP에서 오는 3306 포트 차단
2. MySQL user 권한이 앱 서버 IP에서의 접속을 허용 안 함
3. 일시적인 네트워크 문제

## 수행한 코드 변경

### `app/database.py` - 디버깅용 로그 추가
연결 시도 시 실제로 사용되는 host/port/db/user 값을 로그에 출력하도록 수정.

```python
import logging
# ...
logger = logging.getLogger(__name__)
# ...
logger.info("DB connecting → host=%s port=%s db=%s user=%s", settings.db_host, settings.db_port, settings.db_name, settings.db_user)
```

이제 컨테이너 시작 로그에서 아래처럼 실제 사용 값 확인 가능:
```
DB connecting → host=192.168.0.3 port=3306 db=nodectrl user=...
```

## 다음 단계 (재배포 후 확인 사항)
1. `docker compose logs app` 에서 `DB connecting →` 로그 확인 (env 로딩 정상 여부)
2. MySQL 서버(192.168.0.3)에서 앱 서버 IP의 접속 허용 확인:
   ```sql
   SELECT host, user FROM mysql.user WHERE user = '<DB_USER>';
   ```
3. 앱 서버에서 직접 MySQL 접속 테스트:
   ```bash
   mysql -h 192.168.0.3 -P 3306 -u <DB_USER> -p
   ```
4. 방화벽 확인 (MySQL 서버에서):
   ```bash
   sudo ufw status | grep 3306
   ```
