# Clinicsay Replica

TUI para clonar ambientes de base de datos (INT/STG/PRD → local) y restaurar desde backup local.

---

## Requisitos

- Python 3.10+
- Docker y Docker Compose
- Acceso de red a los ambientes remotos (VPN si aplica)

---

## Instalación

### 1. Levantar la base de datos local

```bash
cd docker
docker compose up -d
```

Esto levanta un PostgreSQL 17 en `localhost:5432` con usuario `clinicsay`, contraseña `clinicsay` y base de datos `clinicsay`.

### 2. Configurar variables de entorno

Crea un archivo `.env` en la raíz del proyecto:

```env
DATABASE_URL_LOCAL="postgresql://clinicsay:clinicsay@localhost:5432/clinicsay?schema=public"
DATABASE_URL_BACKUP="postgresql://clinicsay:clinicsay@localhost:5432/clinicsay-backup?schema=public"
DATABASE_URL_INTEGRATION="postgres://usuario:password@host-int:puerto/defaultdb?sslmode=require"
DATABASE_URL_STAGING="postgres://usuario:password@host-stg:puerto/defaultdb?sslmode=require"
DATABASE_URL_PRODUCTION="postgres://usuario:password@host-prd:puerto/defaultdb?sslmode=require"
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Ejecutar

```bash
python app.py
```

---

## Funcionalidades

### Clonar Ambiente

Clona una base de datos remota (Integration, Staging o Production) hacia la instancia local.

**Origen** — selecciona el ambiente fuente:
- `STG` — Staging
- `INT` — Integration
- `PRD` — Production (marcado en amarillo como advertencia)

**Modo**:

- **Completo** — copia toda la base de datos. Usa `pg_dump` en paralelo para pre-data y post-data, y `COPY` binario con hasta 8 workers concurrentes para las tablas. Tiempo estimado: 20-40 min dependiendo del tamaño.

- **Parcial** — permite seleccionar clínicas específicas. Solo se copian los datos de esas clínicas más las tablas de sistema. Tiempo estimado: 3-5 min para 1-2 clínicas.

  Al seleccionar modo Parcial aparece un buscador de clínicas. Usa `Space` para marcar/desmarcar, escribe en el campo de búsqueda para filtrar por nombre u organización.

Una vez configurado, presiona **Ejecutar**. El progreso se muestra en el panel de log inferior.

#### Proceso interno (Completo)

1. `pg_dump --section=pre-data` y `--section=post-data` en paralelo desde el origen
2. Recreación de la base local (`DROP` + `CREATE DATABASE`)
3. Aplicación del schema (pre-data)
4. `COPY` binario tabla por tabla con hasta 8 workers paralelos
5. Aplicación de índices y foreign keys (post-data)
6. Reset de secuencias

#### Proceso interno (Parcial)

Igual al completo pero las tablas de datos se filtran por `clinic_id`. El registro de tablas (`table_registry.py`) define cómo filtrar cada tabla: directamente por `clinic_id`, por join, por site, o si se omite completamente.

---

### Restaurar desde Backup

Restaura la base de datos local desde el backup local (`clinicsay-backup`).

La estrategia se elige automáticamente según la topología:

- **Mismo cluster** (recomendado) — usa `CREATE DATABASE clinicsay TEMPLATE "clinicsay-backup"`. Opera a nivel filesystem, es casi instantáneo.
- **Cluster distinto** — usa `pg_dump | pg_restore`. Más lento, varios minutos.

Presiona **Restaurar**. La operación sobreescribe completamente la base de datos local.

---

## Cambiar entorno activo

Presiona `e` para abrir el selector de entorno. El entorno activo se usa como contexto visual; el origen real de la clonación se elige dentro de la tarjeta Clonar.

---

## Teclas

| Tecla | Acción |
|-------|--------|
| `e` | Cambiar entorno activo |
| `q` | Salir |

---

## Estructura del proyecto

```
replica/
├── app.py                  # Entrada principal (TUI Textual)
├── app.tcss                # Estilos globales
├── requirements.txt        # Dependencias Python
├── docker/
│   ├── docker-compose.yml  # PostgreSQL 17 local
│   └── init.sql            # Script de inicialización
└── src/
    ├── config/
    │   └── settings.py     # Carga de .env y configuración
    └── environment/
        ├── clone_environment.py      # Lógica de clonación
        ├── restore_from_backup.py    # Lógica de restauración
        ├── table_registry.py         # Catálogo de tablas para modo parcial
        └── _helpers.py               # Utilidades PostgreSQL compartidas
```
