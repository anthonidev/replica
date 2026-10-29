from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Static, Input, Button, SelectionList, Select
from textual.widgets.selection_list import Selection


class AskDialog(ModalScreen[str]):
    """Dialogo modal para solicitar texto al usuario."""

    DEFAULT_CSS = """
    AskDialog {
        align: center middle;
    }

    AskDialog #dialog-container {
        width: 60;
        max-width: 80%;
        height: auto;
        max-height: 80%;
        background: #1A1C25;
        border: round #89DDFF 40%;
        padding: 2 3;
    }

    AskDialog #dialog-prompt {
        margin-bottom: 1;
        color: #8F93A2;
    }

    AskDialog #dialog-hint {
        color: #4B526D;
        margin-bottom: 1;
        padding: 0 2;
    }

    AskDialog #dialog-input {
        margin-bottom: 2;
    }

    AskDialog #dialog-buttons {
        height: 3;
        align: right middle;
    }

    AskDialog #dialog-buttons Button {
        margin-left: 1;
        min-width: 14;
    }

    AskDialog #btn-cancel {
        background: transparent;
        color: #4B526D;
        border: tall #3B3F51;
    }

    AskDialog #btn-accept {
        background: #89DDFF 15%;
        color: #89DDFF;
        border: tall #89DDFF 30%;
    }
    """

    def __init__(self, prompt: str, default: str = None, hint: str = None):
        super().__init__()
        self._prompt = prompt
        self._default = default or ""
        self._hint = hint

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog-container"):
            yield Static(f"[bold #89DDFF]?[/]  {self._prompt}", id="dialog-prompt")
            if self._hint:
                yield Static(self._hint, id="dialog-hint")
            yield Input(value=self._default, placeholder="Escribe aqui...", id="dialog-input")
            with Horizontal(id="dialog-buttons"):
                yield Button("Cancelar", id="btn-cancel", variant="default")
                yield Button("Aceptar", id="btn-accept", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#dialog-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-accept":
            self.dismiss(self.query_one("#dialog-input", Input).value)
        elif event.button.id == "btn-cancel":
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)


