"""
Clonacion de ambiente usando COPY binary directo (sin pg_dump para datos).

Flujo (4 pasos):
  1. pg_dump --section=pre-data + --section=post-data del origen, EN PARALELO
  2. Recrear destinos + aplicar pre-data (paralelo entre destinos)
  3. COPY binary tabla a tabla en paralelo (sin restricciones FK activas)
  4. Aplicar post-data + resetear secuencias (paralelo entre destinos)

Modos disponibles:
  - Completo: copia todas las tablas tal cual (comportamiento original).
  - Parcial:  el usuario selecciona una o mas clinicas; solo se copian las
    filas de esas clinicas mas las tablas de sistema globales. Reduce el
    tiempo de clonacion de ~30 min a 3-5 min para 1-2 clinicas.

El modo parcial usa table_registry.py para saber como filtrar cada tabla.
Las tablas no registradas reciben un fallback automatico por clinic_id con
un warning visible para que el desarrollador las catalogue.

Optimizaciones aplicadas:
  - COPY binary directo PG→PG (no serializa a texto ni a archivo intermedio)
  - Hasta 8 tablas en paralelo (ThreadPoolExecutor)
  - SpooledTemporaryFile en lugar de BytesIO: hasta 128 MB en RAM, despues
    spillea a disco (evita picos de GB con tablas grandes)
  - synchronous_commit=off + work_mem alto durante el COPY (menos fsync)
  - maintenance_work_mem=2GB durante post-data (creacion de indices)
  - LOCAL + BACKUP en paralelo en cada paso de schema/datos — cada destino
    es una conexion independiente al cluster local (en mismo cluster, ambos
    procesos PG aprovechan multiples cores)
  - Pre-data y post-data dumps del origen ejecutados simultaneamente — Aiven
    atiende las dos conexiones en paralelo, ahorra ~30s de espera secuencial
  - Lectura unica del origen; vistas BytesIO compartidas entre destinos

Sobre `CREATE DATABASE TEMPLATE`:
  Se evaluo clonar BACKUP via TEMPLATE despues de cargar LOCAL — en bare-metal
  Linux seria casi instantaneo, pero en Docker/OrbStack en Mac la copia
  filesystem-level se ralentiza (~91 MB/s en mediciones) y resulta mas lenta
  que escribir LOCAL+BACKUP en paralelo de inicio. Se mantiene en
  `restore_from_backup.py` donde si gana frente a pg_dump|pg_restore.

Datos copiados:
  - Todas las tablas, todas las columnas (incluyendo bytea).
  - El backend persiste inline en `binaries.data` archivos < 1 MB; en local
    quedan disponibles para los use-cases de descarga sin S3.
"""
import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2

from environment._helpers import (
    StepTimer,
    db_label,
    format_duration,
    parse_pg_url,
    require_pg_tools,
    run_pg_dump,
    run_psql,
)
from environment.table_registry import (
    TableGroup,
    build_copy_query,
    get_spec,
)


# Limite del buffer en RAM para cada COPY antes de spillear a /tmp.
# Tablas chicas se mantienen en memoria (rapido); tablas grandes usan disco.
SPOOL_MAX_MEMORY_BYTES = 128 * 1024 * 1024   # 128 MB

# Settings PG aplicados a la sesion durante el COPY.
# Reducen fsync y aumentan memoria de trabajo, sin riesgo (la BD se va a
# borrar de nuevo si la clonacion falla).
COPY_SESSION_SETTINGS = (
    "SET LOCAL synchronous_commit = off;"
    "SET LOCAL work_mem = '256MB';"
    "SET LOCAL maintenance_work_mem = '1GB';"
)

# Settings PG para aplicar post-data (indices y FKs).
POST_DATA_PREFIX = (
    "SET maintenance_work_mem = '2GB';\n"
    "SET synchronous_commit = off;\n"
)


# ─── conexion psycopg2 ───────────────────────────────────────────────────────

