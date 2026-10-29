from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Static, Button

from config.settings import ENVIRONMENTS, get_environment, set_environment


ENV_COLORS = {
    "STAGING":     "#FFCB6B",
    "INTEGRATION": "#82AAFF",
    "PRODUCTION":  "#FF5370",
}

ENV_SHORT = {
    "STAGING":     "STG",
    "INTEGRATION": "INT",
    "PRODUCTION":  "PRD",
}


class EnvOption(Static):
    DEFAULT_CSS = """
    EnvOption {
        width: 100%;
        height: 3;
        padding: 0 2;
        content-align: left middle;
        background: transparent;
        color: #8F93A2;
    }
    EnvOption:hover { background: #89DDFF 10%; color: #89DDFF; }
    EnvOption.--current { color: #C3E88D; text-style: bold; }
    """

    class Selected(Message):
        def __init__(self, env_name: str) -> None:
            super().__init__()
            self.env_name = env_name

    def __init__(self, env_name: str, is_current: bool):
        color = ENV_COLORS.get(env_name, "#8F93A2")
        short = ENV_SHORT.get(env_name, env_name)
        check = " *" if is_current else "  "
        super().__init__(f"  [{color}]{short}[/{color}]  {env_name}{check}")
        self.env_name = env_name
        if is_current:
            self.add_class("--current")

    def on_click(self) -> None:
        self.post_message(self.Selected(self.env_name))


class EnvSelectDialog(ModalScreen[str]):
    DEFAULT_CSS = """
    EnvSelectDialog { align: center middle; }
    EnvSelectDialog #env-dialog-container {
        width: 45; height: auto;
        background: #1A1C25; border: round #89DDFF 40%; padding: 2 3;
    }
    EnvSelectDialog #env-dialog-title { margin-bottom: 1; color: #8F93A2; }
    EnvSelectDialog #btn-env-cancel {
        width: 100%; margin-top: 1;
        background: transparent; color: #4B526D; border: none;
    }
    EnvSelectDialog #btn-env-cancel:hover { color: #FF5370; }
    """

    def compose(self) -> ComposeResult:
        current = get_environment()
        with Vertical(id="env-dialog-container"):
            yield Static("[bold #89DDFF]Seleccionar entorno[/bold #89DDFF]", id="env-dialog-title")
            with Vertical(id="env-dialog-options"):
                for env in ENVIRONMENTS:
                    yield EnvOption(env, is_current=(env == current))
            yield Button("Cancelar", id="btn-env-cancel", variant="default")

    def on_env_option_selected(self, event: EnvOption.Selected) -> None:
        self.dismiss(event.env_name)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-env-cancel":
            self.dismiss("")


class TitleBar(Widget):
    class EnvironmentChanged(Message):
        def __init__(self, env_name: str) -> None:
            super().__init__()
            self.env_name = env_name

    DEFAULT_CSS = """
    TitleBar {
        dock: top; height: 3; width: 100%;
        background: #090B10; border-bottom: solid #1A1C25; layout: horizontal;
    }
    TitleBar #title-text {
        width: 1fr; height: 3; content-align: center middle; color: #8F93A2;
    }
    TitleBar #env-badge {
        width: 20; height: 3; content-align: center middle; padding: 0 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold #89DDFF]Clinicsay[/bold #89DDFF][#4B526D] Replica[/#4B526D]",
            id="title-text",
        )
        yield Static("", id="env-badge")

    def on_mount(self) -> None:
        self._update_badge()

    def on_env_selected(self, env_name: str) -> None:
        if not env_name:
            return
        current = get_environment()
        if env_name == current:
            return
        set_environment(env_name)
        self._update_badge()
        self.post_message(self.EnvironmentChanged(env_name))

    def _update_badge(self) -> None:
        current = get_environment()
        color = ENV_COLORS.get(current, "#8F93A2")
        short = ENV_SHORT.get(current, current)
        self.query_one("#env-badge", Static).update(f"[bold {color}]{short}[/bold {color}]")
