import threading

from rich.text import Text

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import RichLog, Static, Button
from textual.widget import Widget


class LogPanel(Widget):
    """Panel de logs estilo terminal con copiado al clipboard."""

    DEFAULT_CSS = """
    LogPanel {
        background: #0F111A;
    }

    LogPanel #log-header-bar {
        layout: horizontal;
        height: 3;
        background: #090B10;
        padding: 0 1;
    }

    LogPanel #log-title {
        width: 1fr;
        content-align: left middle;
        padding: 0 1;
        color: #4B526D;
        text-style: bold;
    }

    LogPanel .log-btn {
        min-width: 3;
        height: 3;
        margin: 0 0 0 1;
        background: transparent;
        color: #4B526D;
        border: none;
    }

    LogPanel .log-btn:hover {
        color: #89DDFF;
        background: #89DDFF 10%;
    }

    LogPanel #btn-clear:hover {
        color: #FF5370;
        background: #FF5370 10%;
    }

    LogPanel #log-output {
        height: 1fr;
        background: #0F111A;
        padding: 0 1;
        scrollbar-size: 1 1;
    }

    LogPanel #log-status {
        height: 1;
        background: #090B10;
        padding: 0 2;
        color: #4B526D;
        content-align: right middle;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._text_buffer: list[str] = []
        self._last_exec_start: int = 0
        self._lock = threading.Lock()

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(id="log-header-bar"):
                yield Static("\u2630 Terminal", id="log-title")
                yield Button("Copiar todo", id="btn-copy-all", classes="log-btn")
                yield Button("Copiar ultimo", id="btn-copy-last", classes="log-btn")
                yield Button("Limpiar", id="btn-clear", classes="log-btn")
            yield RichLog(
                id="log-output",
                highlight=True,
                markup=True,
                wrap=True,
                auto_scroll=True,
            )
            yield Static("", id="log-status")

    @property
    def rich_log(self) -> RichLog:
        return self.query_one("#log-output", RichLog)

    def log_text(self, markup: str) -> None:
        """Escribe texto con markup al log y al buffer."""
        text = Text.from_markup(markup)
        self.rich_log.write(text)
        with self._lock:
            self._text_buffer.append(text.plain)

    def append_to_buffer(self, plain_text: str) -> None:
        """Agrega texto plano al buffer."""
        with self._lock:
            self._text_buffer.append(plain_text)

    def mark_execution_start(self) -> None:
        """Marca el inicio de una nueva ejecucion."""
        with self._lock:
            self._last_exec_start = len(self._text_buffer)

    def _get_all_text(self) -> str:
        with self._lock:
            return "\n".join(self._text_buffer)

    def _get_last_execution_text(self) -> str:
        with self._lock:
            return "\n".join(self._text_buffer[self._last_exec_start:])

    def _copy(self, text: str) -> None:
        """Copia texto al clipboard."""
        if not text.strip():
            self._update_status("Nada que copiar")
            return
        import subprocess
        import platform

        # Textual OSC 52 — funciona en Windows Terminal, iTerm2, etc.
        try:
            self.app.copy_to_clipboard(text)
        except Exception:
            pass

        # Fallback nativo por OS
        try:
            system = platform.system()
            if system == "Windows":
                # clip.exe en Windows necesita UTF-16LE
                process = subprocess.Popen(
                    "clip", stdin=subprocess.PIPE, shell=True,
                )
                process.communicate(text.encode("utf-16-le"))
            elif system == "Darwin":
                process = subprocess.Popen(
                    ["pbcopy"], stdin=subprocess.PIPE,
                )
                process.communicate(text.encode("utf-8"))
            else:
                process = subprocess.Popen(
                    ["xclip", "-selection", "clipboard"],
                    stdin=subprocess.PIPE,
                )
                process.communicate(text.encode("utf-8"))
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-clear":
            self.rich_log.clear()
            with self._lock:
                self._text_buffer.clear()
                self._last_exec_start = 0
            self._update_status("Terminal limpiada")

        elif event.button.id == "btn-copy-all":
            text = self._get_all_text()
            self._copy(text)
            lines = len(text.splitlines())
            self._update_status(f"Copiado: {lines} lineas")

        elif event.button.id == "btn-copy-last":
            text = self._get_last_execution_text()
            self._copy(text)
            lines = len(text.splitlines())
            self._update_status(f"Copiado ultima ejecucion: {lines} lineas")

    def _update_status(self, msg: str) -> None:
        try:
            self.query_one("#log-status", Static).update(f"[dim]{msg}[/dim]")
        except Exception:
            pass
