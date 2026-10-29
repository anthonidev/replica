"""
Contenedor horizontal con grip arrastrable para redimensionar paneles.
"""
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.events import MouseMove, MouseDown, MouseUp
from textual.reactive import reactive


class ResizeGrip(Widget):
    """Grip vertical arrastrable entre paneles."""

    DEFAULT_CSS = """
    ResizeGrip {
        width: 1;
        height: 100%;
        background: #1A1C25;
    }

    ResizeGrip:hover {
        background: #89DDFF 30%;
    }

    ResizeGrip.-dragging {
        background: #89DDFF 50%;
    }
    """

    dragging: reactive[bool] = reactive(False)

    def render(self) -> str:
        return ""

    class Dragged(Message):
        def __init__(self, screen_x: int) -> None:
            super().__init__()
            self.screen_x = screen_x

    def on_mouse_down(self, event: MouseDown) -> None:
        self.dragging = True
        self.add_class("-dragging")
        self.capture_mouse()
        event.stop()

    def on_mouse_up(self, event: MouseUp) -> None:
        self.dragging = False
        self.remove_class("-dragging")
        self.release_mouse()
        event.stop()

    def on_mouse_move(self, event: MouseMove) -> None:
        if self.dragging:
            self.post_message(self.Dragged(event.screen_x))
            event.stop()


class ResizableHorizontal(Horizontal):
    """Horizontal container con grip para redimensionar hijos."""

    DEFAULT_CSS = """
    ResizableHorizontal {
        width: 1fr;
        height: 1fr;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._content_pct = 25

    def on_mount(self) -> None:
        # Insertar grip entre los dos hijos
        children = list(self.children)
        if len(children) >= 2:
            grip = ResizeGrip()
            self.mount(grip, after=children[0])
            self._apply_sizes()

    def _apply_sizes(self) -> None:
        children = [c for c in self.children if not isinstance(c, ResizeGrip)]
        if len(children) >= 2:
            children[0].styles.width = f"{self._content_pct}%"
            children[1].styles.width = f"{100 - self._content_pct}%"

    def on_resize_grip_dragged(self, event: ResizeGrip.Dragged) -> None:
        sidebar = self.app.query_one("Sidebar")
        sidebar_w = sidebar.size.width if sidebar else 30
        available = self.size.width
        if available <= 0:
            return
        relative_x = event.screen_x - sidebar_w
        pct = max(25, min(80, int((relative_x / available) * 100)))
        self._content_pct = pct
        self._apply_sizes()
