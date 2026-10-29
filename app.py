"""
Clinicsay Replica — Clonar/Restaurar ambientes
Ejecutar: python app.py
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")

sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SRC_DIR)

from config.settings import load_config
load_config()

from textual.app import App, ComposeResult
from textual.theme import Theme as TextualTheme
from textual.widgets import Footer

from config.settings import get_environment
from ui.widgets.sidebar import Sidebar
from ui.widgets.log_panel import LogPanel
from ui.widgets.content_area import ContentArea
from ui.widgets.title_bar import TitleBar, ENV_COLORS
from ui.widgets.resizable import ResizableHorizontal


THEME_DARK = TextualTheme(
    name="replica-dark",
    primary="#89DDFF",
    secondary="#C792EA",
    accent="#82AAFF",
    warning="#FFCB6B",
    error="#FF5370",
    success="#C3E88D",
    background="#0F111A",
    surface="#090B10",
    panel="#1A1C25",
    dark=True,
    variables={
        "accent-muted": "#00e8c6",
    },
)


class ReplicaApp(App):
    """App standalone para clonar ambientes y restaurar desde backup."""

    TITLE = "Clinicsay Replica"
    CSS_PATH = "app.tcss"
    BINDINGS = [
        ("q", "quit", "Salir"),
        ("e", "change_env", "Entorno"),
    ]

    RESTART_SENTINEL = object()

    def __init__(self):
        super().__init__()
        self.register_theme(THEME_DARK)
        self.theme = "replica-dark"

    def compose(self) -> ComposeResult:
        yield TitleBar()
        yield Sidebar()
        with ResizableHorizontal(id="main-panels"):
            yield ContentArea()
            yield LogPanel()
        yield Footer()

    def on_mount(self) -> None:
        log_panel = self.query_one(LogPanel)
        log_widget = log_panel.rich_log

        from ui.console import set_gui_mode
        set_gui_mode(log_widget, self)

        log_panel.log_text(
            "[bold #89DDFF]CLINICSAY[/bold #89DDFF] [dim]Replica[/dim]"
        )
        log_panel.log_text("[dim]" + "─" * 40 + "[/dim]")
        log_panel.log_text(
            "[dim]Selecciona Clonar Ambiente o Restaurar Backup.[/dim]\n"
        )

    # ── Navegacion ────────────────────────────────────────────

    def on_sidebar_view_selected(self, event: Sidebar.ViewSelected) -> None:
        self.query_one(ContentArea).show_view(event.view_id)

    # ── Entorno ───────────────────────────────────────────────

    def on_title_bar_environment_changed(self, event: TitleBar.EnvironmentChanged) -> None:
        color = ENV_COLORS.get(event.env_name, "#8F93A2")
        log_panel = self.query_one(LogPanel)
        log_panel.log_text(
            f"[bold {color}]Entorno: {event.env_name}[/bold {color}]"
        )

    # ── Acciones ──────────────────────────────────────────────

    def on_content_area_action_requested(self, event: ContentArea.ActionRequested) -> None:
        handlers = {
            "clone-env":      self._do_clone_environment,
            "restore-backup": self._do_restore_backup,
        }
        handler = handlers.get(event.action_id)
        if handler:
            self.query_one(LogPanel).mark_execution_start()
            self.run_worker(handler, thread=True)

    def _do_clone_environment(self):
        from ui import error
        from ui.widgets.progress_modal import OperationProgressModal

        modal = OperationProgressModal("Clonando Ambiente", target_app=self)
        try:
            from environment.clone_environment import clone_environment
            clone_environment(progress=modal)
        except Exception as e:
            error(f"{e}")
            import traceback
            traceback.print_exc()
        finally:
            if modal._started:
                self.call_from_thread(modal.dismiss)

    def _do_restore_backup(self):
        from ui import error
        try:
            from environment.restore_from_backup import restore_from_backup
            restore_from_backup()
        except Exception as e:
            error(f"{e}")
            import traceback
            traceback.print_exc()

    # ── Bindings ──────────────────────────────────────────────

    def action_change_env(self) -> None:
        from ui.widgets.title_bar import EnvSelectDialog
        self.push_screen(EnvSelectDialog(), self._on_env_selected)

    def _on_env_selected(self, env_name: str) -> None:
        if not env_name:
            return
        current = get_environment()
        if env_name == current:
            return
        title_bar = self.query_one(TitleBar)
        title_bar.on_env_selected(env_name)


if __name__ == "__main__":
    app = ReplicaApp()
    result = app.run()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
