"""Portable direct-mode fixtures and narrowly scoped Windows cleanup fix."""
import os
from pathlib import Path
import tempfile

import pytest


@pytest.fixture(autouse=True)
def windows_message_cleanup(monkeypatch):
    """Defer unlink of the SDK stdin file until the VM releases its handle.

    Fresh genlayer-test 0.29.2 wheels unlink an open fd-0 backing file.
    Catch only Windows sharing violations from this loader operation;
    all other failures still propagate. No installed package is edited.
    """
    if os.name != "nt":
        yield
        return
    from gltest.direct import loader
    original = loader._inject_message_to_fd0
    deferred = []
    temp_root = Path(tempfile.gettempdir()).resolve()

    def inject(vm):
        try:
            return original(vm)
        except PermissionError as error:
            path = Path(error.filename).resolve() if error.filename else None
            if (getattr(error, "winerror", None) != 32 or path is None
                    or path.parent != temp_root or not path.name.startswith("tmp")):
                raise
            deferred.append(path)

    monkeypatch.setattr(loader, "_inject_message_to_fd0", inject)
    yield
    for path in deferred:
        path.unlink(missing_ok=True)