def _connect(url: str) -> psycopg2.extensions.connection:
    cfg = parse_pg_url(url)
    conn = psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        dbname=cfg["database"],
        sslmode=cfg["sslmode"],
        connect_timeout=30,
        options="-c statement_timeout=0",
        keepalives=1,
        keepalives_idle=60,
        keepalives_interval=10,
        keepalives_count=5,
    )
    return conn


# ─── schema: pre-data y post-data ────────────────────────────────────────────

def _dump_section(url: str, section: str, log_fn) -> str:
    log_fn(f"  pg_dump --section={section}...")
    result = run_pg_dump(url, extra_args=[
        "--format=plain",
        f"--section={section}",
        "--no-owner", "--no-acl", "--no-comments", "--no-privileges",
    ])
    return result.stdout.decode("utf-8", errors="replace")


def _apply_sql(url: str, sql: str, label: str, log_fn) -> None:
    cfg = parse_pg_url(url)
    log_fn(f"  Aplicando schema {label} → {cfg['database']}...")
    # ON_ERROR_STOP=0 + ok_codes (0, 3) para tolerar warnings/objetos ya existentes
    run_psql(
        url,
        sql_input=sql,
        extra_args=["--no-psqlrc", "--set", "ON_ERROR_STOP=0", "-q"],
        ok_codes=(0, 3),
    )


# ─── recrear BD ──────────────────────────────────────────────────────────────

def _recreate_db(url: str, log_fn) -> None:
    cfg = parse_pg_url(url)
    db = cfg["database"]
    lbl = db_label(url)

    statements = [
        (
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{db}' AND pid <> pg_backend_pid();",
            "terminar conexiones", True,
        ),
        (f'DROP DATABASE IF EXISTS "{db}";', "drop database", False),
        (f'CREATE DATABASE "{db}";', "create database", False),
    ]
    for sql, desc, ignore in statements:
        try:
            run_psql(url, sql=sql, database="postgres")
        except RuntimeError as e:
            if not ignore:
                raise RuntimeError(f"{desc} fallo en {lbl}: {e}") from e
        log_fn(f"  {desc} → {lbl}")


# ─── inventario de tablas ────────────────────────────────────────────────────

