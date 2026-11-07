import threading
from typing import List, Dict, Any
from io import StringIO

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.rule import Rule

_render_console = Console(file=StringIO(), width=120, no_color=True)

_gui_log = None
_gui_app = None


def _render_to_plain(renderable) -> str:
    if hasattr(renderable, 'plain'):
        return renderable.plain
    try:
        _render_console.file.truncate(0)
        _render_console.file.seek(0)
        _render_console.print(renderable)
        _render_console.file.seek(0)
        return _render_console.file.read().rstrip()
    except Exception:
        return str(renderable)


class _GuiConsoleProxy:
    def print(self, *args, **kwargs):
        for arg in args:
            if isinstance(arg, str):
                _gui_write_markup(arg)
            elif arg == "":
                pass
            else:
                _gui_write(arg)

    def __getattr__(self, name):
        return lambda *a, **kw: None


console = _GuiConsoleProxy()


def set_gui_mode(log_widget, app):
    global _gui_log, _gui_app
    _gui_log = log_widget
    _gui_app = app


def _gui_write(renderable):
    if _gui_app and _gui_log:
        _gui_app.call_from_thread(_gui_log.write, renderable)
        try:
            from ui.widgets.log_panel import LogPanel
            log_panel = _gui_app.query_one(LogPanel)
            plain = _render_to_plain(renderable)
            _gui_app.call_from_thread(log_panel.append_to_buffer, plain)
        except Exception:
            pass


def _gui_write_markup(markup: str):
    if _gui_app and _gui_log:
        text = Text.from_markup(markup)
        _gui_app.call_from_thread(_gui_log.write, text)
        try:
            from ui.widgets.log_panel import LogPanel
            log_panel = _gui_app.query_one(LogPanel)
            _gui_app.call_from_thread(log_panel.append_to_buffer, text.plain)
        except Exception:
            pass


def _gui_ask(prompt_text: str, default: str = None, hint: str = None) -> str:
    from ui.widgets.input_dialog import AskDialog
    result = {"value": default or ""}
    event = threading.Event()

    def on_result(value):
        result["value"] = value
        event.set()

    _gui_app.call_from_thread(
        _gui_app.push_screen,
        AskDialog(prompt_text, default=default, hint=hint),
        on_result,
    )
    event.wait()
    return result["value"]


def _gui_confirm(prompt_text: str, default: bool = False) -> bool:
    from ui.widgets.input_dialog import ConfirmDialog
    result = {"value": default}
    event = threading.Event()

    def on_result(value):
        result["value"] = value
        event.set()

    _gui_app.call_from_thread(
        _gui_app.push_screen,
        ConfirmDialog(prompt_text, default=default),
        on_result,
    )
    event.wait()
    return result["value"]


def _gui_select(prompt_text: str, options: list[str]) -> str:
    from ui.widgets.input_dialog import SelectDialog
    result = {"value": ""}
    event = threading.Event()

    def on_result(value):
        result["value"] = value
        event.set()

    _gui_app.call_from_thread(
        _gui_app.push_screen,
        SelectDialog(prompt_text, options),
        on_result,
    )
    event.wait()
    return result["value"]


def _gui_multi_select(prompt_text: str, options: list[str]) -> list[str]:
    from ui.widgets.input_dialog import MultiSelectDialog
    result: dict[str, list[str]] = {"value": []}
    event = threading.Event()

    def on_result(value):
        result["value"] = value or []
        event.set()

    _gui_app.call_from_thread(
        _gui_app.push_screen,
        MultiSelectDialog(prompt_text, options),
        on_result,
    )
    event.wait()
    return result["value"]


# ── Funciones de UI ──────────────────────────────────────────────────────────

def clear():
    pass


def print_banner(subtitle: str = None):
    pass


def print_header(text: str, style: str = "header"):
    _gui_write(Rule(style="magenta"))
    _gui_write_markup(f"[{style}]{text}[/{style}]")
    _gui_write(Rule(style="magenta"))


def print_operation_header(title: str):
    print_header(title)
    try:
        from config.settings import get_environment
        info(f"Entorno: {get_environment()}")
    except Exception:
        pass


def print_preview(data: dict, title: str = "Datos a aplicar"):
    print_key_value(data, title=title)


def print_summary(message: str, data: dict | None = None, title: str = "Resumen"):
    success(message)
    if data:
        print_key_value(data, title=title)


def print_subheader(text: str):
    _gui_write_markup(f"\n[bold cyan]▶ {text}[/bold cyan]")
    _gui_write(Rule(style="dim"))


def print_menu(title: str, options: List[Dict[str, str]]):
    pass


def print_menu_option(key: str, label: str):
    pass


def print_separator(style: str = "dim"):
    _gui_write(Rule(style=style))


def print_rule(text: str = "", style: str = "cyan"):
    _gui_write(Rule(text, style=style))


def print_key_value(data: Dict[str, Any], title: str = None):
    if title:
        _gui_write_markup(f"\n[bold]{title}[/bold]")
        _gui_write(Rule(style="dim"))
    for key, value in data.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            value = "[dim]-[/dim]"
        _gui_write_markup(f"  [cyan]{key}:[/cyan] {value}")


def print_table(
    title: str,
    columns: List[str],
    rows: List[List[str]],
    show_header: bool = True,
):
    table = Table(title=title, show_header=show_header, header_style="bold cyan")
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*row)
    _gui_write(table)


def print_tree(title: str, items: Dict[str, Any], guide_style: str = "cyan"):
    from rich.tree import Tree as RichTree
    tree = RichTree(f"[bold]{title}[/bold]", guide_style=guide_style)

    def add_items(parent, data):
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    branch = parent.add(f"[cyan]{key}[/cyan]")
                    add_items(branch, value)
                else:
                    display_value = value if value else "[dim]-[/dim]"
                    parent.add(f"[cyan]{key}:[/cyan] {display_value}")
        elif isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, dict):
                    branch = parent.add(f"[yellow]Item {i + 1}[/yellow]")
                    add_items(branch, item)
                else:
                    parent.add(str(item))

    add_items(tree, items)
    _gui_write(tree)


def print_panel(
    content: str,
    title: str = None,
    style: str = "cyan",
    expand: bool = False,
):
    _gui_write(Panel(
        content,
        title=title,
        border_style=style,
        expand=expand,
        padding=(1, 2),
    ))


def info(message: str):
    _gui_write_markup(f"[cyan]ℹ[/cyan]  {message}")


def success(message: str):
    _gui_write_markup(f"[green]✓[/green]  {message}")


def warning(message: str):
    _gui_write_markup(f"[yellow]⚠[/yellow]  {message}")


def error(message: str):
    _gui_write_markup(f"[red bold]✗[/red bold]  {message}")


def step(message: str):
    _gui_write_markup(f"[blue]→[/blue]  {message}")


def ask(prompt: str, default: str = None, hint: str = None) -> str:
    return _gui_ask(prompt, default, hint=hint)


def confirm(prompt: str, default: bool = False) -> bool:
    return _gui_confirm(prompt, default)


def select(prompt: str, options: list[str]) -> str:
    return _gui_select(prompt, options)


def multi_select(prompt: str, options: list[str]) -> list[str]:
    return _gui_multi_select(prompt, options)
