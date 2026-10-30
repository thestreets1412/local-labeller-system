from types import SimpleNamespace

import dearpygui.dearpygui as dpg


def test_storage_shows_scope_and_login_feedback():
    from visionlabel.storage_ui import StoragePanel

    dpg.create_context()
    try:
        app = SimpleNamespace(client=None)
        panel = StoragePanel(app)
        panel.build()
        panel.show()
        assert "Sign in" in dpg.get_value("storage_status")
        assert "root" in dpg.get_value("storage_scope")
    finally:
        dpg.destroy_context()


def test_connection_change_invalidates_storage_preview():
    from visionlabel.storage_ui import StoragePanel

    dpg.create_context()
    try:
        app = SimpleNamespace(client=SimpleNamespace(user={"id": "admin"}))
        panel = StoragePanel(app)
        panel.build()
        assert panel.ready()
        panel.preview = {"token": "old"}
        panel.scope = "old-root"
        app.client = SimpleNamespace(user={"id": "admin"})
        assert panel.ready()
        assert panel.scope is None and panel.preview is None
    finally:
        dpg.destroy_context()
