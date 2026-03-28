import asyncio
import subprocess
import shutil
import time
import psutil as ps
from app.schemas.service import ServiceInfo, ServiceControlResponse


def _run_cmd(cmd: list[str], timeout: int = 10) -> tuple[int, str, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except FileNotFoundError:
        return -1, "", f"Command not found: {cmd[0]}"


# ── Systemd (batched) ──────────────────────────────────────────────────────────

def _get_systemd_services_batch() -> list[ServiceInfo]:
    """Return all systemd service statuses using at most 2 systemctl calls."""
    code, stdout, _ = _run_cmd([
        "systemctl", "list-units", "--type=service",
        "--all", "--no-pager", "--plain", "--no-legend",
    ])
    if code != 0 or not stdout:
        return []

    service_units: list[str] = []
    for line in stdout.splitlines():
        parts = line.split()
        if parts and parts[0].endswith(".service"):
            service_units.append(parts[0])

    if not service_units:
        return []

    # Batch into chunks to avoid arg-list-too-long errors (ARG_MAX)
    CHUNK = 50
    services: list[ServiceInfo] = []
    props_str = "Id,ActiveState,MainPID,MemoryCurrent,Description,ActiveEnterTimestamp"
    for i in range(0, len(service_units), CHUNK):
        chunk = service_units[i:i + CHUNK]
        code, stdout, _ = _run_cmd(
            ["systemctl", "show", "--no-pager", f"--property={props_str}"] + chunk,
            timeout=15,
        )
        if code != 0:
            continue
        services.extend(_parse_show_output(stdout))

    return services


def _parse_show_output(stdout: str) -> list[ServiceInfo]:
    """Parse 'systemctl show' output (blocks separated by blank lines)."""
    result: list[ServiceInfo] = []
    current: dict[str, str] = {}
    for line in stdout.splitlines():
        if not line.strip():
            if current.get("Id"):
                result.append(_props_to_service_info(current))
            current = {}
        elif "=" in line:
            k, v = line.split("=", 1)
            current[k.strip()] = v.strip()
    if current.get("Id"):
        result.append(_props_to_service_info(current))
    return result


def _props_to_service_info(props: dict[str, str]) -> ServiceInfo:
    svc_id = props.get("Id", "")
    name = svc_id[:-8] if svc_id.endswith(".service") else svc_id

    active_state = props.get("ActiveState", "inactive")
    status = (
        "active" if active_state == "active"
        else "failed" if active_state == "failed"
        else "inactive"
    )

    mem_str = props.get("MemoryCurrent", "")
    memory = int(mem_str) if mem_str.isdigit() else 0

    pid_str = props.get("MainPID", "0")
    pid = int(pid_str) if pid_str.isdigit() and pid_str != "0" else None

    return ServiceInfo(
        name=name,
        type="systemd",
        description=props.get("Description", ""),
        status=status,
        uptime=props.get("ActiveEnterTimestamp", "-"),
        memory=memory,
        memory_percent=0.0,
        pid=pid,
    )


def control_systemd_service(service_name: str, action: str) -> ServiceControlResponse:
    if action not in ("start", "stop", "restart", "reload"):
        return ServiceControlResponse(success=False, message=f"Invalid action: {action}")
    code, stdout, stderr = _run_cmd(["sudo", "systemctl", action, service_name])
    return ServiceControlResponse(
        success=code == 0,
        message=stdout if code == 0 else stderr,
    )


def get_service_logs(service_name: str, lines: int = 50) -> list[str]:
    """Return the last *lines* journal log entries for a systemd service."""
    code, stdout, stderr = _run_cmd(
        ["journalctl", "-u", service_name, "-n", str(lines), "--no-pager", "--output=short"]
    )
    if code != 0:
        return [stderr] if stderr else []
    return [ln for ln in stdout.splitlines() if ln.strip()]


# ── Docker ────────────────────────────────────────────────────────────────────

def _docker_available() -> bool:
    return shutil.which("docker") is not None


def get_docker_containers(filter_names: list[str] | None = None) -> list[ServiceInfo]:
    if not _docker_available():
        return []

    fmt = '{{.ID}}\t{{.Names}}\t{{.Status}}\t{{.State}}\t{{.Image}}'
    code, stdout, _ = _run_cmd(["docker", "ps", "-a", "--format", fmt])
    if code != 0 or not stdout:
        return []

    containers: list[ServiceInfo] = []
    for line in stdout.split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 5:
            continue

        cid, name, status_text, state, image = parts[:5]

        if filter_names and name not in filter_names:
            continue

        status = (
            "active" if state == "running"
            else "failed" if state in ("exited", "dead")
            else "inactive"
        )

        memory = 0
        if state == "running":
            _, mem_out, _ = _run_cmd([
                "docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", cid
            ])
            if mem_out:
                try:
                    used_str = mem_out.split("/")[0].strip()
                    if "GiB" in used_str:
                        memory = int(float(used_str.replace("GiB", "")) * 1073741824)
                    elif "MiB" in used_str:
                        memory = int(float(used_str.replace("MiB", "")) * 1048576)
                    elif "KiB" in used_str:
                        memory = int(float(used_str.replace("KiB", "")) * 1024)
                except (ValueError, IndexError):
                    pass

        containers.append(ServiceInfo(
            name=name,
            type="docker",
            description=f"Image: {image}",
            status=status,
            uptime=status_text,
            memory=memory,
            memory_percent=0.0,
            container_id=cid,
        ))

    return containers


def control_docker_container(container_name: str, action: str) -> ServiceControlResponse:
    if action not in ("start", "stop", "restart"):
        return ServiceControlResponse(success=False, message=f"Invalid action: {action}")
    code, stdout, stderr = _run_cmd(["docker", action, container_name])
    return ServiceControlResponse(success=code == 0, message=stdout if code == 0 else stderr)


def get_docker_logs(container_name: str, lines: int = 50) -> list[str]:
    """Return the last *lines* log entries for a docker container."""
    code, stdout, stderr = _run_cmd(
        ["docker", "logs", "--tail", str(lines), container_name],
        timeout=10,
    )
    if code != 0:
        return [stderr] if stderr else []
    # docker logs writes to stderr by default; combine both
    combined = stdout + ("\n" + stderr if stderr else "")
    return [ln for ln in combined.splitlines() if ln.strip()]


# ── Nohup / User processes ────────────────────────────────────────────────────

def get_nohup_service_status(name: str, keyword: str) -> ServiceInfo:
    info: dict = {
        "name": name,
        "type": "nohup",
        "description": f"Process keyword: {keyword}",
        "status": "inactive",
        "uptime": "-",
        "memory": 0,
        "memory_percent": 0.0,
        "pid": None,
    }

    for proc in ps.process_iter(["pid", "name", "cmdline", "memory_info", "create_time"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or [])
            if keyword in cmdline:
                mem = proc.info.get("memory_info")
                create_time = proc.info.get("create_time", 0)
                uptime_sec = int(time.time() - create_time) if create_time else 0
                days = uptime_sec // 86400
                hours = (uptime_sec % 86400) // 3600
                mins = (uptime_sec % 3600) // 60

                info["status"] = "active"
                info["pid"] = proc.info["pid"]
                info["memory"] = mem.rss if mem else 0
                info["memory_percent"] = proc.memory_percent()
                info["uptime"] = f"{days}d {hours}h {mins}m"
                break
        except (ps.NoSuchProcess, ps.AccessDenied):
            continue

    return ServiceInfo(**info)


def control_nohup_service(name: str, keyword: str, action: str) -> ServiceControlResponse:
    if action == "stop":
        for proc in ps.process_iter(["pid", "cmdline"]):
            try:
                cmdline = " ".join(proc.info.get("cmdline") or [])
                if keyword in cmdline:
                    proc.terminate()
                    return ServiceControlResponse(
                        success=True,
                        message=f"Process {name} (PID {proc.pid}) terminated",
                    )
            except (ps.NoSuchProcess, ps.AccessDenied) as e:
                return ServiceControlResponse(success=False, message=str(e))
        return ServiceControlResponse(success=False, message=f"Process '{name}' not found")

    if action == "restart":
        # Stop existing process first, then let external supervisor restart it
        stop_result = control_nohup_service(name, keyword, "stop")
        if not stop_result.success:
            return ServiceControlResponse(
                success=False,
                message=f"Could not stop '{name}': {stop_result.message}",
            )
        return ServiceControlResponse(
            success=True,
            message=f"Process '{name}' stopped. Restart requires external management.",
        )

    return ServiceControlResponse(
        success=False,
        message=f"Action '{action}' not supported for nohup services",
    )


def _discover_nohup_processes() -> list[ServiceInfo]:
    result: list[ServiceInfo] = []
    for proc in ps.process_iter(["pid", "ppid", "name", "cmdline", "memory_info", "create_time", "uids"]):
        try:
            if proc.info.get("ppid") != 1:
                continue
            cmdline_list = proc.info.get("cmdline") or []
            if not cmdline_list:
                continue
            cmdline = " ".join(cmdline_list)
            if cmdline.startswith("["):
                continue
            uid = (proc.info.get("uids") or [0, 0, 0])[0]
            if uid < 1000:
                continue

            mem = proc.info.get("memory_info")
            create_time = proc.info.get("create_time", 0)
            uptime_sec = int(time.time() - create_time) if create_time else 0
            days, remainder = divmod(uptime_sec, 86400)
            hours, mins = divmod(remainder, 3600)
            mins //= 60

            result.append(ServiceInfo(
                name=proc.info.get("name", cmdline_list[0]),
                type="nohup",
                description=cmdline,
                status="active",
                uptime=f"{days}d {hours}h {mins}m",
                memory=mem.rss if mem else 0,
                memory_percent=proc.memory_percent(),
                pid=proc.info["pid"],
            ))
        except (ps.NoSuchProcess, ps.AccessDenied):
            continue
    return result


# ── Public API ────────────────────────────────────────────────────────────────

def _collect_all_services_sync() -> list[ServiceInfo]:
    services: list[ServiceInfo] = []
    services.extend(_get_systemd_services_batch())
    services.extend(get_docker_containers())
    services.extend(_discover_nohup_processes())
    return services


async def get_all_services() -> list[ServiceInfo]:
    """Collect all services without blocking the async event loop."""
    return await asyncio.to_thread(_collect_all_services_sync)


async def control_service(
    service_name: str, action: str, service_type: str | None = None
) -> ServiceControlResponse:
    if service_type is None:
        code, _, _ = _run_cmd(["systemctl", "cat", f"{service_name}.service"], timeout=5)
        if code == 0:
            service_type = "systemd"
        else:
            containers = get_docker_containers()
            if any(c.name == service_name for c in containers):
                service_type = "docker"
            else:
                service_type = "nohup"

    if service_type == "systemd":
        return control_systemd_service(service_name, action)
    elif service_type == "docker":
        return control_docker_container(service_name, action)
    elif service_type == "nohup":
        return control_nohup_service(service_name, service_name, action)
    else:
        return ServiceControlResponse(success=False, message=f"Unknown service: {service_name}")
