"""
Dashboard principal: dos tarjetas (Clonar / Restaurar) + log abajo.
"""
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Input, Label, SelectionList, Static
from textual.widgets.selection_list import Selection


# ── SelectionList con colores propios ─────────────────────────

class ClinicList(SelectionList):
    DEFAULT_CSS = SelectionList.DEFAULT_CSS + """
    ClinicList {
        background: #0D0F18;
        background-tint: #0D0F18 0%;
        & > .option-list--option-highlighted {
            background: #1A1D2E;
            color: #CDD6F4;
        }
        &:focus {
            background-tint: #0D0F18 0%;
            & > .option-list--option-highlighted {
                background: #1A1D2E;
                color: #CDD6F4;
            }
        }
        & > .selection-list--button {
            background: #0D0F18;
            color: #8F93A2;
        }
        & > .selection-list--button-highlighted {
            background: #1A1D2E;
            color: #CDD6F4;
        }
        & > .selection-list--button-selected {
            background: #0D0F18;
            color: #C3E88D;
        }
        & > .selection-list--button-selected-highlighted {
            background: #1A2A20;
            color: #C3E88D;
        }
    }
    """


# ── Mensaje central de acción ─────────────────────────────────

class ActionRequested(Message):
    def __init__(self, action_id: str, params: dict | None = None) -> None:
        super().__init__()
        self.action_id = action_id
        self.params = params or {}


# ── Chip tipo toggle (Widget nativo, sin Button) ──────────────

class Chip(Widget, can_focus=True):
    """Botón tipo chip seleccionable. Sin animación de Button."""

    DEFAULT_CSS = """
    Chip {
        width: auto;
        height: 3;
        min-width: 10;
        padding: 0 2;
        content-align: center middle;
        background: #0D0F18;
        border: tall #2A2D3E;
        color: #45475A;
        margin: 0 1 0 0;
    }
    Chip:hover {
        background: #1A1D2E;
        border: tall #45475A;
        color: #8F93A2;
    }
    Chip:focus {
        background: #1A1D2E;
        border: tall #45475A;
    }
    Chip.--on {
        background: #1E2A35;
        border: tall #89DDFF;
        color: #CDD6F4;
        text-style: bold;
    }
    Chip.--on:hover {
        background: #243240;
        border: tall #89DDFF;
    }
    Chip.--on:focus {
        background: #243240;
        border: tall #89DDFF;
    }
    Chip.--warn {
        background: #2A1E12;
        border: tall #FFCB6B;
        color: #FFCB6B;
        text-style: bold;
    }
    Chip.--warn:hover {
        background: #352515;
        border: tall #FFCB6B;
    }
    """

    class Toggled(Message):
        def __init__(self, chip: "Chip") -> None:
            super().__init__()
            self.chip = chip

    def __init__(self, label: str, value: str, group: str, active: bool = False, warn: bool = False) -> None:
        super().__init__()
        self._label = label
        self.value = value
        self.group = group
        self._warn = warn
        if active:
            if warn:
                self.add_class("--warn")
            else:
                self.add_class("--on")

    def render(self) -> str:
        return self._label

    async def _on_click(self, event: events.Click) -> None:
        event.stop()
        self.post_message(self.Toggled(self))

    async def _on_key(self, event: events.Key) -> None:
        if event.key in ("enter", "space"):
            event.stop()
            self.post_message(self.Toggled(self))

    def activate(self) -> None:
        self.remove_class("--on", "--warn")
        if self._warn:
            self.add_class("--warn")
        else:
            self.add_class("--on")

    def deactivate(self) -> None:
        self.remove_class("--on", "--warn")


# ── Fila de chips (grupo exclusivo) ──────────────────────────

class ChipRow(Widget):
    """Fila de Chips con selección exclusiva."""

    DEFAULT_CSS = """
    ChipRow {
        height: 3;
        layout: horizontal;
        background: transparent;
        margin-bottom: 1;
    }
    """

    class Changed(Message):
        def __init__(self, group: str, value: str) -> None:
            super().__init__()
            self.group = group
            self.value = value

    def __init__(self, options: list[tuple[str, str]], group: str, default: str, warn_value: str | None = None) -> None:
        super().__init__()
        self._options = options     # [(label, value), ...]
        self._group = group
        self._default = default
        self._warn_value = warn_value
        self._active = default

    def compose(self) -> ComposeResult:
        for label, value in self._options:
            warn = (value == self._warn_value)
            yield Chip(label, value, self._group, active=(value == self._default), warn=warn)

    def on_chip_toggled(self, event: Chip.Toggled) -> None:
        event.stop()
        chip = event.chip
        if chip.group != self._group:
            return
        if chip.value == self._active:
            return
        self._active = chip.value
        for c in self.query(Chip):
            if c.value == self._active:
                c.activate()
            else:
                c.deactivate()
        self.post_message(self.Changed(self._group, self._active))

    @property
    def active_value(self) -> str:
        return self._active


# ── Tarjeta base ──────────────────────────────────────────────

