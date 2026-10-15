"""Explicit project removal, separate from the annotation Delete shortcut."""

import dearpygui.dearpygui as dpg

from .domain import canonical, empty_content, uid


class ImageDeletePanel:
    def __init__(self, app):
        self.app = app
        self.pending = None
        self.retry = None

    def build(self):
        with dpg.window(
            label="Delete image permanently?",
            tag="delete_image_dialog",
            modal=True,
            show=False,
            no_close=True,
            width=510,
            autosize=True,
        ):
            dpg.add_text("", tag="delete_image_message", wrap=480)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Yes, delete image", callback=self.confirm)
                dpg.add_button(label="No, keep image", callback=self.cancel)

    def request(self):
        app = self.app
        if app.busy or app.saving or app.review.busy or app.blocked or not app.image or not app.head:
            return
        if not app.project or not app.project.get("can_manage_members") or app.project.get("archived"):
            app.message("Maintainer permission is required to delete images.")
            return
        self.pending = {
            "image_id": app.image["id"],
            "body": {
                "expected_revision": app.head["revision"],
                "expected_state_revision": app.head["state_revision"],
            },
            "claim": app.claim,
            "key": uid(),
        }
        if self.retry and all(self.retry[k] == self.pending[k] for k in ("image_id", "body")):
            self.pending = self.retry
        app.busy = True
        dpg.set_value(
            "delete_image_message",
            f"Delete {app.image['display_filename']} from this project?\n\n"
            "This cannot be undone in the application. Unsaved edits will be discarded. "
            "The image will be excluded from future working exports. "
            "Historical evidence and existing snapshots retain their files. "
            "Original files in the import folder are not deleted.",
        )
        dpg.show_item("delete_image_dialog")

    def cancel(self):
        self.pending = None
        self.app.busy = False
        dpg.hide_item("delete_image_dialog")

    def confirm(self):
        if not self.pending:
            return
        app, pending = self.app, self.pending
        self.pending = None  # Double clicks cannot dispatch a second mutation.
        dpg.hide_item("delete_image_dialog")
        app.message("Deleting image...")
        client, store = app.client, app.store

        def success(_):
            self.retry = None
            app.image_query_generation += 1
            app.images = [i for i in app.images if i["id"] != pending["image_id"]]
            app.image = app.claim = app.head = app.pending_save = None
            app.canvas.cancel()
            app.editor.load(empty_content())
            app.last_content = canonical(app.editor.content)
            dpg.delete_item("canvas", children_only=True)
            if app.texture:
                dpg.delete_item(app.texture)
                app.texture = None
            app.busy = False
            dpg.set_value("image_title", "Open an image to begin")
            app.populate_images()
            app.render()
            app.refresh_images()
            app.message("Image deleted from the project. Historical evidence is retained.")
            try:
                if store:
                    store.remove_draft(pending["image_id"])
            except OSError:
                app.message("Image deleted. Its local recovery draft could not be removed.")

        def failure(error):
            # A transport error can follow a successful server commit. Keep the
            # original key so the next explicit confirmation resolves that result.
            self.retry = pending
            app.busy = False
            app.error(error)

        app.submit(
            lambda: client.request(
                "DELETE",
                f"/images/{pending['image_id']}",
                pending["body"],
                claim=pending["claim"],
                key=pending["key"],
            ),
            success,
            failure,
        )
