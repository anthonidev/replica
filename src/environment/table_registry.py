"""
Catálogo de tablas para la clonación parcial por clínica.

Cada TableSpec define cómo se filtra una tabla cuando el modo de clonación
es "Parcial". Los grupos posibles son:

  SYSTEM       — Tablas globales del sistema; se copian siempre completas.
  ROOT         — Entidades raíz (organization, clinic, site, company);
                 se filtran a las organizaciones/clínicas seleccionadas.
  CLINIC_DIRECT— Tienen clinic_id propio; filtro: WHERE clinic_id IN (...).
  SITE_ONLY    — Tienen site_id pero no clinic_id; filtro via subquery a site.
  VIA_JOIN     — Sin clinic_id/site_id directo; filtro via JOIN a tabla padre.
  USERS        — Tablas de usuarios y acceso; lógica especial (ver build_copy_query).
  SKIP         — Se omiten en modo parcial (colas transitorias, backups, etc.).

Tablas NO listadas aquí → fallback CLINIC_DIRECT (se intenta filtrar por
clinic_id). Si la tabla no tiene esa columna el COPY falla y queda en
errores[], con un warning visible para que el desarrollador añada el spec.

Para añadir una tabla nueva basta agregar un TableSpec a TABLE_REGISTRY.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TableGroup(Enum):
    SYSTEM        = "system"
    ROOT          = "root"
    CLINIC_DIRECT = "clinic_direct"
    SITE_ONLY     = "site_only"
    VIA_JOIN      = "via_join"
    USERS         = "users"
    SKIP          = "skip"


@dataclass
class TableSpec:
    table: str
    group: TableGroup
    # Para VIA_JOIN: SQL completa con placeholders literales
    # {clinic_ids}, {site_ids}, {org_ids}, {company_ids}, {user_ids}
    # que se sustituyen en build_copy_query().
    filter_sql: Optional[str] = None
    note: Optional[str] = field(default=None, repr=False)


# ─── Registry completo ────────────────────────────────────────────────────────

TABLE_REGISTRY: list[TableSpec] = [

    # ── SYSTEM: sin relación con clinic/site/org ──────────────────────────────
    TableSpec("_prisma_migrations",   TableGroup.SYSTEM),
    TableSpec("alert_definition",     TableGroup.SYSTEM,
              note="Catálogo global de definiciones de alertas; no pertenece a clínica"),
    TableSpec("kpi_definition",       TableGroup.SYSTEM),
    TableSpec("permission",           TableGroup.SYSTEM),
    TableSpec("role_permission",      TableGroup.SYSTEM),

    # ── SKIP: colas transitorias, backups y schemas auxiliares de migración ─────
    TableSpec("domain_event_outbox",               TableGroup.SKIP,
              note="Cola de eventos; no tiene valor en LOCAL"),
    TableSpec("odontogram_record_backup_20260827", TableGroup.SKIP,
              note="Backup puntual; excluir para no añadir peso"),
    # Tablas de los schemas mig.* y mig_growclinic.* — datos de trabajo de
    # migración, no datos de clínica. Se copian completas (son pequeñas) o
    # se omiten; aquí las omitimos para no fallar con clinic_id inexistente.
    TableSpec("id_map",   TableGroup.SKIP, note="Schema auxiliar de migración"),
    TableSpec("file_log", TableGroup.SKIP, note="Schema auxiliar de migración"),
    TableSpec("run_log",  TableGroup.SKIP, note="Schema auxiliar de migración"),
    TableSpec("reversion",TableGroup.SKIP, note="Schema auxiliar de migración"),
    TableSpec("registro", TableGroup.SKIP, note="Schema auxiliar de migración"),

    # ── ROOT: entidades raíz, filtradas a la selección ───────────────────────
    TableSpec("organization",     TableGroup.ROOT),
    TableSpec("company",          TableGroup.ROOT),
    TableSpec("clinic",           TableGroup.ROOT),
    TableSpec("site",             TableGroup.ROOT),
    TableSpec("_ClinicCompanies", TableGroup.ROOT,
              note="Junction table clinic↔company"),

    # ── USERS: lógica especial (ver build_copy_query) ─────────────────────────
    TableSpec("app_user",                TableGroup.USERS),
    TableSpec("user_clinic",             TableGroup.USERS),
    TableSpec("user_site",               TableGroup.USERS),
    TableSpec("user_organization",       TableGroup.USERS),
    TableSpec("user_context_tracking",   TableGroup.USERS),
    TableSpec("user_permission_override",TableGroup.USERS),
    TableSpec("user_signature_profile",  TableGroup.USERS),
    TableSpec("user_context_suspension", TableGroup.USERS),

    # ── CLINIC_DIRECT: tienen clinic_id propio ────────────────────────────────
    # (se filtran automáticamente por clinic_id IN {clinic_ids})
    TableSpec("acquisition_channel",              TableGroup.CLINIC_DIRECT),
    TableSpec("attendance",                       TableGroup.CLINIC_DIRECT),
    TableSpec("attendance_incident",              TableGroup.CLINIC_DIRECT),
    TableSpec("availability_template",            TableGroup.CLINIC_DIRECT),
    TableSpec("billing_client",                   TableGroup.CLINIC_DIRECT),
    TableSpec("billing_document",                 TableGroup.CLINIC_DIRECT),
    TableSpec("billing_sequence",                 TableGroup.CLINIC_DIRECT),
    TableSpec("binaries",                         TableGroup.CLINIC_DIRECT),
    TableSpec("budget",                           TableGroup.CLINIC_DIRECT),
    TableSpec("budget_proposal",                  TableGroup.CLINIC_DIRECT),
    TableSpec("budget_simple_delivery_attempt",   TableGroup.CLINIC_DIRECT),
    TableSpec("budget_template",                  TableGroup.CLINIC_DIRECT),
    TableSpec("care_plan",                        TableGroup.CLINIC_DIRECT),
    TableSpec("cash_register",                    TableGroup.CLINIC_DIRECT),
    TableSpec("category",                         TableGroup.CLINIC_DIRECT),
    TableSpec("class",                            TableGroup.CLINIC_DIRECT),
    TableSpec("class_booking",                    TableGroup.CLINIC_DIRECT),
    TableSpec("class_group",                      TableGroup.CLINIC_DIRECT),
    TableSpec("class_group_session",              TableGroup.CLINIC_DIRECT),
    TableSpec("class_group_subscription",         TableGroup.CLINIC_DIRECT),
    TableSpec("class_makeup_credit",              TableGroup.CLINIC_DIRECT),
    TableSpec("clinical_note",                    TableGroup.CLINIC_DIRECT),
    TableSpec("clinical_note_comment",            TableGroup.CLINIC_DIRECT),
    TableSpec("clinical_note_narrative_template", TableGroup.CLINIC_DIRECT),
    TableSpec("clinical_note_template",           TableGroup.CLINIC_DIRECT),
    TableSpec("commission_entry",                 TableGroup.CLINIC_DIRECT),
    TableSpec("commission_rule",                  TableGroup.CLINIC_DIRECT),
    TableSpec("commission_settlement",            TableGroup.CLINIC_DIRECT),
    TableSpec("consent_delivery_attempt",         TableGroup.CLINIC_DIRECT),
    TableSpec("consent_delivery_dlq",             TableGroup.VIA_JOIN,
              filter_sql="consent_instance_id IN "
                         "(SELECT id FROM consent_instance WHERE clinic_id IN {clinic_ids})"),
    TableSpec("consent_instance",                 TableGroup.CLINIC_DIRECT),
    TableSpec("consent_template",                 TableGroup.CLINIC_DIRECT),
    TableSpec("discount",                         TableGroup.CLINIC_DIRECT),
    TableSpec("document_delivery_attempt",         TableGroup.CLINIC_DIRECT),
    TableSpec("document_folders",                 TableGroup.CLINIC_DIRECT),
    TableSpec("document_number_prefix_config",    TableGroup.CLINIC_DIRECT),
    TableSpec("document_references",              TableGroup.CLINIC_DIRECT),
    TableSpec("enrollment",                       TableGroup.CLINIC_DIRECT),
    TableSpec("equipment",                        TableGroup.CLINIC_DIRECT),
    TableSpec("expense",                          TableGroup.CLINIC_DIRECT),
    TableSpec("fixed_expense",                    TableGroup.CLINIC_DIRECT),
    TableSpec("form_assignment",                  TableGroup.CLINIC_DIRECT),
    TableSpec("form_response",                    TableGroup.CLINIC_DIRECT),
    TableSpec("form_template",                    TableGroup.CLINIC_DIRECT),
    TableSpec("form_template_version",            TableGroup.CLINIC_DIRECT),
    TableSpec("gift_card",                        TableGroup.CLINIC_DIRECT),
    TableSpec("image_reports",                    TableGroup.CLINIC_DIRECT),
    TableSpec("income",                           TableGroup.CLINIC_DIRECT),
    TableSpec("kommo_bot",                        TableGroup.CLINIC_DIRECT),
    TableSpec("manual_commission_adjustment",     TableGroup.CLINIC_DIRECT),
    TableSpec("measurement",                       TableGroup.CLINIC_DIRECT),
    TableSpec("medication_catalog",               TableGroup.CLINIC_DIRECT),
    TableSpec("membership",                       TableGroup.CLINIC_DIRECT),
    TableSpec("notification",                     TableGroup.CLINIC_DIRECT),
    TableSpec("odontogram_note",                  TableGroup.CLINIC_DIRECT),
    TableSpec("odontogram_record",                TableGroup.CLINIC_DIRECT),
    TableSpec("odontogram_settings",              TableGroup.CLINIC_DIRECT),
    TableSpec("orthodontic_case",                 TableGroup.CLINIC_DIRECT),
    TableSpec("orthodontic_record",               TableGroup.CLINIC_DIRECT),
    TableSpec("pack_definition",                  TableGroup.CLINIC_DIRECT),
    TableSpec("pack_instance",                    TableGroup.CLINIC_DIRECT),
    TableSpec("pack_instance_share",              TableGroup.CLINIC_DIRECT),
    TableSpec("pack_payment_allocation",          TableGroup.CLINIC_DIRECT),
    TableSpec("partner_agreement",                TableGroup.CLINIC_DIRECT),
    TableSpec("patient",                          TableGroup.CLINIC_DIRECT),
    TableSpec("patient_alert",                    TableGroup.CLINIC_DIRECT),
    TableSpec("patient_balance",                  TableGroup.CLINIC_DIRECT),
    TableSpec("patient_problem",                  TableGroup.CLINIC_DIRECT),
    TableSpec("patient_email",                    TableGroup.CLINIC_DIRECT),
    TableSpec("patient_phone",                    TableGroup.CLINIC_DIRECT),
    TableSpec("patient_related_person",           TableGroup.CLINIC_DIRECT),
    TableSpec("patient_problem_evolution",         TableGroup.CLINIC_DIRECT),
    TableSpec("patient_template",                 TableGroup.CLINIC_DIRECT),
    TableSpec("pediatric_exploration_text",       TableGroup.CLINIC_DIRECT),
    TableSpec("pediatric_history_section",        TableGroup.CLINIC_DIRECT),
    TableSpec("pediatric_visit",                  TableGroup.CLINIC_DIRECT),
    TableSpec("pediatric_visit_type",             TableGroup.CLINIC_DIRECT),
    TableSpec("payment",                          TableGroup.CLINIC_DIRECT),
    TableSpec("payment_allocation",               TableGroup.CLINIC_DIRECT),
    TableSpec("payment_method",                   TableGroup.CLINIC_DIRECT),
    TableSpec("photo_registries",                 TableGroup.CLINIC_DIRECT),
    TableSpec("planned_appointment",              TableGroup.CLINIC_DIRECT),
    TableSpec("planned_session",                  TableGroup.CLINIC_DIRECT),
    TableSpec("prescription",                     TableGroup.CLINIC_DIRECT),
    TableSpec("prescription_settings",            TableGroup.CLINIC_DIRECT),
    TableSpec("prescription_token",               TableGroup.CLINIC_DIRECT),
    TableSpec("prescription_token_batch",         TableGroup.CLINIC_DIRECT),
    TableSpec("professional",                     TableGroup.CLINIC_DIRECT),
    TableSpec("professional_lab_expense_declaration", TableGroup.CLINIC_DIRECT),
    TableSpec("professional_type",                TableGroup.CLINIC_DIRECT),
    TableSpec("prosthetic_shipment",              TableGroup.CLINIC_DIRECT),
    TableSpec("provider",                         TableGroup.CLINIC_DIRECT),
    TableSpec("record",                           TableGroup.CLINIC_DIRECT),
    TableSpec("receipt",                          TableGroup.CLINIC_DIRECT),
    TableSpec("room",                             TableGroup.CLINIC_DIRECT),
    TableSpec("schedule_block",                   TableGroup.CLINIC_DIRECT),
    TableSpec("service",                          TableGroup.CLINIC_DIRECT),
    TableSpec("schedule_block_series",            TableGroup.CLINIC_DIRECT),
    TableSpec("schedule_block_session_snapshot",  TableGroup.CLINIC_DIRECT),
    TableSpec("scheduling_policy",                TableGroup.CLINIC_DIRECT),
    TableSpec("supply_consumption",               TableGroup.CLINIC_DIRECT),
    TableSpec("support_conversation",             TableGroup.CLINIC_DIRECT),
    TableSpec("support_session_replay",           TableGroup.CLINIC_DIRECT),
    TableSpec("task",                             TableGroup.CLINIC_DIRECT),
    TableSpec("task_comment",                     TableGroup.CLINIC_DIRECT),
    TableSpec("task_recurrence",                  TableGroup.CLINIC_DIRECT),
    TableSpec("template",                         TableGroup.CLINIC_DIRECT),
    TableSpec("trigger_rule",                     TableGroup.CLINIC_DIRECT),
    TableSpec("trigger_scheduled_execution",      TableGroup.CLINIC_DIRECT),
    TableSpec("visit_status_definition",          TableGroup.CLINIC_DIRECT),
    TableSpec("voucher",                          TableGroup.CLINIC_DIRECT),
    TableSpec("workflow",                         TableGroup.CLINIC_DIRECT),

    # ── SITE_ONLY: tienen site_id pero no clinic_id ───────────────────────────
    TableSpec("user_site_preference",  TableGroup.SITE_ONLY),
    TableSpec("ai_integration",        TableGroup.SITE_ONLY),
    TableSpec("budget_status",         TableGroup.SITE_ONLY),
    TableSpec("expense_file",          TableGroup.SITE_ONLY),
    TableSpec("mrn_counter",           TableGroup.SITE_ONLY),
    TableSpec("orthodontic_status",    TableGroup.SITE_ONLY),
    TableSpec("product",               TableGroup.SITE_ONLY),
    TableSpec("site_billing_line",     TableGroup.SITE_ONLY),
    TableSpec("site_document_template",TableGroup.SITE_ONLY),
    TableSpec("site_mrn_configuration",TableGroup.SITE_ONLY),
    TableSpec("supply",                TableGroup.SITE_ONLY),
    TableSpec("tag",                   TableGroup.SITE_ONLY),
    TableSpec("task_status_group",     TableGroup.SITE_ONLY),
    TableSpec("treatment",             TableGroup.SITE_ONLY),
    TableSpec("workflow_configuration",TableGroup.SITE_ONLY),

    # cash_* tienen site_id solamente
    TableSpec("cash_movement",         TableGroup.SITE_ONLY),
    TableSpec("cash_movement_file",    TableGroup.SITE_ONLY),
    TableSpec("cash_session",          TableGroup.SITE_ONLY),
    TableSpec("cash_session_access",   TableGroup.SITE_ONLY),
    TableSpec("cash_session_count",    TableGroup.SITE_ONLY),
    TableSpec("cash_session_incident", TableGroup.SITE_ONLY),

    # ── VIA_JOIN: sin clinic_id/site_id directo, filtro vía padre ────────────
    TableSpec("attendance_pause",
              TableGroup.VIA_JOIN,
              filter_sql="attendance_id IN "
                         "(SELECT id FROM attendance WHERE clinic_id IN {clinic_ids})"),

    TableSpec("availability_exception",
              TableGroup.VIA_JOIN,
              filter_sql="template_id IN "
                         "(SELECT id FROM availability_template WHERE clinic_id IN {clinic_ids})"),

    TableSpec("billing_client_treatment",
              TableGroup.VIA_JOIN,
              filter_sql="billing_client_id IN "
                         "(SELECT id FROM billing_client WHERE clinic_id IN {clinic_ids})"),

    TableSpec("billing_document_file",
              TableGroup.VIA_JOIN,
              filter_sql="billing_document_id IN "
                         "(SELECT id FROM billing_document WHERE clinic_id IN {clinic_ids})"),

    TableSpec("billing_item",
              TableGroup.VIA_JOIN,
              filter_sql="billing_document_id IN "
                         "(SELECT id FROM billing_document WHERE clinic_id IN {clinic_ids})"),

    TableSpec("budget_consent_template",
              TableGroup.VIA_JOIN,
              filter_sql="budget_id IN "
                         "(SELECT id FROM budget WHERE clinic_id IN {clinic_ids})"),

    TableSpec("consent_evidence",
              TableGroup.VIA_JOIN,
              filter_sql="consent_instance_id IN "
                         "(SELECT id FROM consent_instance WHERE clinic_id IN {clinic_ids})"),

    TableSpec("consent_evidence_access_log",
              TableGroup.VIA_JOIN,
              filter_sql="consent_instance_id IN "
                         "(SELECT id FROM consent_instance WHERE clinic_id IN {clinic_ids})"),

    TableSpec("consent_image_access_logs", TableGroup.CLINIC_DIRECT),

    TableSpec("consent_images",
              TableGroup.VIA_JOIN,
              filter_sql="consent_instance_id IN "
                         "(SELECT id FROM consent_instance WHERE clinic_id IN {clinic_ids})"),

    TableSpec("consent_instance_signature",
              TableGroup.VIA_JOIN,
              filter_sql="consent_instance_id IN "
                         "(SELECT id FROM consent_instance WHERE clinic_id IN {clinic_ids})"),

    TableSpec("consent_instance_signer",
              TableGroup.VIA_JOIN,
              filter_sql="consent_instance_id IN "
                         "(SELECT id FROM consent_instance WHERE clinic_id IN {clinic_ids})"),

    TableSpec("discount_application",
              TableGroup.VIA_JOIN,
              filter_sql="discount_id IN "
                         "(SELECT id FROM discount WHERE clinic_id IN {clinic_ids})"),

    TableSpec("discount_user_access",
              TableGroup.VIA_JOIN,
              filter_sql="discount_id IN "
                         "(SELECT id FROM discount WHERE clinic_id IN {clinic_ids})"),

    TableSpec("expense_item",
              TableGroup.VIA_JOIN,
              filter_sql="expense_id IN "
                         "(SELECT id FROM expense WHERE clinic_id IN {clinic_ids})"),

    TableSpec("expense_payment",
              TableGroup.VIA_JOIN,
              filter_sql="expense_id IN "
                         "(SELECT id FROM expense WHERE clinic_id IN {clinic_ids})"),

    TableSpec("fixed_expense_cell",
              TableGroup.VIA_JOIN,
              filter_sql="fixed_expense_id IN "
                         "(SELECT id FROM fixed_expense WHERE clinic_id IN {clinic_ids})"),

    TableSpec("gift_card_movement",
              TableGroup.VIA_JOIN,
              filter_sql="gift_card_id IN "
                         "(SELECT id FROM gift_card WHERE clinic_id IN {clinic_ids})"),

    TableSpec("income_cell",
              TableGroup.VIA_JOIN,
              filter_sql="income_id IN "
                         "(SELECT id FROM income WHERE clinic_id IN {clinic_ids})"),

    TableSpec("membership_class",
              TableGroup.VIA_JOIN,
              filter_sql="membership_id IN "
                         "(SELECT id FROM membership WHERE clinic_id IN {clinic_ids})"),

    TableSpec("pack_consumption",
              TableGroup.VIA_JOIN,
              filter_sql="pack_instance_id IN "
                         "(SELECT id FROM pack_instance WHERE clinic_id IN {clinic_ids})"),

    TableSpec("pack_item_definition",
              TableGroup.VIA_JOIN,
              filter_sql="pack_definition_id IN "
                         "(SELECT id FROM pack_definition WHERE clinic_id IN {clinic_ids})"),

    TableSpec("patient_balance_movement",
              TableGroup.VIA_JOIN,
              filter_sql="patient_balance_id IN "
                         "(SELECT id FROM patient_balance WHERE clinic_id IN {clinic_ids})"),

    TableSpec("patient_billing_client",
              TableGroup.VIA_JOIN,
              filter_sql="patient_id IN "
                         "(SELECT id FROM patient WHERE clinic_id IN {clinic_ids})"),

    TableSpec("patient_related_person_designation",
              TableGroup.VIA_JOIN,
              filter_sql="patient_related_person_id IN "
                         "(SELECT id FROM patient_related_person WHERE clinic_id IN {clinic_ids})"),

    TableSpec("payment_detail",
              TableGroup.VIA_JOIN,
              filter_sql="payment_id IN "
                         "(SELECT id FROM payment WHERE clinic_id IN {clinic_ids})"),

    TableSpec("planned_session_visit_state",
              TableGroup.VIA_JOIN,
              filter_sql="planned_session_id IN "
                         "(SELECT id FROM planned_session WHERE clinic_id IN {clinic_ids})"),

    TableSpec("prescription_item",
              TableGroup.VIA_JOIN,
              filter_sql="prescription_id IN "
                         "(SELECT id FROM prescription WHERE clinic_id IN {clinic_ids})"),

    TableSpec("professional_room",
              TableGroup.VIA_JOIN,
              filter_sql="room_id IN "
                         "(SELECT id FROM room WHERE clinic_id IN {clinic_ids})"),

    TableSpec("professional_treatment",
              TableGroup.VIA_JOIN,
              filter_sql="professional_id IN "
                         "(SELECT id FROM professional WHERE clinic_id IN {clinic_ids})"),

    TableSpec("receipt_item",
              TableGroup.VIA_JOIN,
              filter_sql="receipt_id IN "
                         "(SELECT id FROM receipt WHERE clinic_id IN {clinic_ids})"),

    TableSpec("room_treatment",
              TableGroup.VIA_JOIN,
              filter_sql="room_id IN "
                         "(SELECT id FROM room WHERE clinic_id IN {clinic_ids})"),

    TableSpec("schedule_block_item",
              TableGroup.VIA_JOIN,
              filter_sql="schedule_block_id IN "
                         "(SELECT id FROM schedule_block WHERE clinic_id IN {clinic_ids})"),

    TableSpec("schedule_history_entry",
              TableGroup.VIA_JOIN,
              filter_sql="schedule_block_id IN "
                         "(SELECT id FROM schedule_block WHERE clinic_id IN {clinic_ids})"),

    TableSpec("supply_batch",
              TableGroup.VIA_JOIN,
              filter_sql="supply_id IN "
                         "(SELECT id FROM supply WHERE site_id IN "
                         "(SELECT id FROM site WHERE clinic_id IN {clinic_ids}))"),

    TableSpec("template_images",
              TableGroup.VIA_JOIN,
              filter_sql="template_id IN "
                         "(SELECT id FROM template WHERE clinic_id IN {clinic_ids})"),

    TableSpec("workflow_version",
              TableGroup.VIA_JOIN,
              filter_sql="workflow_id IN "
                         "(SELECT id FROM workflow WHERE clinic_id IN {clinic_ids})"),

    TableSpec("support_message",
              TableGroup.VIA_JOIN,
              filter_sql="conversation_id IN "
                         "(SELECT id FROM support_conversation WHERE clinic_id IN {clinic_ids})"),
]

# Índice rápido por nombre de tabla
_REGISTRY_INDEX: dict[str, TableSpec] = {s.table: s for s in TABLE_REGISTRY}


def get_spec(table_name: str) -> Optional[TableSpec]:
    """Devuelve el TableSpec para una tabla, o None si no está en el registry."""
    return _REGISTRY_INDEX.get(table_name)


def build_copy_query(
    spec: TableSpec,
    schema: str,
    clinic_ids: tuple[str, ...],
    site_ids: tuple[str, ...],
    org_ids: tuple[str, ...],
    company_ids: tuple[str, ...],
    user_ids: tuple[str, ...],
) -> Optional[str]:
    """Genera la SQL que va dentro de COPY (...) TO STDOUT.

    Retorna None para SYSTEM/ROOT/SKIP (el caller decide qué hacer).
    Retorna la SELECT completa (sin COPY) para los demás grupos.
    """
    qualified = f'"{schema}"."{spec.table}"'

    def _ids(tpl: tuple[str, ...]) -> str:
        return "(" + ", ".join(f"'{v}'" for v in tpl) + ")"

    if spec.group in (TableGroup.SYSTEM, TableGroup.ROOT, TableGroup.SKIP):
        return None  # el caller maneja estos grupos directamente

    if spec.group == TableGroup.CLINIC_DIRECT:
        return f"SELECT * FROM {qualified} WHERE clinic_id IN {_ids(clinic_ids)}"

    if spec.group == TableGroup.SITE_ONLY:
        return (
            f"SELECT * FROM {qualified} WHERE site_id IN "
            f"(SELECT id FROM site WHERE clinic_id IN {_ids(clinic_ids)})"
        )

    if spec.group == TableGroup.VIA_JOIN:
        where = spec.filter_sql.format(
            clinic_ids=_ids(clinic_ids),
            site_ids=_ids(site_ids),
            org_ids=_ids(org_ids),
            company_ids=_ids(company_ids),
            user_ids=_ids(user_ids),
        )
        return f"SELECT * FROM {qualified} WHERE {where}"

    if spec.group == TableGroup.USERS:
        if spec.table == "app_user":
            return (
                f"SELECT * FROM {qualified} WHERE id IN ("
                f"SELECT user_id FROM user_clinic WHERE clinic_id IN {_ids(clinic_ids)} "
                f"UNION "
                f"SELECT user_id FROM user_organization WHERE organization_id IN {_ids(org_ids)}"
                f") OR user_type = 'platform_staff'"
            )
        if spec.table == "user_clinic":
            return f"SELECT * FROM {qualified} WHERE clinic_id IN {_ids(clinic_ids)}"
        if spec.table == "user_site":
            return f"SELECT * FROM {qualified} WHERE site_id IN {_ids(site_ids)}"
        if spec.table == "user_organization":
            return f"SELECT * FROM {qualified} WHERE organization_id IN {_ids(org_ids)}"
        if spec.table == "user_context_tracking":
            return (
                f"SELECT * FROM {qualified} WHERE "
                f"primary_clinic_id IN {_ids(clinic_ids)} "
                f"OR last_active_clinic_id IN {_ids(clinic_ids)} "
                f"OR user_id IN ("
                f"SELECT id FROM app_user WHERE user_type = 'platform_staff'"
                f")"
            )
        if spec.table in ("user_permission_override", "user_signature_profile"):
            return f"SELECT * FROM {qualified} WHERE clinic_id IN {_ids(clinic_ids)}"
        if spec.table == "user_context_suspension":
            return f"SELECT * FROM {qualified} WHERE user_id IN {_ids(user_ids)}"
        if spec.table == "user_site_preference":
            return (
                f"SELECT * FROM {qualified} WHERE user_site_id IN "
                f"(SELECT id FROM user_site WHERE site_id IN {_ids(site_ids)})"
            )

    return None  # desconocido → el caller aplicará fallback
