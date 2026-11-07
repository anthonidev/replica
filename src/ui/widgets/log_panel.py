import threading

from rich.text import Text

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.geometry import Offset
from textual.widget import Widget
from textual.widgets import RichLog, Static


class _ResizeHandle(Widget, can_focus=False):
    """Barra superior arrastrable para redimensionar el LogPanel."""

    DEFAULT_CSS = """
    _ResizeHandle {
        height: 1;
        width: 100%;
        background: #0D0F18;
        border-top: solid #1A1D2E;
    }
    _ResizeHandle:hover {
        border-top: solid #45475A;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._drag_start_y: int | None = None
        self._drag_start_height: int | None = None

    def on_mouse_down(self, event: events.MouseDown) -> None:
        event.stop()
        self._drag_start_y = event.screen_y
        self._drag_start_height = self.app.query_one(LogPanel).styles.height.value
        self.capture_mouse()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self._drag_start_y is None:
            return
        event.stop()
        delta = self._drag_start_y - event.screen_y
        new_h = max(4, int(self._drag_start_height + delta))
        self.app.query_one(LogPanel).styles.height = new_h

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if self._drag_start_y is None:
            return
        event.stop()
        self._drag_start_y = None
        self._drag_start_height = None
        self.release_mouse()


class LogPanel(Widget):
    """Panel de logs redimensionable."""

    DEFAULT_CSS = """
    LogPanel {
        height: 10;
        background: #0D0F18;
        layout: vertical;
    }

    LogPanel #log-output {
        height: 1fr;
        background: #0D0F18;
        padding: 0 1;
        scrollbar-size: 1 1;
    }

    LogPanel #log-action-bar {
        height: 1;
        background: #0D0F18;
        padding: 0 1;
    }

    LogPanel #log-status {
        width: 1fr;
        height: 1;
        content-align: left middle;
        color: #45475A;
    }

    LogPanel .log-btn {
        width: auto;
        height: 1;
        background: transparent;
        color: #45475A;
        padding: 0 1;
        content-align: center middle;
    }

    LogPanel .log-btn:hover {
        color: #89DDFF;
    }

    LogPanel #btn-clear:hover {
        color: #FF5370;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._text_buffer: list[str] = []
        self._last_exec_start: int = 0
        self._lock = threading.Lock()

    def compose(self) -> ComposeResult:
        yield _ResizeHandle()
        yield RichLog(
            id="log-output",
            highlight=True,
            markup=True,
            wrap=True,
            auto_scroll=True,
        )
        with Horizontal(id="log-action-bar"):
            yield Static("", id="log-status")
            yield Static("copiar", id="btn-copy-all", classes="log-btn")
            yield Static("limpiar", id="btn-clear", classes="log-btn")

    @property
    def rich_log(self) -> RichLog:
        return self.query_one("#log-output", RichLog)

    def log_text(self, markup: str) -> None:
        text = Text.from_markup(markup)
        self.rich_log.write(text)
        with self._lock:
            self._text_buffer.append(text.plain)

    def append_to_buffer(self, plain_text: str) -> None:
        with self._lock:
            self._text_buffer.append(plain_text)

    def mark_execution_start(self) -> None:
        with self._lock:
            self._last_exec_start = len(self._text_buffer)

    def _get_all_text(self) -> str:
        with self._lock:
            return "\n".join(self._text_buffer)

    def _copy(self, text: str) -> None:
        if not text.strip():
            self._update_status("Nada que copiar")
            return
        import subprocess, platform
        try:
            self.app.copy_to_clipboard(text)
        except Exception:
            pass
        try:
            system = platform.system()
            if system == "Windows":
                p = subprocess.Popen("clip", stdin=subprocess.PIPE, shell=True)
                p.communicate(text.encode("utf-16-le"))
            elif system == "Darwin":
                p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                p.communicate(text.encode("utf-8"))
            else:
                p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
                p.communicate(text.encode("utf-8"))
        except Exception:
            pass

    def on_click(self, event: events.Click) -> None:
        widget_id = event.widget.id if event.widget else None
        if widget_id == "btn-clear":
            event.stop()
            self.rich_log.clear()
            with self._lock:
                self._text_buffer.clear()
                self._last_exec_start = 0
            self._update_status("Limpiado")
        elif widget_id == "btn-copy-all":
            event.stop()
            text = self._get_all_text()
            self._copy(text)
            self._update_status(f"Copiado ({len(text.splitlines())} líneas)")

    def _update_status(self, msg: str) -> None:
        try:
            self.query_one("#log-status", Static).update(f"[dim]{msg}[/dim]")
        except Exception:
            pass
