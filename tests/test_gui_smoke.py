"""End-to-end smoke test for the desktop front end.

This is the only test that builds the real window. It is what turns CI into
a meaningful check on the GUI: everything else can pass while the app still
crashes on launch because of a renamed customtkinter argument, a missing
theme asset, or a view that raises during construction.

It drives the whole interface against the in-memory mock device, so it
needs no Bluetooth hardware. Headless environments where Tk cannot
initialise skip instead of failing — the point is to catch real breakage,
not to make the suite environment-sensitive.

Message boxes are stubbed out for the duration: a real ``showerror`` on a
CI runner would block forever waiting for a click.
"""

import os
import sys
import tempfile
import time

import pytest

pytest.importorskip("tkinter", reason="tkinter is not available")
pytest.importorskip("customtkinter", reason="customtkinter is not available")

from gui import views as views_pkg          # noqa: E402
from gui.app import BoseCtlApp              # noqa: E402
from gui.settings import Settings           # noqa: E402

#: How long to let the Tk event loop run while waiting for worker results.
PUMP_SECONDS = 4.0


class _FakeBox:
    """Records dialog calls instead of showing them."""

    def __init__(self):
        self.errors = []
        self.infos = []
        self.warnings = []
        self.asked = []

    def showerror(self, title, message, **kwargs):
        self.errors.append((title, message))

    def showinfo(self, title, message, **kwargs):
        self.infos.append((title, message))

    def showwarning(self, title, message, **kwargs):
        self.warnings.append((title, message))

    def askyesno(self, title, message, **kwargs):
        self.asked.append((title, message))
        return False


def _pump(app, seconds=PUMP_SECONDS):
    """Run the Tk loop until the worker is idle (or the budget expires).

    The worker delivers results through ``widget.after``, so ``update()``
    has to be called repeatedly for anything to happen.
    """
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.update()
        if not app.worker.busy and time.time() > deadline - seconds + 0.4:
            # At least a few ticks after the queue drained, so the delivered
            # callbacks have run too.
            app.update()
            return
        time.sleep(0.02)


@pytest.fixture
def box(monkeypatch):
    fake = _FakeBox()
    import gui.app as app_module
    for name in ("showerror", "showinfo", "showwarning", "askyesno"):
        monkeypatch.setattr(app_module.mb, name, getattr(fake, name))
    return fake


@pytest.fixture
def app(box):
    """A real window backed by a throwaway settings file."""
    config = os.path.join(tempfile.mkdtemp(prefix="bosectl-test-"), "settings.json")
    settings = Settings(path=config)
    settings.update({"auto_connect": False, "last_view": "audio",
                     "appearance": "light", "geometry": ""})
    try:
        instance = BoseCtlApp(settings=settings)
    except Exception as exc:  # pragma: no cover - depends on the runner
        pytest.skip("Tk could not initialise in this environment: %s" % exc)
    instance.update()
    try:
        yield instance
    finally:
        try:
            instance.worker.stop()
        except Exception:
            pass
        try:
            instance.destroy()
        except Exception:
            pass


def _connect_mock(app, box):
    app.connect(mock=True)
    _pump(app)
    assert not box.errors, "connection reported errors: %r" % box.errors
    assert app.dev is not None


# ── construction ─────────────────────────────────────────────────────────────

def test_window_builds_with_every_view(app):
    assert app.title() == "BoseCtl for Windows"
    assert set(app._views) == {key for key, _ in views_pkg.VIEWS}
    assert app._current == "connect"


def test_views_are_laid_out_in_navigation_order(app):
    keys = [key for key, _ in views_pkg.VIEWS]
    assert keys[0] == "connect"
    assert keys == ["connect", "audio", "modes", "device", "advanced", "about"]


def test_device_views_start_disabled(app):
    for key, view_cls in views_pkg.VIEWS:
        if view_cls.requires_device:
            assert str(app._nav_buttons[key].cget("state")) == "disabled"


def test_sidebar_exposes_disconnect(app):
    assert str(app._disconnect_button.cget("state")) == "disabled"


