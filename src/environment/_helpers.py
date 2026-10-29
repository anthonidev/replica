"""
Helpers compartidos por los scripts de Entorno.

Cubren cuatro areas comunes:
  · Parseo y representacion de DATABASE_URLs (parse_pg_url, db_label, pg_env,
    same_cluster).
  · Localizacion y verificacion de las PostgreSQL client tools
    (find_pg_binary, require_pg_tools).
  · Wrappers de subprocess para psql / pg_dump (run_psql, run_pg_dump).
  · Reporte de tiempos por seccion (print_timings).

Ningun helper depende del entorno seleccionado en la app: estos scripts trabajan
sobre URLs explicitas (origen/destino), no sobre `DATABASE_URL_<env>`.
"""
import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from typing import Optional, Sequence
from urllib.parse import urlparse


# ─── URL parsing ─────────────────────────────────────────────────────────────

def parse_pg_url(url: str) -> dict:
    """Parsea una DATABASE_URL en sus componentes.

    Retorna dict con: host, port (str), user, password, database, sslmode.
    `sslmode` es 'require' si la URL lo declara, 'prefer' en caso contrario.
    """
    parsed = urlparse(url)
    db = parsed.path[1:] if parsed.path else ""
    if "?" in db:
        db = db.split("?")[0]
    return {
        "host": parsed.hostname,
        "port": str(parsed.port or 5432),
        "user": parsed.username,
        "password": parsed.password or "",
        "database": db,
        "sslmode": "require" if "sslmode=require" in url else "prefer",
    }


def db_label(url: str) -> str:
    """Etiqueta corta legible: 'database@host:port'."""
    cfg = parse_pg_url(url)
    return f"{cfg['database']}@{cfg['host']}:{cfg['port']}"


def same_cluster(url_a: str, url_b: str) -> bool:
    """True si ambas URLs apuntan al mismo servidor Postgres (mismo host:port).

    Habilita optimizaciones que requieren mismo cluster: `CREATE DATABASE x
    TEMPLATE y`, `\\copy` entre databases via socket Unix interno, etc.
    """
    a = parse_pg_url(url_a)
    b = parse_pg_url(url_b)
    return a["host"] == b["host"] and a["port"] == b["port"]


def pg_env(cfg: dict) -> dict:
    """os.environ enriquecido con PGPASSWORD (y PGSSLMODE si require).

    `cfg` es el dict que devuelve `parse_pg_url`.
    """
    env = os.environ.copy()
    env["PGPASSWORD"] = cfg["password"]
    if cfg.get("sslmode") == "require":
        env["PGSSLMODE"] = "require"
    return env


# ─── Localizacion de PostgreSQL client tools ─────────────────────────────────

# Rutas preferidas para PostgreSQL 17 (Homebrew Mac). Si no existen, cae al PATH.
_PG17_CANDIDATES = (
    "/opt/homebrew/opt/postgresql@17/bin",
    "/usr/local/opt/postgresql@17/bin",
)


def find_pg_binary(name: str) -> str:
    """Devuelve la ruta absoluta a un binario de PostgreSQL.

    Prefiere PostgreSQL 17 (rutas Homebrew); si no, usa el del PATH.
    Retorna `name` (sin ruta) como ultimo recurso, para que subprocess
    intente resolverlo segun PATH y falle de forma uniforme.
    """
    for base in _PG17_CANDIDATES:
        candidate = os.path.join(base, name)
        if os.path.isfile(candidate):
            return candidate
    in_path = shutil.which(name)
    return in_path or name


def require_pg_tools(*tools: str) -> bool:
    """Verifica que los binarios pedidos esten disponibles.

    Imprime un error con `ui.error` por cada faltante y retorna True/False.
    """
    from ui import error
    missing = [t for t in tools if not shutil.which(t) and not _has_in_pg17(t)]
    if missing:
        for t in missing:
            error(f"'{t}' no encontrado. Instala las PostgreSQL client tools.")
        return False
    return True


def _has_in_pg17(name: str) -> bool:
    return any(os.path.isfile(os.path.join(b, name)) for b in _PG17_CANDIDATES)


# ─── Subprocess wrappers ─────────────────────────────────────────────────────