class Card(Widget):
    DEFAULT_CSS = """
    Card {
        width: 1fr;
        height: 1fr;
        background: #13151F;
        border: round #2A2D3E;
        padding: 1 2;
        layout: vertical;
    }
    Card .section-label {
        color: #45475A;
        height: 1;
        margin-top: 1;
        margin-bottom: 0;
        text-style: bold;
    }
    """


# ── Tarjeta: Clonar ───────────────────────────────────────────

ENVS = [
    ("STG", "STAGING"),
    ("INT", "INTEGRATION"),
    ("PRD", "PRODUCTION"),
]

MODES = [
    ("Completo", "full"),
    ("Parcial",  "partial"),
]

ENV_COLORS = {
    "STAGING":     "#FFCB6B",
    "INTEGRATION": "#82AAFF",
    "PRODUCTION":  "#FF5370",
}


class CloneCard(Card):
    DEFAULT_CSS = """
    CloneCard {
        margin: 0 1 0 0;
        layout: vertical;
    }
    CloneCard #clone-title {
        height: 1;
        color: #89DDFF;
        text-style: bold;
        margin-bottom: 1;
    }
    CloneCard #clinics-section {
        height: 1fr;
        display: none;
        margin-top: 1;
    }
    CloneCard #clinic-search {
        height: 3;
        margin-bottom: 1;
        border: tall #2A2D3E;
        background: #0D0F18;
        color: #CDD6F4;
        padding: 0 1;
    }
    CloneCard #clinic-search:focus {
        border: tall #89DDFF 70%;
    }
    CloneCard #clinic-list {
        height: 1fr;
        border: round #2A2D3E;
        background: #0D0F18;
        scrollbar-size: 1 1;
        color: #CDD6F4;
    }
    CloneCard #clinic-list:focus {
        border: round #89DDFF 50%;
    }
    CloneCard #clinic-count {
        height: 1;
        color: #45475A;
        content-align: right middle;
    }
    CloneCard #btn-clone {
        dock: bottom;
        width: 100%;
        margin-top: 1;
        background: #89DDFF 20%;
        color: #89DDFF;
        border: tall #89DDFF 50%;
        text-style: bold;
    }
    CloneCard #btn-clone:hover {
        background: #89DDFF 30%;
        border: tall #89DDFF 80%;
    }
    CloneCard #btn-clone:focus {
        background: #89DDFF 25%;
        border: tall #89DDFF;
    }
    CloneCard #no-clinics-warning {
        height: 1;
        color: #FF5370;
        display: none;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._all_clinics: list[dict] = []
        self._selected_ids: set[str] = set()
        self._clinics_loaded = False
        self._selected_env = "STAGING"
        self._selected_mode = "full"

    def compose(self) -> ComposeResult:
        yield Static("⬇  Clonar Ambiente", id="clone-title")

        yield Label("Origen", classes="section-label")
        yield ChipRow(ENVS, group="env", default="STAGING", warn_value="PRODUCTION")

        yield Label("Modo", classes="section-label")
        yield ChipRow(MODES, group="mode", default="full")

        with Vertical(id="clinics-section"):
            yield Label("Clínicas  [dim](Space para marcar)[/dim]", classes="section-label")
            yield Input(placeholder="Buscar...", id="clinic-search")
            yield ClinicList(id="clinic-list")
            yield Static("", id="clinic-count")

        yield Static("⚠  Selecciona al menos una clínica.", id="no-clinics-warning")
        yield Button("▶  Ejecutar", id="btn-clone", variant="default")

    def on_mount(self) -> None:
        self._refresh_clinics_visibility()

    # ── ChipRow handlers ───────────────────────────────────────

    def on_chip_row_changed(self, event: ChipRow.Changed) -> None:
        event.stop()
        if event.group == "env":
            self._selected_env = event.value
            if self._selected_mode == "partial":
                self._clinics_loaded = False
                self._reload_clinics()
        elif event.group == "mode":
            self._selected_mode = event.value
            self._refresh_clinics_visibility()

    def _refresh_clinics_visibility(self) -> None:
        is_partial = self._selected_mode == "partial"
        self.query_one("#clinics-section").display = is_partial
        self.query_one("#no-clinics-warning").display = False
        if is_partial and not self._clinics_loaded:
            self._reload_clinics()

    # ── Clínicas ──────────────────────────────────────────────

    def _reload_clinics(self) -> None:
        sl = self.query_one("#clinic-list", ClinicList)
        sl.clear_options()
        sl.add_option(Selection("Conectando al origen...", "__loading__", disabled=True))
        self._update_count(0, 0)
        self.app.run_worker(self._fetch_clinics, thread=True)

    def _fetch_clinics(self) -> None:
        try:
            from environment.clone_environment import get_clinics_from_origin
            from config.settings import get_config
            dbs = get_config().get("DATABASES", {})
            src_url = dbs.get(f"DATABASE_URL_{self._selected_env}")
            if not src_url:
                self.app.call_from_thread(
                    self._set_clinics_error, f"Sin URL configurada para {self._selected_env}"
                )
                return
            clinics = get_clinics_from_origin(src_url)
            self.app.call_from_thread(self._set_clinics, clinics)
        except Exception as e:
            self.app.call_from_thread(self._set_clinics_error, str(e))

    def _set_clinics(self, clinics: list[dict]) -> None:
        self._all_clinics = clinics
        self._selected_ids.clear()
        self._clinics_loaded = True
        self._render_list(clinics)

    def _set_clinics_error(self, msg: str) -> None:
        sl = self.query_one("#clinic-list", ClinicList)
        sl.clear_options()
        sl.add_option(Selection(f"Error: {msg}", "__err__", disabled=True))

    def _render_list(self, clinics: list[dict]) -> None:
        sl = self.query_one("#clinic-list", ClinicList)
        sl.clear_options()
        if not clinics:
            sl.add_option(Selection("Sin clínicas disponibles.", "__empty__", disabled=True))
            self._update_count(0, 0)
            return
        for c in clinics:
            cid = str(c["id"])
            label = f"{c['name']}  [dim]{c.get('org', '')}[/dim]"
            sl.add_option(Selection(label, cid, initial_state=(cid in self._selected_ids)))
        self._update_count(len(self._selected_ids), len(self._all_clinics))

    def _update_count(self, selected: int, total: int) -> None:
        try:
            text = f"{selected}/{total} seleccionadas" if total else ""
            self.query_one("#clinic-count", Static).update(f"[dim]{text}[/dim]")
        except Exception:
            pass

    # ── Búsqueda ──────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "clinic-search":
            return
        self._sync_selection_from_list()
        query = event.value.strip().lower()
        filtered = [
            c for c in self._all_clinics
            if not query
            or query in c["name"].lower()
            or query in c.get("org", "").lower()
        ]
        self._render_list(filtered)

    def _sync_selection_from_list(self) -> None:
        sl = self.query_one("#clinic-list", ClinicList)
        visible = {sl.get_option_at_index(i).value for i in range(sl.option_count)}
        self._selected_ids -= visible
        self._selected_ids.update(sl.selected)

    def on_selection_list_selected_changed(self, event: SelectionList.SelectedChanged) -> None:
        self._sync_selection_from_list()
        self._update_count(len(self._selected_ids), len(self._all_clinics))

    # ── Ejecutar ──────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "btn-clone":
            return
        if self._selected_mode == "partial" and not self._selected_ids:
            self.query_one("#no-clinics-warning").display = True
            return
        self.query_one("#no-clinics-warning").display = False
        self.post_message(ActionRequested("clone-env", {
            "env":        self._selected_env,
            "mode":       self._selected_mode,
            "clinic_ids": list(self._selected_ids),
        }))


# ── Tarjeta: Restaurar ────────────────────────────────────────

class RestoreCard(Card):
    DEFAULT_CSS = """
    RestoreCard {
        margin: 0 0 0 1;
    }
    RestoreCard #restore-title {
        height: 1;
        color: #C792EA;
        text-style: bold;
        margin-bottom: 2;
    }
    RestoreCard #restore-desc {
        color: #8F93A2;
        height: 5;
        margin-bottom: 1;
    }
    RestoreCard #restore-warning {
        color: #FFCB6B;
        height: 1;
    }
    RestoreCard #btn-restore {
        dock: bottom;
        width: 100%;
        margin-top: 1;
        background: #C792EA 15%;
        color: #C792EA;
        border: tall #C792EA 40%;
    }
    RestoreCard #btn-restore:hover {
        background: #C792EA 25%;
        border: tall #C792EA 70%;
    }
    RestoreCard #btn-restore:focus {
        background: #C792EA 20%;
        border: tall #C792EA;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("↺  Restaurar desde Backup", id="restore-title")
        yield Static(
            "Restaura LOCAL desde el BACKUP local.\n\n"
            "Mismo cluster → CREATE DATABASE TEMPLATE\n"
            "(casi instantáneo, copia a nivel filesystem).\n\n"
            "Distinto cluster → pg_dump / pg_restore.",
            id="restore-desc",
        )
        yield Static("⚠  Sobreescribe completamente la BD LOCAL.", id="restore-warning")
        yield Button("↺  Restaurar", id="btn-restore")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-restore":
            self.post_message(ActionRequested("restore-backup"))


# ── ContentArea ───────────────────────────────────────────────

class ContentArea(Widget):
    class ActionRequested(Message):
        def __init__(self, action_id: str, params: dict | None = None) -> None:
            super().__init__()
            self.action_id = action_id
            self.params = params or {}

    DEFAULT_CSS = """
    ContentArea {
        width: 1fr;
        height: 1fr;
        padding: 1 2;
    }
    ContentArea #cards-row {
        width: 1fr;
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="cards-row"):
            yield CloneCard()
            yield RestoreCard()

    def on_action_requested(self, event: ActionRequested) -> None:
        event.stop()
        self.post_message(ContentArea.ActionRequested(event.action_id, event.params))