class ConfirmDialog(ModalScreen[bool]):
    """Dialogo modal de confirmacion Si/No."""

    DEFAULT_CSS = """
    ConfirmDialog {
        align: center middle;
    }

    ConfirmDialog #dialog-container {
        width: 60;
        max-width: 80%;
        height: auto;
        max-height: 80%;
        background: #1A1C25;
        border: round #FFCB6B 40%;
        padding: 2 3;
    }

    ConfirmDialog #dialog-prompt {
        margin-bottom: 2;
        color: #8F93A2;
    }

    ConfirmDialog #dialog-buttons {
        height: 3;
        align: right middle;
    }

    ConfirmDialog #dialog-buttons Button {
        margin-left: 1;
        min-width: 14;
    }

    ConfirmDialog #btn-no {
        background: #FF5370 15%;
        color: #FF5370;
        border: tall #FF5370 30%;
    }

    ConfirmDialog #btn-yes {
        background: #C3E88D 15%;
        color: #C3E88D;
        border: tall #C3E88D 30%;
    }
    """

    def __init__(self, prompt: str, default: bool = False):
        super().__init__()
        self._prompt = prompt
        self._default = default

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog-container"):
            yield Static(f"[bold #FFCB6B]\u26A0[/]  {self._prompt}", id="dialog-prompt")
            with Horizontal(id="dialog-buttons"):
                yield Button("No", id="btn-no", variant="error")
                yield Button("Si", id="btn-yes", variant="success")

    def on_mount(self) -> None:
        self.query_one("#btn-yes" if self._default else "#btn-no", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-yes")


class SelectOption(Static):
    """Opcion clickeable en el SelectDialog."""

    DEFAULT_CSS = """
    SelectOption {
        width: 100%;
        height: 3;
        padding: 0 2;
        content-align: left middle;
        background: transparent;
        color: #8F93A2;
    }

    SelectOption:hover {
        background: #89DDFF 10%;
        color: #89DDFF;
    }

    SelectOption.--hidden {
        display: none;
    }
    """

    class Selected(Message):
        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    def __init__(self, label: str, index: int):
        super().__init__(f"  [#4B526D]\u25CB[/#4B526D]  {label}")
        self._index = index
        self._label = label

    def on_click(self) -> None:
        self.post_message(self.Selected(self._index))


class SelectDialog(ModalScreen[str]):
    """Dialogo modal con lista de opciones clickeables, buscador y scroll."""

    DEFAULT_CSS = """
    SelectDialog {
        align: center middle;
    }

    SelectDialog #dialog-container {
        width: 50;
        max-width: 80%;
        height: auto;
        max-height: 50%;
        background: #1A1C25;
        border: round #89DDFF 40%;
        padding: 2 3;
    }

    SelectDialog #dialog-prompt {
        margin-bottom: 1;
        color: #8F93A2;
    }

    SelectDialog #dialog-search {
        margin-bottom: 1;
    }

    SelectDialog #dialog-options {
        max-height: 15;
        margin-bottom: 1;
        scrollbar-size: 1 1;
    }

    SelectDialog #btn-select-cancel {
        width: 100%;
        background: transparent;
        color: #4B526D;
        border: none;
    }

    SelectDialog #btn-select-cancel:hover {
        color: #FF5370;
    }
    """

    def __init__(self, prompt: str, options: list[str]):
        super().__init__()
        self._prompt = prompt
        self._options = options

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog-container"):
            yield Static(
                f"[bold #89DDFF]?[/]  {self._prompt}",
                id="dialog-prompt",
            )
            yield Input(placeholder="Buscar...", id="dialog-search")
            with VerticalScroll(id="dialog-options"):
                for i, option in enumerate(self._options):
                    yield SelectOption(option, i)
            yield Button("Cancelar", id="btn-select-cancel", variant="default")

    def on_mount(self) -> None:
        self.query_one("#dialog-search", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "dialog-search":
            query = event.value.strip().lower()
            for opt in self.query(SelectOption):
                if query and query not in opt._label.lower():
                    opt.add_class("--hidden")
                else:
                    opt.remove_class("--hidden")

    def on_select_option_selected(self, event: SelectOption.Selected) -> None:
        if 0 <= event.index < len(self._options):
            self.dismiss(self._options[event.index])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-select-cancel":
            self.dismiss("")


class MultiSelectDialog(ModalScreen[list[str]]):
    """Dialogo modal con lista de checkboxes + buscador para seleccion multiple."""

    DEFAULT_CSS = """
    MultiSelectDialog {
        align: center middle;
    }

    MultiSelectDialog #ms-container {
        width: 60;
        max-width: 85%;
        height: auto;
        max-height: 65%;
        background: #1A1C25;
        border: round #89DDFF 40%;
        padding: 2 3;
    }

    MultiSelectDialog #ms-prompt {
        margin-bottom: 1;
        color: #8F93A2;
    }

    MultiSelectDialog #ms-search {
        margin-bottom: 1;
    }

    MultiSelectDialog #ms-list {
        max-height: 18;
        margin-bottom: 1;
        scrollbar-size: 1 1;
    }

    MultiSelectDialog #ms-buttons {
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    MultiSelectDialog #btn-ms-confirm {
        width: 1fr;
        background: #4CAF50 20%;
        color: #4CAF50;
        border: none;
        margin-right: 1;
    }

    MultiSelectDialog #btn-ms-confirm:hover {
        background: #4CAF50 40%;
    }

    MultiSelectDialog #btn-ms-cancel {
        width: 1fr;
        background: transparent;
        color: #4B526D;
        border: none;
    }

    MultiSelectDialog #btn-ms-cancel:hover {
        color: #FF5370;
    }
    """

    def __init__(self, prompt: str, options: list[str]):
        super().__init__()
        self._prompt = prompt
        self._options = options
        self._selected: set[str] = set()

    def compose(self) -> ComposeResult:
        with Vertical(id="ms-container"):
            yield Static(
                f"[bold #89DDFF]?[/]  {self._prompt}",
                id="ms-prompt",
            )
            yield Input(placeholder="Buscar...", id="ms-search")
            yield SelectionList(
                *[Selection(opt, opt) for opt in self._options],
                id="ms-list",
            )
            with Horizontal(id="ms-buttons"):
                yield Button("Confirmar", id="btn-ms-confirm", variant="success")
                yield Button("Cancelar",  id="btn-ms-cancel",  variant="default")

    def on_mount(self) -> None:
        self.query_one("#ms-search", Input).focus()

    def on_selection_list_selected_changed(self, event: SelectionList.SelectedChanged) -> None:
        # Sincroniza solo los items visibles: quita los desmarcados, agrega los marcados.
        # No reemplaza _selected completo para no perder clinicas ocultas por el filtro.
        sl = event.selection_list
        visible_values = {sl.get_option_at_index(i).value for i in range(sl.option_count)}
        self._selected -= visible_values
        self._selected.update(sl.selected)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "ms-search":
            return
        query = event.value.strip().lower()
        sl = self.query_one("#ms-list", SelectionList)

        # Reconstruye la lista con solo las opciones que coinciden con el filtro,
        # marcando como seleccionadas las que el usuario ya habia elegido.
        visible = [
            opt for opt in self._options
            if not query or query in opt.lower()
        ]
        sl.clear_options()
        for opt in visible:
            sl.add_option(Selection(opt, opt, initial_state=opt in self._selected))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-ms-confirm":
            # Combina selecciones visibles + las que quedaron fuera del filtro
            sl = self.query_one("#ms-list", SelectionList)
            self._selected.update(sl.selected)
            self.dismiss(list(self._selected))
        elif event.button.id == "btn-ms-cancel":
            self.dismiss([])

