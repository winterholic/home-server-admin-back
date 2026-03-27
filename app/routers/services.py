from fastapi import APIRouter, HTTPException, Query
from app.services.service_manager import get_all_services, control_service, get_service_logs
from app.schemas.service import (
    ServiceListResponse, ServiceSummary,
    ServiceControlRequest, ServiceControlResponse,
    ServiceLogsResponse,
)

router = APIRouter(prefix="/api/services", tags=["Service Management"])


@router.get("", response_model=ServiceListResponse)
async def list_services():
    services = await get_all_services()

    return ServiceListResponse(
        services=services,
        summary=ServiceSummary(
            total=len(services),
            active=sum(1 for s in services if s.status == "active"),
            failed=sum(1 for s in services if s.status == "failed"),
            inactive=sum(1 for s in services if s.status == "inactive"),
        ),
    )


@router.post("/{service_name}/control", response_model=ServiceControlResponse)
async def control_service_endpoint(service_name: str, request: ServiceControlRequest):
    result = await control_service(service_name, request.action, request.service_type)

    if not result.success:
        raise HTTPException(status_code=500, detail=result.message)

    return result


@router.get("/{service_name}/logs", response_model=ServiceLogsResponse)
async def get_service_log_lines(
    service_name: str,
    lines: int = Query(50, ge=1, le=200),
):
    log_lines = get_service_logs(service_name, lines)
    return ServiceLogsResponse(service_name=service_name, lines=log_lines)