def run_psql(
    url: str,
    *,
    sql: Optional[str] = None,
    sql_input: Optional[str] = None,
    database: Optional[str] = None,
    extra_args: Sequence[str] = (),
    check: bool = True,
    ok_codes: Sequence[int] = (0,),
) -> subprocess.CompletedProcess:
    """Ejecuta `psql` contra la BD indicada.

    · `sql`        → se pasa con `-c "<sql>"` (una sola sentencia corta).
    · `sql_input`  → se envia por stdin (scripts SQL completos, multi-statement).
    · `database`   → si se especifica, override del nombre de BD (util para
                     conectar a `postgres` y emitir DROP/CREATE de otra BD).
    · `extra_args` → flags adicionales (ej. ["--no-psqlrc", "-q"]).
    · `check`      → si True, lanza RuntimeError cuando returncode no esta
                     en `ok_codes` (default solo 0). Pon (0, 3) para ignorar
                     errores no fatales en scripts grandes.
    """
    cfg = parse_pg_url(url)
    target_db = database or cfg["database"]
    cmd = [
        find_pg_binary("psql"),
        "-h", cfg["host"], "-p", cfg["port"],
        "-U", cfg["user"], "-d", target_db,
        *extra_args,
    ]
    if sql is not None:
        cmd.extend(["-c", sql])

    result = subprocess.run(
        cmd,
        env=pg_env(cfg),
        input=sql_input.encode("utf-8") if sql_input is not None else None,
        capture_output=True,
    )
    if check and result.returncode not in ok_codes:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(stderr or f"psql fallo con codigo {result.returncode}")
    return result


def terminate_db_connections(url: str, target_db: str, log_fn=None) -> None:
    """Termina todas las conexiones activas a `target_db`.

    Util antes de `DROP DATABASE` o de usar una BD como TEMPLATE (ambos
    requieren que no haya conexiones activas).
    """
    if log_fn:
        log_fn(f"  Terminando conexiones a {target_db!r}...")
    run_psql(
        url,
        sql=(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{target_db}' AND pid <> pg_backend_pid();"
        ),
        database="postgres",
        check=False,
    )


def run_pg_dump(
    url: str,
    *,
    extra_args: Sequence[str] = (),
    output_file: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """Ejecuta `pg_dump` contra la BD indicada.

    · `extra_args`  → flags especificos del caller (ej. ["--section=pre-data",
                      "--format=plain", "--no-owner"]).
    · `output_file` → si se pasa, agrega `-f <file>`; si no, el dump va a stdout
                      (capture_output=True, lee `result.stdout`).

    Lanza RuntimeError si returncode != 0.
    """
    cfg = parse_pg_url(url)
    cmd = [
        find_pg_binary("pg_dump"),
        "-h", cfg["host"], "-p", cfg["port"],
        "-U", cfg["user"], "-d", cfg["database"],
        *extra_args,
    ]
    if output_file:
        cmd.extend(["-f", output_file])

    result = subprocess.run(cmd, env=pg_env(cfg), capture_output=True)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(stderr or f"pg_dump fallo con codigo {result.returncode}")
    return result


# ─── Formato de duraciones ───────────────────────────────────────────────────

def format_duration(seconds: float) -> str:
    """Formatea una duracion en segundos a un string legible.

    < 60s → 'X.Xs'        (ej. '32.4s')
    >= 60s → 'Mm SSs'     (ej. '3m 45s')
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    mins = int(seconds // 60)
    secs = int(round(seconds - mins * 60))
    if secs == 60:
        mins += 1
        secs = 0
    return f"{mins}m {secs:02d}s"


# ─── Reporte de tiempos por seccion ──────────────────────────────────────────

class StepTimer:
    """Contexto para medir el tiempo de secciones logicas y reportarlas al final.

    Uso:
        timer = StepTimer()
        with timer.section("Pre-data"):
            ...
        with timer.section("COPY datos"):
            ...
        timer.print_summary()       # imprime tabla con tiempos + total
    """

    def __init__(self):
        self.timings: dict[str, float] = {}
        self._t_start = time.time()

    @contextmanager
    def section(self, name: str):
        t0 = time.time()
        try:
            yield
        finally:
            elapsed = time.time() - t0
            # Si el nombre se repite (multi-pass), acumula el tiempo.
            self.timings[name] = self.timings.get(name, 0.0) + elapsed

    @property
    def total(self) -> float:
        return time.time() - self._t_start

    def print_summary(self, title: str = "Tiempos por seccion") -> None:
        from ui import info
        if not self.timings:
            return
        width = max(len(k) for k in self.timings.keys())
        width = max(width, len("Total"))
        # Ancho de la columna de duraciones para alinear (mayor entre 'Total'
        # y todos los timings). Usa format_duration para mostrar 'Xm YYs'.
        durations = {k: format_duration(v) for k, v in self.timings.items()}
        total_str = format_duration(self.total)
        time_width = max(max(len(s) for s in durations.values()), len(total_str))
        info(title + ":")
        for name, dur_str in durations.items():
            info(f"  {name:<{width}}  {dur_str:>{time_width}}")
        info(f"  {'─' * (width + time_width + 2)}")
        info(f"  {'Total':<{width}}  {total_str:>{time_width}}")
