#!/bin/bash

set -e

APP_NAME="home-server-admin"
COMPOSE_FILE="docker-compose.yml"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Home Server Admin 백엔드 배포${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

if [ ! -f ".env" ]; then
    echo -e "${RED}✗${NC} .env 파일이 없습니다!"
    exit 1
fi
echo -e "${GREEN}✓${NC} .env 파일 확인됨"

if [ ! -f "$COMPOSE_FILE" ]; then
    echo -e "${RED}✗${NC} $COMPOSE_FILE 파일이 없습니다!"
    exit 1
fi
echo -e "${GREEN}✓${NC} $COMPOSE_FILE 파일 확인됨"

echo ""
echo -e "${BLUE}[1/4]${NC} Docker 이미지 빌드 중..."
docker compose build --no-cache app

echo ""
echo -e "${BLUE}[2/4]${NC} 기존 컨테이너 중지 중..."
docker compose down --remove-orphans

echo ""
echo -e "${BLUE}[3/4]${NC} 새 컨테이너 시작 중..."
docker compose up -d

echo ""
echo -e "${BLUE}[4/4]${NC} 헬스체크 진행 중..."
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if docker compose ps | grep -q "home-server-admin-app.*Up"; then
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5004/api/health || echo "000")

        if [ "$HTTP_CODE" == "200" ]; then
            echo -e "${GREEN}✓${NC} 헬스체크 성공 (HTTP $HTTP_CODE)"
            break
        fi
    fi

    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo -e "  시도 $RETRY_COUNT/$MAX_RETRIES..."

    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        echo -e "${RED}✗${NC} 헬스체크 실패! 배포를 중단합니다."
        echo -e "\n${RED}컨테이너 로그:${NC}"
        docker compose logs --tail 50 app
        docker compose down
        exit 1
    fi

    sleep 2
done

echo ""
mkdir -p logs
DEPLOY_LOG="logs/deploy.log"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Docker Compose deployment completed" >> $DEPLOY_LOG

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  배포 완료!${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "배포 시간: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

echo -e "${BLUE}실행 중인 서비스:${NC}"
docker compose ps

echo ""
echo -e "${YELLOW}유용한 명령어:${NC}"
echo -e "  로그 확인:        docker compose logs -f app"
echo -e "  서비스 재시작:    docker compose restart app"
echo -e "  서비스 중지:      docker compose stop"
echo -e "  전체 중지:        docker compose down"
echo ""

exit 0
