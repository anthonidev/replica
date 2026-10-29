"""
Restaura la base de datos local desde el backup local.

Dos modos de operacion segun la topologia de DATABASE_URL y DATABASE_BACKUP:

1. **Mismo cluster** (mismo host:port — config recomendada): usa
   `CREATE DATABASE clinicsay TEMPLATE "clinicsay-backup"`. Postgres clona los
   archivos de la BD a nivel filesystem — se completa en segundos incluso para
   BDs grandes. Es el camino rapido por defecto.

2. **Clusters distintos** (legacy, fallback): usa `pg_dump --format=custom`
   del backup → archivo temporal → `pg_restore`. Tarda minutos en BDs grandes.

Requiere: psql en PATH (siempre); pg_dump y pg_restore solo si el modo
fallback se activa.
"""
import os
import subprocess
import time

from environment._helpers import (
    StepTimer,
    db_label,
    find_pg_binary,
    format_duration,
    parse_pg_url,
    pg_env,
    require_pg_tools,
    run_psql,
    same_cluster,
    terminate_db_connections,
)


def _restore_via_template(local_url: str, backup_url: str, timer: StepTimer) -> None:
    """Restaura usando CREATE DATABASE x TEMPLATE y. Requiere mismo cluster."""
    from ui import info, success

    local_cfg = parse_pg_url(local_url)
    backup_cfg = parse_pg_url(backup_url)
    local_db = local_cfg["database"]
    backup_db = backup_cfg["database"]

    info("Modo: CREATE DATABASE TEMPLATE (clonacion filesystem-level)")

    with timer.section("Terminar conexiones"):
        terminate_db_connections(local_url, local_db, info)
        terminate_db_connections(local_url, backup_db, info)

    with timer.section("DROP local + CREATE TEMPLATE"):
        info(f"  DROP DATABASE {local_db!r}...")
        run_psql(
            local_url,
            sql=f'DROP DATABASE IF EXISTS "{local_db}" WITH (FORCE);',
            database="postgres",
        )
        info(f"  CREATE DATABASE {local_db!r} TEMPLATE {backup_db!r}...")
        run_psql(
            local_url,
            sql=f'CREATE DATABASE "{local_db}" TEMPLATE "{backup_db}" OWNER {local_cfg["user"]};',
            database="postgres",
        )
    success("BD local recreada desde TEMPLATE")


def _restore_via_pg_dump(local_url: str, backup_url: str, timer: StepTimer) -> None:
    """Fallback para clusters distintos: pg_dump --format=custom + pg_restore."""
    from ui import info, success, error

    local_cfg = parse_pg_url(local_url)
    backup_cfg = parse_pg_url(backup_url)

    info("Modo: pg_dump/pg_restore (clusters distintos — modo lento)")

    if not require_pg_tools("pg_dump", "pg_restore"):
        raise RuntimeError("Herramientas pg_dump/pg_restore no disponibles.")

    with timer.section("Terminar conexiones"):
        terminate_db_connections(local_url, local_cfg["database"], info)

    with timer.section("DROP + CREATE local"):
        for sql, desc in [
            (f'DROP DATABASE IF EXISTS "{local_cfg["database"]}" WITH (FORCE);', "drop"),
            (f'CREATE DATABASE "{local_cfg["database"]}";', "create"),
        ]:
            try:
                run_psql(local_url, sql=sql, database="postgres")
            except RuntimeError as e:
                raise RuntimeError(f"Fallo al {desc}: {e}") from e

    dump_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        ".tmp_backup.dump",
    )
    try:
        with timer.section("pg_dump (backup → archivo)"):
            info("  Exportando backup...")
            r = subprocess.run(
                [
                    find_pg_binary("pg_dump"),
                    "-h", backup_cfg["host"], "-p", backup_cfg["port"],
                    "-U", backup_cfg["user"], "-d", backup_cfg["database"],
                    "--format=custom", "--no-owner", "--no-acl",
                    "-f", dump_file,
                ],
                env=pg_env(backup_cfg), capture_output=True, text=True,
            )
            if r.returncode != 0:
                raise RuntimeError(f"pg_dump fallo: {r.stderr.strip()}")
            dump_size_mb = os.path.getsize(dump_file) / (1024 * 1024)
            info(f"  Dump: {dump_size_mb:.1f} MB")

        with timer.section("pg_restore (archivo → local)"):
            info("  Restaurando en local...")
            r = subprocess.run(
                [
                    find_pg_binary("pg_restore"),
                    "-h", local_cfg["host"], "-p", local_cfg["port"],
                    "-U", local_cfg["user"], "-d", local_cfg["database"],
                    "--no-owner", "--no-acl", "--single-transaction",
                    dump_file,
                ],
                env=pg_env(local_cfg), capture_output=True, text=True,
            )
            # pg_restore retorna 1 si hay warnings no criticos
            if r.returncode not in (0, 1):
                raise RuntimeError(f"pg_restore fallo: {r.stderr.strip()}")
    finally:
        if os.path.exists(dump_file):
            os.remove(dump_file)
    success("BD local recreada desde dump")


def restore_from_backup():
    from ui import print_header, info, success, error, warning, confirm
    from config.settings import get_config

    print_header("Restaurar BD desde Backup")

    if not require_pg_tools("psql"):
        return

    config = get_config()
    databases = config.get("DATABASES", {})

    local_url = databases.get("DATABASE_URL")
    backup_url = databases.get("DATABASE_BACKUP")

    if not local_url:
        error("DATABASE_URL (local) no configurada en .config.yaml")
        return
    if not backup_url:
        error("DATABASE_BACKUP no configurada en .config.yaml")
        return

    info(f"Origen (backup): {db_label(backup_url)}")
    info(f"Destino (local): {db_label(local_url)}")

    use_template = same_cluster(local_url, backup_url)
    if use_template:
        info("Topologia: mismo cluster → restauracion instantanea via TEMPLATE")
    else:
        warning("Topologia: clusters distintos → fallback a pg_dump/pg_restore (lento)")

    warning("Se borraran TODOS los datos actuales de la BD local.")

    if not confirm("¿Restaurar backup → local? Esta accion es irreversible."):
        info("Cancelado.")
        return

    timer = StepTimer()

    try:
        if use_template:
            _restore_via_template(local_url, backup_url, timer)
        else:
            _restore_via_pg_dump(local_url, backup_url, timer)
    except Exception as e:
        error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return

    success(f"Restauracion completada en {format_duration(timer.total)}")
    info(f"  {db_label(backup_url)} → {db_label(local_url)}")
    timer.print_summary()
