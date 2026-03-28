# 이전 작업 내용 (홈서버 관리 대시보드 백엔드)

## 최종 업데이트: 2026-03-28

---

## 완료된 작업 (2026-03-28 - 세션 2)

### 이슈 #6: IP 접속 현황 API 추가
- **파일**: `app/routers/logs.py`, `app/services/log_analyzer.py`, `app/schemas/log.py`
- **내용**:
  - `GET /api/logs/access-ips` 엔드포인트 추가 (`hours`, `limit` 쿼리 파라미터)
  - `get_access_ips()` 함수: nginx access.log 직접 파싱, IP별 집계
  - `AccessIpEntry` / `AccessIpsResponse` 스키마 추가
  - 응답: IP, 요청 수, 마지막 접속, 경로 목록(최대 10), 상태코드, 의심 여부(50회 이상)
  - 파일 50MB 초과 시 마지막 50MB만 읽음 (성능 보호)

---

## 완료된 작업 (2026-03-28 - 세션 1)

### 1. `/api/logs/recent` 422 오류 수정
- **파일**: `app/routers/logs.py`
- **내용**: `limit` 파라미터 최대값 `le=200` → `le=500`

### 2. 디스크 가상 파티션 필터링
- **파일**: `app/services/monitor.py`
- **내용**: `_SKIP_FSTYPES`, `_is_real_partition()` 추가

### 3. 서비스 조회 성능 최적화
- **파일**: `app/services/service_manager.py`
- **내용**: `asyncio.to_thread()`, `_get_systemd_services_batch()`, `get_docker_logs()` 추가

### 4. 서비스 로그 API docker 지원
- **파일**: `app/routers/services.py`

### 5. 이메일 설정 간소화
- **파일**: `app/config.py`, `app/schemas/settings.py`, `app/routers/settings.py`, `app/services/notification.py`

---

## 다음 세션에서 작업할 내용

### nohup 프로세스 실제 restart 지원
- 현재 stop 후 외부 관리자에 위임 → 실제 재시작 명령어 지원 필요
- `app/services/service_manager.py` 수정

### 모니터링 히스토리 파티션별 디스크 (선택)
- `app/routers/system.py` history 응답에 파티션별 데이터 추가 가능

---

## 주요 파일 현황

```
app/
├── config.py
├── routers/
│   ├── logs.py             # limit le=500, GET /access-ips
│   ├── services.py         # service_type 파라미터
│   └── settings.py         # /email-recipient 엔드포인트
├── schemas/
│   ├── log.py              # AccessIpEntry, AccessIpsResponse 추가
│   └── settings.py
└── services/
    ├── monitor.py
    ├── service_manager.py
    ├── log_analyzer.py     # get_access_ips() 추가
    └── notification.py
```
