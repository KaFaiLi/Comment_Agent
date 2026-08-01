"""Thread-safe Streamlit status callbacks."""

import threading
from collections.abc import Callable
from typing import Any

from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx


def make_status_callback(placeholder: Any) -> Callable[[str], None]:
    script_context = get_script_run_ctx()

    def update_status(message: str) -> None:
        add_script_run_ctx(threading.current_thread(), script_context)
        placeholder.info(message)

    return update_status
