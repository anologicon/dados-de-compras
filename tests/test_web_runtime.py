import pytest

import compras_crawler.web.runtime as runtime
from compras_crawler.web.runtime import SharedThrottle, file_lock
from compras_crawler.web.store import AppStore


def test_throttle_is_shared_and_cooldown_affects_other_workers(tmp_path, monkeypatch):
    store = AppStore(tmp_path)
    store.init_schema()
    clock = [100.0]
    monkeypatch.setattr(runtime.time, "time", lambda: clock[0])

    class Control:
        def check(self):
            pass
        def wait(self, seconds):
            clock[0] += seconds

    one = SharedThrottle(store, Control())
    two = SharedThrottle(AppStore(tmp_path), Control())
    one.wait()
    two.wait()
    assert clock[0] == pytest.approx(101)
    one.pause_for(60)
    two.wait()
    assert clock[0] == pytest.approx(161)


def test_workspace_lock_fences_second_server(tmp_path):
    with file_lock(tmp_path / "service.lock"):
        with pytest.raises(RuntimeError, match="já está em uso"):
            with file_lock(tmp_path / "service.lock"):
                pass
