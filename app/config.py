from pydantic_settings import BaseSettings
from functools import lru_cache
from urllib.parse import quote_plus


class Settings(BaseSettings):
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "nodectrl"

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = False
    secret_key: str = "change-this"

    cors_origins: str = "http://localhost:5173"

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_tls: bool = True

    monitor_interval: int = 300
    data_retention_days: int = 30

    systemd_services: str = "nginx,mariadb,redis-server,cloudflared"
    docker_containers: str = ""
    nohup_services: str = ""

    nginx_access_log: str = "/var/log/nginx/access.log"
    nginx_error_log: str = "/var/log/nginx/error.log"
    auth_log: str = "/var/log/auth.log"
    syslog: str = "/var/log/syslog"
    fail2ban_log: str = "/var/log/fail2ban.log"

    @property
    def database_url(self) -> str:
        return (
            f"mysql+aiomysql://{quote_plus(self.db_user)}:{quote_plus(self.db_password)}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"mysql+pymysql://{quote_plus(self.db_user)}:{quote_plus(self.db_password)}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def systemd_service_list(self) -> list[str]:
        return [s.strip() for s in self.systemd_services.split(",") if s.strip()]

    @property
    def docker_container_list(self) -> list[str]:
        return [c.strip() for c in self.docker_containers.split(",") if c.strip()]

    @property
    def nohup_service_list(self) -> list[dict]:
        # NOTE: format is "display_name:process_keyword" per entry
        result = []
        for entry in self.nohup_services.split(","):
            entry = entry.strip()
            if not entry:
                continue
            if ":" in entry:
                name, keyword = entry.split(":", 1)
                result.append({"name": name.strip(), "keyword": keyword.strip()})
            else:
                result.append({"name": entry, "keyword": entry})
        return result

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