def _get_tables(url: str) -> list[tuple[str, str, int]]:
    """
    Retorna [(schema, tabla, filas_estimadas), ...] ordenado por tamaño desc.
    El orden permite arrancar primero las tablas grandes (LPT scheduling).
    """
    conn = _connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    n.nspname,
                    c.relname,
                    greatest(c.reltuples::bigint, 0) AS est_rows
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind = 'r'
                  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
                ORDER BY c.relpages DESC
            """)
            return [(r[0], r[1], r[2]) for r in cur.fetchall()]
    finally:
        conn.close()


# ─── COPY binario por tabla ───────────────────────────────────────────────────

def _copy_table(src_url: str, dst_urls: list[str], schema: str, table: str) -> int:
    """
    Copia una tabla de src a todos los destinos en paralelo.

    Estrategia:
      1. Lee la tabla completa en SpooledTemporaryFile (RAM hasta 128 MB,
         despues /tmp).
      2. Si hay 1 destino: stream directo desde el buffer.
      3. Si hay >1 destinos: materializa el buffer en bytes una sola vez y
         crea una vista BytesIO por destino. Threads paralelos escriben
         simultaneamente — los bytes son inmutables y compartidos entre
         las vistas (no se duplican en memoria).

    Retorna bytes_transferidos.
    """
    qualified = f'"{schema}"."{table}"'
    copy_sql = f"COPY {qualified} TO STDOUT (FORMAT binary)"
    insert_sql = f"COPY {qualified} FROM STDIN (FORMAT binary)"

    src_conn = _connect(src_url)
    try:
        buf = tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX_MEMORY_BYTES, mode="w+b")
        with src_conn.cursor() as cur:
            cur.copy_expert(copy_sql, buf)
    finally:
        src_conn.close()

    size = buf.tell()
    if size == 0:
        buf.close()
        return 0

    errors: list[str] = []
    err_lock = threading.Lock()

    def write_dst(dst_url: str, reader):
        dst_conn = _connect(dst_url)
        try:
            with dst_conn.cursor() as cur:
                cur.execute(COPY_SESSION_SETTINGS)
                cur.copy_expert(insert_sql, reader)
            dst_conn.commit()
        except Exception as e:
            with err_lock:
                errors.append(f"{db_label(dst_url)}: {e}")
        finally:
            dst_conn.close()

    if len(dst_urls) == 1:
        buf.seek(0)
        write_dst(dst_urls[0], buf)
    else:
        # Materializar una sola vez. Los bytes son inmutables y se comparten
        # entre las BytesIO views, asi que NO se duplica el contenido.
        import io as _io
        buf.seek(0)
        data = buf.read()
        threads = [
            threading.Thread(target=write_dst, args=(u, _io.BytesIO(data)))
            for u in dst_urls
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    buf.close()

    if errors:
        raise RuntimeError("; ".join(errors))

    return size


# ─── aplicar a multiples destinos en paralelo ────────────────────────────────

def _run_per_destination(dst_urls: list[str], fn, *args, **kwargs) -> None:
    """Ejecuta `fn(dst_url, *args, **kwargs)` para cada destino, en paralelo.

    Util para pasos donde LOCAL y BACKUP no compiten por la misma tabla
    (recreate_db, apply pre-data, apply post-data, reset_sequences). Saturarian
    IOPS si fueran al mismo cluster, pero al ser dos instancias PG separadas
    cada una procesa en paralelo y aprovecha CPUs distintos.

    Si una de las llamadas falla, propaga la excepcion (las otras terminan o
    se cancelan al cerrar el pool).
    """
    if len(dst_urls) == 1:
        fn(dst_urls[0], *args, **kwargs)
        return

    with ThreadPoolExecutor(max_workers=len(dst_urls)) as pool:
        futures = [pool.submit(fn, u, *args, **kwargs) for u in dst_urls]
        for f in as_completed(futures):
            f.result()  # propaga excepciones


# ─── secuencias ──────────────────────────────────────────────────────────────

def _reset_sequences(src_url: str, dst_urls: list[str], log_fn) -> None:
    src_conn = _connect(src_url)
    try:
        with src_conn.cursor() as cur:
            cur.execute("""
                SELECT schemaname, sequencename, last_value
                FROM pg_sequences
                WHERE schemaname NOT IN ('pg_catalog','information_schema')
            """)
            seqs = cur.fetchall()
    finally:
        src_conn.close()

    if not seqs:
        return

    sql = "\n".join(
        f"SELECT setval('{schema}.{seq}', {val});"
        for schema, seq, val in seqs
        if val is not None
    )
    if not sql:
        return

    log_fn(f"  Reseteando {len(seqs)} secuencias en {len(dst_urls)} destino(s)...")
    _run_per_destination(dst_urls, _apply_sql, sql, "secuencias", log_fn)


# ─── seleccion de clinicas (modo parcial) ────────────────────────────────────

def _get_clinics_from_origin(src_url: str) -> list[dict]:
    """Lista clinicas disponibles en el origen ordenadas por nombre."""
    conn = _connect(src_url)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.id, c.name, o.name AS org_name
                FROM clinic c
                JOIN organization o ON o.id = c.organization_id
                WHERE c.record_status = 'ACTIVE'
                ORDER BY o.name, c.name
            """)
            return [
                {"id": r[0], "name": r[1], "org": r[2]}
                for r in cur.fetchall()
            ]
    finally:
        conn.close()


def _select_clinics(src_url: str) -> list[dict]:
    """Muestra el dialogo multiselect y retorna las clinicas elegidas."""
    from ui import multi_select, warning

    clinics = _get_clinics_from_origin(src_url)
    if not clinics:
        warning("No se encontraron clinicas activas en el origen.")
        return []

    opciones = [f"{c['name']}  [{c['org']}]" for c in clinics]
    seleccionadas = multi_select("Selecciona las clinicas a clonar:", opciones)

    if not seleccionadas:
        return []

    seleccionadas_set = set(seleccionadas)
    return [c for c, opt in zip(clinics, opciones) if opt in seleccionadas_set]


