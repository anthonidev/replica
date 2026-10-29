"""
Modal de progreso para operaciones largas (clonar ambiente, restaurar backup).

El modal muestra un resumen compacto: paso actual + barra de tablas + bytes
transferidos + tiempo elapsed. Los logs detallados siguen llegando al
LogPanel como siempre — el modal es informacion adicional, no reemplazo.

Uso desde un worker (thread):
    modal = OperationProgressModal("Clonando Ambiente")
    app.call_from_thread(app.push_screen, modal)
    try:
        modal.set_step(1, 4, "Dumps origen")           # thread-safe
        modal.advance_table("public.patient", size_bytes)   # thread-safe
        ...
    finally:
        app.call_from_thread(modal.dismiss)
"""
import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ProgressBar, Static


class OperationProgressModal(ModalScreen):
    """Modal con barra de progreso para operaciones largas.

    Todos los metodos `*_threadsafe` pueden llamarse desde workers; usan
    `app.call_from_thread` internamente para actualizar la UI.
    """

    DEFAULT_CSS = """
    OperationProgressModal {
        align: center middle;
    }

    OperationProgressModal #progress-container {
        width: 100;
        height: auto;
        background: #1A1C25;
        border: round #89DDFF 40%;
        padding: 2 3;
    }

    OperationProgressModal #progress-title {
        text-style: bold;
        color: #89DDFF;
        height: 1;
        content-align: center middle;
        margin-bottom: 1;
    }

    OperationProgressModal #progress-step {
        color: #C792EA;
        height: 1;
        margin-bottom: 1;
    }

    OperationProgressModal #progress-bar {
        width: 100%;
        margin-bottom: 1;
    }

    OperationProgressModal Bar {
        width: 1fr;
    }

    OperationProgressModal #progress-current-table {
        color: #4B526D;
        height: 1;
        margin-bottom: 1;
    }

    OperationProgressModal #progress-stats {
        color: #8F93A2;
        height: 1;
    }

    OperationProgressModal #progress-elapsed {
        color: #4B526D;
        height: 1;
    }
    """

    def __init__(self, title: str, target_app=None):
        super().__init__()
        self._title = title
        self._target_app = target_app  # para call_from_thread antes del mount
        self._t_start = None  # se setea en start() — no en __init__
        # Estado interno (la unica fuente de verdad — la UI lo refleja en cada render)
        self._step_idx = 0
        self._step_total = 0
        self._step_name = "Iniciando..."
        self._tables_done = 0
        self._tables_total = 0
        self._current_table = ""
        self._total_bytes = 0
        self._mounted = False
        self._started = False

    def compose(self) -> ComposeResult:
        with Vertical(id="progress-container"):
            yield Static(self._title, id="progress-title")
            yield Static("Iniciando...", id="progress-step")
            yield ProgressBar(total=100, show_eta=False, id="progress-bar")
            yield Static(" ", id="progress-current-table")
            yield Static(" ", id="progress-stats")
            yield Static(" ", id="progress-elapsed")

    def on_mount(self) -> None:
        self._mounted = True
        # Refrescar el tiempo elapsed cada segundo
        self.set_interval(1.0, self._refresh_elapsed)
        # Aplicar cualquier estado que haya llegado antes del mount
        self._render_state()

    # ────────────────────────────────────────────────────────────────────
    # API publica thread-safe (llamar desde workers)
    # ────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Pushea el modal y arranca el contador de tiempo.

        Debe llamarse desde el worker DESPUES de las pantallas modales de
        seleccion (select/confirm) — asi el tiempo medido refleja solo la
        operacion real, no la espera por input del usuario.
        """
        if self._started:
            return
        self._started = True
        self._t_start = time.time()
        if self._target_app is not None:
            try:
                self._target_app.call_from_thread(
                    self._target_app.push_screen, self
                )
            except Exception:
                pass

    def set_step(self, index: int, total: int, name: str) -> None:
        """Actualiza el paso actual (ej. set_step(2, 4, 'Recrear destinos')).

        Cualquier `set_step` sale del modo COPY (resetea tables_total). Si el
        siguiente step vuelve a tener progreso por tabla, debe llamar
        `set_tables_total` para reactivar el modo.
        """
        self._step_idx = index
        self._step_total = total
        self._step_name = name
        # Salir del modo COPY al cambiar de step
        self._tables_total = 0
        self._current_table = ""
        self._schedule_render()

    def set_tables_total(self, total: int) -> None:
        """Establece el numero total de tablas a copiar (al inicio del paso 3)."""
        self._tables_total = total
        self._tables_done = 0
        self._schedule_render()

    def advance_table(self, table_name: str, size_bytes: int) -> None:
        """Marca una tabla como copiada — actualiza barra y stats."""
        self._tables_done += 1
        self._total_bytes += size_bytes
        self._current_table = table_name
        self._schedule_render()

    # ────────────────────────────────────────────────────────────────────
    # Render (corre en el thread de UI)
    # ────────────────────────────────────────────────────────────────────

    def _schedule_render(self) -> None:
        """Programa un repintado en el thread de UI (no-op si no esta montado)."""
        if not self._mounted:
            return
        try:
            self.app.call_from_thread(self._render_state)
        except Exception:
            pass  # nunca rompemos el worker por un fallo de UI

    def _render_state(self) -> None:
        if not self._mounted:
            return
        try:
            # Step header
            if self._step_total > 0:
                self.query_one("#progress-step", Static).update(
                    f"[{self._step_idx}/{self._step_total}] {self._step_name}"
                )

            # Barra: si estamos en COPY, muestra tablas (granular).
            # Si no (pasos 1, 2, 4): modo indeterminate — no podemos predecir
            # con precision el avance, pero la animacion indica actividad.
            bar = self.query_one("#progress-bar", ProgressBar)
            if self._tables_total > 0:
                bar.update(total=self._tables_total, progress=self._tables_done)
            else:
                bar.update(total=None)

            # Tabla actual (solo durante COPY)
            current = f"  {self._current_table}" if self._tables_total > 0 and self._current_table else " "
            self.query_one("#progress-current-table", Static).update(current)

            # Stats: tablas (solo en COPY) + total de bytes (persistente)
            parts = []
            if self._tables_total > 0:
                parts.append(f"Tablas: {self._tables_done}/{self._tables_total}")
            if self._total_bytes > 0:
                mb = self._total_bytes / 1_048_576
                parts.append(f"Datos: {mb:,.1f} MB")
            self.query_one("#progress-stats", Static).update(
                "    ".join(parts) if parts else " "
            )
        except Exception:
            pass  # widgets aun no listos, lo retomamos en el siguiente render

    def _refresh_elapsed(self) -> None:
        if self._t_start is None:
            return
        secs = int(time.time() - self._t_start)
        mins, s = divmod(secs, 60)
        if mins > 0:
            text = f"Tiempo: {mins}m {s:02d}s"
        else:
            text = f"Tiempo: {s}s"
        try:
            self.query_one("#progress-elapsed", Static).update(text)
        except Exception:
            pass
