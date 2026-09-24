from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from app.config import DATA_DIR

CHECKPOINT_DB = DATA_DIR / "checkpoints.db"


@contextmanager
def sqlite_checkpointer(path: Path = CHECKPOINT_DB) -> Iterator[SqliteSaver]:
    """Persist conversations per thread_id so a chat can be resumed later."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(path)) as saver:
        yield saver
