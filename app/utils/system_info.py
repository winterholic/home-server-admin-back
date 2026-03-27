import platform
import psutil
from app.schemas.system import SystemInfoResponse


def get_system_info() -> SystemInfoResponse:
    uname = platform.uname()
    return SystemInfoResponse(
        hostname=uname.node,
        os=f"{uname.system} {uname.release}",
        os_version=uname.version,
        architecture=uname.machine,
        processor=uname.processor or "Unknown",
        cpu_count_physical=psutil.cpu_count(logical=False),
        cpu_count_logical=psutil.cpu_count(logical=True),
        total_memory=psutil.virtual_memory().total,
        total_swap=psutil.swap_memory().total,
        boot_time=psutil.boot_time(),
    )
