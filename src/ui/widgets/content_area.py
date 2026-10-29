from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static


class ActionButton(Static):
    """Boton de accion clickeable."""

    DEFAULT_CSS = """
    ActionButton {
        width: 100%; height: 5; margin: 0 0 1 0;
        padding: 1 2; background: #1A1C25;
        border: round #3B3F51; color: #8F93A2;
        content-align: left middle;
    }
    ActionButton:hover { background: #89DDFF 12%; border: round #89DDFF 40%; color: #89DDFF; }
    ActionButton.--primary { border: round #C3E88D 30%; }
    ActionButton.--primary:hover { background: #C3E88D 12%; border: round #C3E88D 60%; color: #C3E88D; }
    """

    class Pressed(Message):
        def __init__(self, action_id: str) -> None:
            super().__init__()
            self.action_id = action_id

    def __init__(self, label: str, action_id: str, description: str = "", primary: bool = False):
        icon_line = f"  {label}"
        desc_line = f"\n  [dim]{description}[/dim]" if description else ""
        super().__init__(f"{icon_line}{desc_line}")
        self._action_id = action_id
        if primary:
            self.add_class("--primary")

    def on_click(self) -> None:
        self.post_message(self.Pressed(self._action_id))


class CloneView(VerticalScroll):
    """Vista de clonacion de ambiente."""

    DEFAULT_CSS = """
    CloneView { padding: 1 2; }
    CloneView #clone-title { color: #89DDFF; text-style: bold; margin-bottom: 1; }
    CloneView #clone-subtitle { color: #4B526D; margin-bottom: 2; }
    """

    def compose(self) -> ComposeResult:
        yield Static("⬇  Clonar Ambiente", id="clone-title")
        yield Static(
            "Clona un ambiente remoto (STG/INT/PRD) a la BD local.\n"
            "Modo completo copia todo. Modo parcial filtra por clínicas seleccionadas.",
            id="clone-subtitle",
        )
        yield ActionButton(
            "▶  Clonar Ambiente",
            "clone-env",
            "Selecciona origen, modo y clínicas → clona LOCAL + BACKUP",
            primary=True,
        )


class RestoreView(VerticalScroll):
    """Vista de restauracion desde backup."""

    DEFAULT_CSS = """
    RestoreView { padding: 1 2; }
    RestoreView #restore-title { color: #C792EA; text-style: bold; margin-bottom: 1; }
    RestoreView #restore-subtitle { color: #4B526D; margin-bottom: 2; }
    """

    def compose(self) -> ComposeResult:
        yield Static("↺  Restaurar desde Backup", id="restore-title")
        yield Static(
            "Restaura la base de datos LOCAL desde el BACKUP local.\n"
            "Mismo cluster → TEMPLATE (instantáneo). Clusters distintos → pg_dump/pg_restore.",
            id="restore-subtitle",
        )
        yield ActionButton(
            "↺  Restaurar Backup → Local",
            "restore-backup",
            "Sobreescribe LOCAL con el contenido del BACKUP",
            primary=True,
        )


class ContentArea(Widget):
    """Area de contenido que alterna entre las vistas disponibles."""

    class ActionRequested(Message):
        def __init__(self, action_id: str) -> None:
            super().__init__()
            self.action_id = action_id

    DEFAULT_CSS = """
    ContentArea { width: 1fr; height: 1fr; }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._current_view = "clone"

    def compose(self) -> ComposeResult:
        yield CloneView(id="view-clone")
        yield RestoreView(id="view-restore")

    def on_mount(self) -> None:
        self._show_view("clone")

    def show_view(self, view_id: str) -> None:
        self._current_view = view_id
        self._show_view(view_id)

    def _show_view(self, view_id: str) -> None:
        for view in self.query("CloneView, RestoreView"):
            view.display = False
        target_map = {
            "clone":   "CloneView",
            "restore": "RestoreView",
        }
        selector = target_map.get(view_id)
        if selector:
            try:
                self.query_one(selector).display = True
            except Exception:
                pass

    def on_action_button_pressed(self, event: ActionButton.Pressed) -> None:
        self.post_message(self.ActionRequested(event.action_id))