# ── connecting to the simulated device ───────────────────────────────────────

def test_demo_mode_connects_and_unlocks_the_ui(app, box):
    _connect_mock(app, box)
    assert app.caps.name
    for key, view_cls in views_pkg.VIEWS:
        if view_cls.requires_device:
            assert str(app._nav_buttons[key].cget("state")) == "normal"
    assert str(app._disconnect_button.cget("state")) == "normal"


def test_status_tiles_are_populated(app, box):
    _connect_mock(app, box)
    app.refresh_status(manual=True)
    _pump(app)
    assert "%" in app.tile_battery.value_text()
    assert app.tile_mode.value_text() not in ("", "—")
    assert "/" in app.tile_noise.value_text()


@pytest.mark.parametrize("key", [key for key, _ in views_pkg.VIEWS])
def test_every_view_can_be_shown(app, box, key):
    """Visiting each page must not raise, including its first-show work.

    ``select_view`` swallows hook exceptions by design, so the assertion is
    on the view instance actually having been built and raised to the top.
    """
    _connect_mock(app, box)
    app.select_view(key)
    _pump(app, seconds=2.0)
    assert app._current == key
    assert key in app._shown_once
    assert not box.errors, "view %s raised: %r" % (key, box.errors)


def test_every_view_refreshes_from_a_status_snapshot(app, box):
    _connect_mock(app, box)
    status = app.dev.status()
    for view in app._views.values():
        view.refresh(status)          # must not raise
    assert not box.errors


# ── writing through the full stack ───────────────────────────────────────────

def test_cnc_write_roundtrips_through_the_worker(app, box):
    _connect_mock(app, box)
    app.call(app.dev.set_cnc, 7, refresh=False)
    _pump(app)
    assert not box.errors

    result = {}
    app.read(app.dev.cnc, on_ok=lambda value: result.setdefault("cnc", value))
    _pump(app)
    assert result.get("cnc", (None, None))[0] == 7


def test_eq_write_roundtrips(app, box):
    _connect_mock(app, box)
    app.call(app.dev.set_eq, 3, 0, -2, refresh=False)
    _pump(app)
    bands = {b.name: b.current for b in app.dev.eq()}
    assert bands == {"Bass": 3, "Mid": 0, "Treble": -2}


def test_mode_switch_roundtrips(app, box):
    _connect_mock(app, box)
    app.call(app.dev.set_mode, "aware", refresh=False)
    _pump(app)
    assert app.dev.mode() == "aware"


# ── chrome ───────────────────────────────────────────────────────────────────

def test_appearance_toggle_rebuilds_without_losing_the_device(app, box):
    _connect_mock(app, box)
    app.select_view("audio")
    app.toggle_appearance()
    app.update()
    assert app.theme.appearance == "dark"
    assert app.dev is not None
    assert set(app._views) == {key for key, _ in views_pkg.VIEWS}
    app.toggle_appearance()
    app.update()
    assert app.theme.appearance == "light"


def test_switching_to_a_device_view_without_a_device_warns(app, box):
    app.select_view("audio")
    assert app._current == "connect"
    assert app._status_text.cget("text")


def test_disconnect_returns_to_the_connect_page(app, box):
    _connect_mock(app, box)
    app.disconnect()
    _pump(app, seconds=2.0)
    assert app.dev is None
    assert app._current == "connect"
    for key, view_cls in views_pkg.VIEWS:
        if view_cls.requires_device:
            assert str(app._nav_buttons[key].cget("state")) == "disabled"


def test_worker_serialises_results_and_goes_idle(app, box):
    _connect_mock(app, box)
    seen = []
    for level in (1, 2, 3):
        app.read(app.dev.set_cnc, level, on_ok=lambda _r, l=level: seen.append(l))
    _pump(app)
    assert seen == [1, 2, 3]
    assert app.worker.busy is False


def test_shortcuts_are_bound(app):
    # A Windows user will try these unprompted; a missing binding is a bug.
    for sequence in ("<F5>", "<Control-r>", "<Control-q>"):
        assert app.bind(sequence)
