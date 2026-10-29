from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class SidebarOption(Static):
    DEFAULT_CSS = """
    SidebarOption {
        padding: 0 2; height: 3;
        content-align: left middle;
        background: transparent; color: #4B526D;
    }
    SidebarOption:hover { background: #1A1C25; color: #8F93A2; }
    SidebarOption.--active {
        background: #89DDFF 12%; color: #89DDFF; text-style: bold;
    }
    SidebarOption.--active:hover { background: #89DDFF 18%; }
    """

    class Clicked(Message):
        def __init__(self, view_id: str) -> None:
            super().__init__()
            self.view_id = view_id

    def __init__(self, label: str, view_id: str, icon: str = ""):
        self._label = label
        self._icon = icon
        text = f" {icon}  {label}" if icon else f"  {label}"
        super().__init__(text)
        self.view_id = view_id

    def on_click(self) -> None:
        self.post_message(self.Clicked(self.view_id))


class Sidebar(Widget):
    class ViewSelected(Message):
        def __init__(self, view_id: str) -> None:
            super().__init__()
            self.view_id = view_id

    DEFAULT_CSS = """
    Sidebar {
        width: 28; dock: left; background: #090B10;
    }
    Sidebar #sidebar-nav { height: 1fr; scrollbar-size: 1 1; }
    """

    MENU_ITEMS = [
        ("Clonar Ambiente",      "clone",   "⬇"),
        ("Restaurar Backup",     "restore", "↺"),
    ]

    active_view: reactive[str] = reactive("clone")

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="sidebar-nav"):
            for label, view_id, icon in self.MENU_ITEMS:
                yield SidebarOption(label, view_id, icon)

    def on_mount(self) -> None:
        self._update_active()

    def on_sidebar_option_clicked(self, event: SidebarOption.Clicked) -> None:
        self.active_view = event.view_id
        self.post_message(self.ViewSelected(event.view_id))
        self._update_active()

    def _update_active(self) -> None:
        for option in self.query(SidebarOption):
            option.remove_class("--active")
            if option.view_id == self.active_view:
                option.add_class("--active")
