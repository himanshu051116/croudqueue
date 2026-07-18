import sys

from backend.app.runtime import configure_event_loop_policy

configure_event_loop_policy()

import uvicorn  # noqa: E402

if __name__ == "__main__":
    loop = (
        "backend.app.runtime:selector_event_loop" if sys.platform == "win32" else "auto"
    )
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8001, loop=loop)