def _resolve_partial_ids(
    src_url: str,
    clinic_ids: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    """Resuelve site_ids, org_ids, company_ids a partir de las clinicas seleccionadas."""
    conn = _connect(src_url)
    try:
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(clinic_ids))

            cur.execute(
                f"SELECT id FROM site WHERE clinic_id IN ({placeholders})",
                clinic_ids,
            )
            site_ids = tuple(r[0] for r in cur.fetchall())

            cur.execute(
                f"SELECT DISTINCT organization_id FROM clinic WHERE id IN ({placeholders})",
                clinic_ids,
            )
            org_ids = tuple(r[0] for r in cur.fetchall())

            # Companies: las referenciadas por clinic o por site.
            # _ClinicCompanies usa columnas "A" (clinic_id) y "B" (company_id)
            # segun la convencion de Prisma para tablas M:N implicitas.
            cur.execute(
                f"""
                SELECT DISTINCT "B" FROM "_ClinicCompanies"
                WHERE "A" IN ({placeholders})
                UNION
                SELECT DISTINCT default_issuer_company_id FROM clinic
                WHERE id IN ({placeholders}) AND default_issuer_company_id IS NOT NULL
                UNION
                SELECT DISTINCT default_company_id FROM site
                WHERE clinic_id IN ({placeholders}) AND default_company_id IS NOT NULL
                """,
                clinic_ids * 3,
            )
            company_ids = tuple(r[0] for r in cur.fetchall() if r[0])

        return {
            "site_ids":    site_ids,
            "org_ids":     org_ids,
            "company_ids": company_ids,
        }
    finally:
        conn.close()


def _resolve_user_ids(
    src_url: str,
    clinic_ids: tuple[str, ...],
    org_ids: tuple[str, ...],
) -> tuple[str, ...]:
    """Resuelve los user_ids vinculados a las clinicas/orgs seleccionadas,
    mas todos los usuarios root de plataforma (platform_staff)."""
    conn = _connect(src_url)
    try:
        with conn.cursor() as cur:
            c_ph = ",".join(["%s"] * len(clinic_ids))
            o_ph = ",".join(["%s"] * len(org_ids))
            cur.execute(
                f"""
                SELECT DISTINCT user_id FROM user_clinic
                WHERE clinic_id IN ({c_ph})
                UNION
                SELECT DISTINCT user_id FROM user_organization
                WHERE organization_id IN ({o_ph})
                UNION
                SELECT id FROM app_user
                WHERE user_type = 'platform_staff'
                """,
                clinic_ids + org_ids,
            )
            return tuple(r[0] for r in cur.fetchall())
    finally:
        conn.close()


# ─── COPY con filtro (modo parcial) ──────────────────────────────────────────

