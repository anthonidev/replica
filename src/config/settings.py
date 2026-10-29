"""
Configuración central de Replica.

Lee variables de conexión desde .env en la raíz del proyecto.
No requiere .config.yaml — todas las URLs viven en el .env.
"""
import os
import re

ENV_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".env",
)

ENVIRONMENTS = ["STAGING", "INTEGRATION", "PRODUCTION"]

_config: dict = {}
_current_env: str = "STAGING"


def _parse_env_file(path: str) -> dict:
    """Lee un archivo .env y devuelve un dict con las variables."""
    result = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                # Quitar comillas simples o dobles alrededor del valor
                value = value.strip()
                value = re.sub(r'^(["\'])(.*)\1$', r'\2', value)
                result[key] = value
    except FileNotFoundError:
        pass
    return result


def load_config() -> dict:
    global _config

    env_vars = _parse_env_file(ENV_FILE)

    # Normalizar: DATABASE_URL_LOCAL → DATABASE_URL (clave que espera el código)
    databases = {
        "DATABASE_URL":         env_vars.get("DATABASE_URL_LOCAL", ""),
        "DATABASE_BACKUP":      env_vars.get("DATABASE_URL_BACKUP", ""),
        "DATABASE_URL_INTEGRATION": env_vars.get("DATABASE_URL_INTEGRATION", ""),
        "DATABASE_URL_STAGING":     env_vars.get("DATABASE_URL_STAGING", ""),
        "DATABASE_URL_PRODUCTION":  env_vars.get("DATABASE_URL_PRODUCTION", ""),
    }

    _config = {"DATABASES": databases}

    # Exportar a os.environ para que psycopg2 / helpers las encuentren
    if not os.environ.get("DATABASE_URL") and databases["DATABASE_URL"]:
        os.environ["DATABASE_URL"] = databases["DATABASE_URL"]
    if databases["DATABASE_BACKUP"]:
        os.environ["DATABASE_BACKUP"] = databases["DATABASE_BACKUP"]

    return _config


def get_config() -> dict:
    return _config


def get_environment() -> str:
    return _current_env


def set_environment(env_name: str) -> None:
    global _current_env
    if env_name not in ENVIRONMENTS:
        raise ValueError(f"Entorno inválido: {env_name}. Opciones: {ENVIRONMENTS}")
    _current_env = env_name
