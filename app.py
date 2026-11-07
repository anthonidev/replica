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

from config.settings import get_environment
from ui.widgets.log_panel import LogPanel
from ui.widgets.content_area import ContentArea
from ui.widgets.title_bar import ENV_COLORS


THEME = TextualTheme(
    name="replica",
    primary="#89DDFF",
    secondary="#C792EA",
    accent="#82AAFF",
    warning="#FFCB6B",
    error="#FF5370",
    success="#C3E88D",
    background="#0D0F18",
    surface="#13151F",
    panel="#1A1D2E",
    dark=True,
    variables={
        "text": "#CDD6F4",
        "text-muted": "#6C7086",
        "text-disabled": "#45475A",
        "border-color": "#313244",
    },
)


class ReplicaApp(App):
    """App para clonar ambientes y restaurar desde backup."""

    TITLE = "Clinicsay Replica"
    CSS_PATH = "app.tcss"
    BINDINGS = [
        ("q", "quit", "Salir"),
        ("e", "change_env", "Entorno"),
    ]

    def __init__(self):
        super().__init__()
        self.register_theme(THEME)
        self.theme = "replica"

    def compose(self) -> ComposeResult:
        yield ContentArea()
        yield LogPanel()

    def on_mount(self) -> None:
        log_panel = self.query_one(LogPanel)
        log_widget = log_panel.rich_log

        from ui.console import set_gui_mode
        set_gui_mode(log_widget, self)

        log_panel.log_text("[bold]CLINICSAY[/bold] [dim]Replica[/dim]")
        log_panel.log_text("[dim]─────────────────────────────────[/dim]")
        log_panel.log_text(f"[dim]Entorno activo: {get_environment()}[/dim]\n")

    # ── Acciones ──────────────────────────────────────────────

    def on_content_area_action_requested(self, event: ContentArea.ActionRequested) -> None:
        handlers = {
            "clone-env":      self._do_clone_environment,
            "restore-backup": self._do_restore_backup,
        }
        handler = handlers.get(event.action_id)
        if handler:
            self.query_one(LogPanel).mark_execution_start()
            self.run_worker(lambda: handler(event.params), thread=True)

    def _do_clone_environment(self, params: dict):
        from ui import error
        from ui.widgets.progress_modal import OperationProgressModal

        modal = OperationProgressModal("Clonando Ambiente", target_app=self)
        try:
            from environment.clone_environment import clone_environment
            clone_environment(progress=modal, params=params)
        except Exception as e:
            error(f"{e}")
            import traceback
            traceback.print_exc()
        finally:
            if modal._started:
                self.call_from_thread(modal.dismiss)

    def _do_restore_backup(self, params: dict):
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
        if not env_name or env_name == get_environment():
            return
        from config.settings import set_environment
        set_environment(env_name)
        color = ENV_COLORS.get(env_name, "#8F93A2")
        self.query_one(LogPanel).log_text(
            f"[bold {color}]Entorno: {env_name}[/bold {color}]"
        )


if __name__ == "__main__":
    app = ReplicaApp()
    result = app.run()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