def _copy_table_partial(
    src_url: str,
    dst_urls: list[str],
    schema: str,
    table: str,
    select_sql: str,
) -> int:
    """Igual que _copy_table pero con SELECT filtrada en lugar de tabla completa.

    `select_sql` es la query completa: 'SELECT * FROM "schema"."tabla" WHERE ...'
    COPY usa la forma  COPY (select_sql) TO STDOUT (FORMAT binary).
    """
    copy_sql    = f"COPY ({select_sql}) TO STDOUT (FORMAT binary)"
    qualified   = f'"{schema}"."{table}"'
    insert_sql  = f"COPY {qualified} FROM STDIN (FORMAT binary)"

    src_conn = _connect(src_url)
    try:
        buf = tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX_MEMORY_BYTES, mode="w+b")
        with src_conn.cursor() as cur:
            cur.copy_expert(copy_sql, buf)
    finally:
        src_conn.close()

    size = buf.tell()
    if size == 0:
        buf.close()
        return 0

    errors: list[str] = []
    err_lock = threading.Lock()

    def write_dst(dst_url: str, reader):
        dst_conn = _connect(dst_url)
        try:
            with dst_conn.cursor() as cur:
                cur.execute(COPY_SESSION_SETTINGS)
                cur.copy_expert(insert_sql, reader)
            dst_conn.commit()
        except Exception as e:
            with err_lock:
                errors.append(f"{db_label(dst_url)}: {e}")
        finally:
            dst_conn.close()

    if len(dst_urls) == 1:
        buf.seek(0)
        write_dst(dst_urls[0], buf)
    else:
        import io as _io
        buf.seek(0)
        data = buf.read()
        threads = [
            threading.Thread(target=write_dst, args=(u, _io.BytesIO(data)))
            for u in dst_urls
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    buf.close()

    if errors:
        raise RuntimeError("; ".join(errors))

    return size


# ─── COPY ROOT con filtro (organization, clinic, site, company) ───────────────

def _copy_root_tables(
    src_url: str,
    dst_urls: list[str],
    clinic_ids: tuple[str, ...],
    site_ids: tuple[str, ...],
    org_ids: tuple[str, ...],
    company_ids: tuple[str, ...],
    log_fn,
) -> int:
    """Copia las entidades raiz filtradas a las clinicas seleccionadas."""
    total = 0

    def _run(table: str, select_sql: str):
        nonlocal total
        size = _copy_table_partial(src_url, dst_urls, "public", table, select_sql)
        total += size
        log_fn(f"  ROOT  public.{table}  {size / 1_048_576:.2f} MB")

    def _ids(tpl):
        return "(" + ", ".join(f"'{v}'" for v in tpl) + ")"

    _run("organization", f'SELECT * FROM "public"."organization" WHERE id IN {_ids(org_ids)}')
    _run("company",      f'SELECT * FROM "public"."company" WHERE id IN {_ids(company_ids)}' if company_ids else
                         f'SELECT * FROM "public"."company" WHERE 1=0')
    _run("clinic",       f'SELECT * FROM "public"."clinic" WHERE id IN {_ids(clinic_ids)}')
    _run("site",         f'SELECT * FROM "public"."site" WHERE clinic_id IN {_ids(clinic_ids)}')
    _run("_ClinicCompanies",
         f'SELECT * FROM "public"."_ClinicCompanies" WHERE "A" IN {_ids(clinic_ids)}')

    return total


# ─── funcion principal ────────────────────────────────────────────────────────

def clone_environment(progress=None):
    """Clona un ambiente remoto (PRD/STG/INT) a las BDs locales.

    Ofrece dos modos:
      - Completo: copia toda la BD (comportamiento original).
      - Parcial:  seleccion de clinicas; solo copia datos de esas clinicas
                  mas tablas de sistema globales.

    Args:
        progress: objeto opcional con metodos thread-safe para reportar
            avance al UI (ej. `OperationProgressModal`). Debe exponer:
              · set_step(index: int, total: int, name: str)
              · set_tables_total(total: int)
              · advance_table(name: str, size_bytes: int)
            Si es None, los reportes se omiten silenciosamente.
    """
    from ui import print_header, info, success, error, warning, step, select, confirm
    from config.settings import get_config

    def _report(method: str, *args, **kwargs):
        """Llama un metodo del objeto progress si existe; ignora si no."""
        if progress is None:
            return
        fn = getattr(progress, method, None)
        if fn is not None:
            try:
                fn(*args, **kwargs)
            except Exception:
                pass  # nunca rompemos el clone por un fallo del UI

    print_header("Clonar Ambiente")

    if not require_pg_tools("pg_dump", "psql"):
        return

    config = get_config()
    databases = config.get("DATABASES", {})

    ENV_OPTIONS = [
        ("INT", "INTEGRATION", databases.get("DATABASE_URL_INTEGRATION")),
        ("STG", "STAGING",     databases.get("DATABASE_URL_STAGING")),
        ("PRD", "PRODUCTION",  databases.get("DATABASE_URL_PRODUCTION")),
    ]
    disponibles = [(s, n, u) for s, n, u in ENV_OPTIONS if u]
    if not disponibles:
        error("No hay URLs remotas en .config.yaml (DATABASES).")
        return

    opciones = [f"{s} — {n}" for s, n, _ in disponibles]
    eleccion = select("Selecciona el ambiente ORIGEN:", opciones)
    if not eleccion:
        return

    idx = opciones.index(eleccion)
    _, env_name, src_url = disponibles[idx]

    local_url  = databases.get("DATABASE_URL")
    backup_url = databases.get("DATABASE_BACKUP")

    if not local_url:
        error("DATABASE_URL (local) no configurada.")
        return

    dst_urls = [local_url]
    if backup_url:
        dst_urls.append(backup_url)

    info(f"Origen : {env_name} — {db_label(src_url)}")
    info(f"Destino: LOCAL — {db_label(local_url)}")
    if backup_url:
        info(f"Backup : LOCAL BACKUP — {db_label(backup_url)}")
    else:
        warning("DATABASE_BACKUP no configurada — solo LOCAL.")

    destinos_label = "LOCAL + BACKUP" if backup_url else "LOCAL"

    # ── Seleccion de modo ────────────────────────────────────────────────────
    modo = select(
        "Selecciona el modo de clonacion:",
        [
            "Completo — copia toda la BD",
            "Parcial  — selecciona clinicas especificas",
        ],
    )
    if not modo:
        info("Cancelado.")
        return

    modo_parcial = modo.startswith("Parcial")

    # ── Seleccion de clinicas (solo modo parcial) ────────────────────────────
    clinicas_seleccionadas: list[dict] = []
    if modo_parcial:
        step("Conectando al origen para listar clinicas...")
        clinicas_seleccionadas = _select_clinics(src_url)
        if not clinicas_seleccionadas:
            info("No se seleccionaron clinicas. Cancelado.")
            return
        info(f"Clinicas seleccionadas ({len(clinicas_seleccionadas)}):")
        for c in clinicas_seleccionadas:
            info(f"  · {c['name']}  [{c['org']}]")

    # ── Confirmacion ─────────────────────────────────────────────────────────
    if modo_parcial:
        nombres = ", ".join(c["name"] for c in clinicas_seleccionadas)
        confirmar_msg = (
            f"¿Clonar {env_name} → {destinos_label} "
            f"(parcial: {nombres})? Se borraran los datos actuales."
        )
    else:
        confirmar_msg = f"¿Clonar {env_name} → {destinos_label}? Se borraran los datos actuales."

    if not confirm(confirmar_msg):
        info("Cancelado.")
        return

    # workers: hasta 8 tablas simultaneas (cap subido desde 6 para CPUs grandes)
    workers = min(max((os.cpu_count() or 4) - 2, 4), 8)
    info(f"Usando {workers} workers paralelos.")
    info("Puedes cancelar en cualquier momento — al reiniciar todo se limpia solo.")

    # Mostrar el modal de progreso (si hay) recien aqui — despues de selects
    # y confirm — para que el tiempo medido refleje solo la operacion.
    _report("start")

    timer = StepTimer()
    errores: list[str] = []

    try:
        # ── 1. Schema pre-data + post-data del origen (paralelo) ────────────
        with timer.section("[1/4] Dumps origen (paralelo)"):
            _report("set_step", 1, 4, "Dumps origen (paralelo)")
            step(f"[1/4] Extrayendo schema pre-data y post-data de {env_name} en paralelo...")
            with ThreadPoolExecutor(max_workers=2) as pool:
                f_pre  = pool.submit(_dump_section, src_url, "pre-data",  info)
                f_post = pool.submit(_dump_section, src_url, "post-data", info)
                pre_data_sql  = f_pre.result()
                post_data_sql = f_post.result()
            success(
                f"Schema obtenido (pre-data {len(pre_data_sql) // 1024} KB, "
                f"post-data {len(post_data_sql) // 1024} KB)"
            )

        # ── 2. Recrear destinos + aplicar pre-data (paralelo entre destinos) ─
        with timer.section("[2/4] Recrear + pre-data destinos"):
            _report("set_step", 2, 4, "Recrear + pre-data destinos")
            step(f"[2/4] Recreando destinos y aplicando estructura ({len(dst_urls)} destinos en paralelo)...")

            def _recreate_and_apply_pre_data(dst_url: str):
                _recreate_db(dst_url, info)
                _apply_sql(dst_url, pre_data_sql, "pre-data", info)

            _run_per_destination(dst_urls, _recreate_and_apply_pre_data)

        # ── 3. COPY datos ────────────────────────────────────────────────────
        with timer.section("[3/4] COPY datos"):
            _report("set_step", 3, 4, "COPY datos")
            tables = _get_tables(src_url)
            total_tables = len(tables)
            done_count   = 0
            total_bytes  = 0
            lock         = threading.Lock()

            if not modo_parcial:
                # ── Modo completo (comportamiento original) ──────────────────
                step(f"[3/4] Copiando datos — modo completo ({workers} tablas en paralelo)...")
                info(f"  {total_tables} tablas encontradas")
                _report("set_tables_total", total_tables)

                # Tablas que se omiten en modo completo por ser muy pesadas y no necesarias en local.
                SKIP_FULL = {"binaries"}

                def copy_worker_full(schema: str, table: str, est_rows: int):
                    nonlocal done_count, total_bytes
                    try:
                        if table in SKIP_FULL:
                            with lock:
                                done_count += 1
                                pct = done_count * 100 // total_tables
                                info(f"  [{pct:3d}%] {done_count}/{total_tables}  {schema}.{table}  [SKIP]")
                            _report("advance_table", f"{schema}.{table}", 0)
                            return
                        size = _copy_table(src_url, dst_urls, schema, table)
                        with lock:
                            done_count  += 1
                            total_bytes += size
                            pct  = done_count * 100 // total_tables
                            mb   = size / 1_048_576
                            rows = f"  (~{est_rows:,} filas)" if est_rows > 0 else ""
                            info(
                                f"  [{pct:3d}%] {done_count}/{total_tables}  "
                                f"{schema}.{table}  {mb:.1f} MB{rows}"
                            )
                        _report("advance_table", f"{schema}.{table}", size)
                    except Exception as e:
                        with lock:
                            errores.append(f"{schema}.{table}: {e}")
                            info(f"  [ERROR] {schema}.{table}: {e}")

                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = [
                        pool.submit(copy_worker_full, schema, table, est)
                        for schema, table, est in tables
                    ]
                    for f in as_completed(futures):
                        f.result()

            else:
                # ── Modo parcial ─────────────────────────────────────────────
                step(
                    f"[3/4] Copiando datos — modo parcial "
                    f"({len(clinicas_seleccionadas)} clinica(s), {workers} tablas en paralelo)..."
                )

                # Resolver IDs auxiliares una sola vez antes del pool
                clinic_ids   = tuple(c["id"] for c in clinicas_seleccionadas)
                partial_ids  = _resolve_partial_ids(src_url, clinic_ids)
                site_ids     = partial_ids["site_ids"]
                org_ids      = partial_ids["org_ids"]
                company_ids  = partial_ids["company_ids"]
                user_ids     = _resolve_user_ids(src_url, clinic_ids, org_ids)

                info(
                    f"  IDs resueltos — "
                    f"{len(clinic_ids)} clinica(s), "
                    f"{len(site_ids)} sede(s), "
                    f"{len(org_ids)} org(s), "
                    f"{len(company_ids)} empresa(s), "
                    f"{len(user_ids)} usuario(s)"
                )

                # Copiar primero las entidades raiz (fuera del pool, orden garantizado)
                _copy_root_tables(
                    src_url, dst_urls,
                    clinic_ids, site_ids, org_ids, company_ids,
                    info,
                )

                # Filtrar del listado de tablas las que ya se copiaron como ROOT
                root_tables = {"organization", "company", "clinic", "site", "_ClinicCompanies"}
                tables_to_copy = [
                    (s, t, e) for s, t, e in tables if t not in root_tables
                ]
                total_tables = len(tables_to_copy)
                info(f"  {total_tables} tablas restantes a procesar")
                _report("set_tables_total", total_tables)

                def copy_worker_partial(schema: str, table: str, est_rows: int):
                    nonlocal done_count, total_bytes
                    try:
                        # Schemas auxiliares (mig.*, mig_growclinic.*) se omiten
                        # siempre en modo parcial — no son datos de clinica.
                        if schema != "public":
                            with lock:
                                info(f"  [SKIP] {schema}.{table}  (schema auxiliar, omitido en modo parcial)")
                                done_count += 1
                            _report("advance_table", f"{schema}.{table}", 0)
                            return

                        spec = get_spec(table)

                        if spec is None:
                            # Fallback: intentar por clinic_id; warning para el dev
                            with lock:
                                warning(
                                    f"  [REGISTRY] {table} no esta en table_registry.py "
                                    f"— usando fallback clinic_id"
                                )
                            select_sql = (
                                f'SELECT * FROM "{schema}"."{table}" '
                                f"WHERE clinic_id IN "
                                + "(" + ", ".join(f"'{v}'" for v in clinic_ids) + ")"
                            )
                            size = _copy_table_partial(src_url, dst_urls, schema, table, select_sql)

                        elif spec.group == TableGroup.SKIP:
                            with lock:
                                info(f"  [SKIP] {schema}.{table}  ({spec.note or 'omitida en modo parcial'})")
                                done_count += 1
                            _report("advance_table", f"{schema}.{table}", 0)
                            return

                        elif spec.group == TableGroup.SYSTEM:
                            size = _copy_table(src_url, dst_urls, schema, table)

                        else:
                            select_sql = build_copy_query(
                                spec, schema,
                                clinic_ids, site_ids, org_ids, company_ids, user_ids,
                            )
                            if select_sql is None:
                                # ROOT ya copiado arriba
                                with lock:
                                    done_count += 1
                                return
                            size = _copy_table_partial(src_url, dst_urls, schema, table, select_sql)

                        with lock:
                            done_count  += 1
                            total_bytes += size
                            pct  = done_count * 100 // total_tables
                            mb   = size / 1_048_576
                            rows = f"  (~{est_rows:,} filas)" if est_rows > 0 else ""
                            info(
                                f"  [{pct:3d}%] {done_count}/{total_tables}  "
                                f"{schema}.{table}  {mb:.1f} MB{rows}"
                            )
                        _report("advance_table", f"{schema}.{table}", size)

                    except Exception as e:
                        with lock:
                            errores.append(f"{schema}.{table}: {e}")
                            info(f"  [ERROR] {schema}.{table}: {e}")

                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = [
                        pool.submit(copy_worker_partial, schema, table, est)
                        for schema, table, est in tables_to_copy
                    ]
                    for f in as_completed(futures):
                        f.result()

            if errores:
                warning(f"  {len(errores)} tabla(s) con error")
            else:
                mb_total = (total_bytes if not modo_parcial else total_bytes) / 1_048_576
                success(f"  {total_tables} tablas procesadas — {mb_total:.1f} MB transferidos")

        # ── 4. Post-data + secuencias (paralelo entre destinos) ──────────────
        with timer.section("[4/4] Post-data + secuencias"):
            _report("set_step", 4, 4, "Post-data + secuencias")
            step(f"[4/4] Aplicando indices, FK y secuencias ({len(dst_urls)} destinos en paralelo)...")
            # Prefijar settings agresivos para acelerar CREATE INDEX y FK.
            _run_per_destination(
                dst_urls,
                _apply_sql, POST_DATA_PREFIX + post_data_sql, "post-data", info,
            )
            _reset_sequences(src_url, dst_urls, info)

    except Exception as e:
        error(f"Fallo inesperado: {e}")
        import traceback
        traceback.print_exc()
        return

    modo_label = "parcial" if modo_parcial else "completo"
    if not errores:
        success(
            f"Clonacion {modo_label} completada en {format_duration(timer.total)}"
            f"  ({env_name} → {destinos_label})"
        )
    else:
        warning(f"Clonacion finalizada con errores en {format_duration(timer.total)}")
        for e in errores:
            error(f"  {e}")
    timer.print_summary()
