"""ActionMenu — overlay action picker (Space key).

Lists all actions from list_actions(). On select, suspends TUI and calls
execute_action(), then resumes on agent exit.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView

from phyrax.actions.engine import ActionTemplate, execute_action, list_actions
from phyrax.config import PhyraxConfig
from phyrax.models import MessageDetail


class ActionMenu(ModalScreen[ActionTemplate | None]):
    """Modal overlay listing available action templates for selection.

    Triggered by pressing Space on a highlighted thread. The caller should
    use :func:`run_action_for_thread` which handles suspension and execution.

    Returns the chosen :class:`~phyrax.actions.engine.ActionTemplate`, or
    ``None`` if the user cancelled with Escape.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    CSS_PATH = "action_menu.tcss"

    def __init__(self) -> None:
        super().__init__()
        self._actions: list[ActionTemplate] = []

    def compose(self) -> ComposeResult:
        self._actions = list_actions()
        with Vertical(id="action-panel"):
            yield Label("Select action (Escape to cancel)", id="title")
            if not self._actions:
                yield Label("No actions found in actions directory.")
            else:
                list_items = [
                    ListItem(
                        Label(f"{action.name}  \u2014  {action.description}"),
                    )
                    for action in self._actions
                ]
                yield ListView(*list_items, id="action-list")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Dismiss with the chosen ActionTemplate when Enter is pressed."""
        event.stop()
        try:
            lv = self.query_one("#action-list", ListView)
            idx = lv.index
        except Exception:
            return
        if idx is not None and 0 <= idx < len(self._actions):
            self.dismiss(self._actions[idx])

    def action_cancel(self) -> None:
        """Dismiss with None when Escape is pressed."""
        self.dismiss(None)


async def run_action_for_thread(
    app: App,  # type: ignore[type-arg]  # App is generic; caller provides concrete type
    message: MessageDetail,
    config: PhyraxConfig,
) -> None:
    """Push ActionMenu, await selection, then execute with app.suspend().

    Args:
        app: The running Textual application instance.
        message: The currently selected message to pass as the email payload.
        config: The loaded PhyraxConfig (provides ai.agent_command etc.).
    """
    template: ActionTemplate | None = await app.push_screen_wait(ActionMenu())
    if template is None:
        return

    with app.suspend():
        execute_action(template, message, config)
