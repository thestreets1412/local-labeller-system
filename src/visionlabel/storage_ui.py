"""Root-bound storage manager. No client-side filesystem operations."""

import json
import time
from typing import Any

import dearpygui.dearpygui as dpg

from .domain import Problem, uid
from .feedback import failure_text


def amount(size):
    return f"{size / 1024**3:.3f} GiB ({size:,} bytes)"


class StoragePanel:
    def __init__(self, app):
        self.app = app
        self.busy = False
        self.scope = None
        self.client = None
        self.preview = None
        self.apply_key = None
        self.policy: Any = None
        self.policy_preview = None
        self.policy_body = None
        self.report_id = None
        self.items = {}
        self.choices = {}
        self.offset = 0

    def build(self):
        with dpg.window(
            label="Storage usage",
            tag="storage_manager",
            show=False,
            width=940,
            height=720,
            pos=(60, 30),
            modal=True,
        ):
            dpg.add_text("Scope: configured service root only", tag="storage_scope", wrap=0)
            dpg.add_text("Only this root is scanned and managed. Assets are report-only.", wrap=0)
            dpg.add_text("", tag="storage_status", wrap=0)
            with dpg.child_window(height=-1, width=-1, border=False):
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Refresh usage", callback=lambda: self.refresh())
                    dpg.add_button(
                        label="Inspect assets / create report", callback=lambda: self.make_report()
                    )
                    dpg.add_button(label="Open report", callback=lambda: self.open_report())
                dpg.add_input_text(tag="storage_usage", multiline=True, readonly=True, width=-1, height=100)
                dpg.add_separator()
                dpg.add_button(label="Inspect and register legacy exports", callback=lambda: self.adopt())
                dpg.add_text("Cached export")
                dpg.add_combo([], tag="storage_picker", width=-1)
                dpg.add_button(label="Prepare selected snapshot again", callback=lambda: self.reprepare())
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Previous page", callback=lambda: self.page(-100))
                    dpg.add_button(label="Next page", callback=lambda: self.page(100))
                    dpg.add_button(label="Add selected", callback=lambda: self.add_selected())
                    dpg.add_button(label="Pin", callback=lambda: self.pin(True))
                    dpg.add_button(label="Unpin", callback=lambda: self.pin(False))
                dpg.add_text("Selected archive IDs (one per line)")
                dpg.add_input_text(
                    tag="storage_ids",
                    multiline=True,
                    width=-1,
                    height=65,
                )
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Preview cleanup", callback=lambda: self.preview_cleanup())
                    dpg.add_button(label="Apply reviewed cleanup", callback=lambda: self.apply_cleanup())
                dpg.add_separator()
                dpg.add_input_int(
                    label="Cache budget (GiB)",
                    default_value=4,
                    min_value=1,
                    min_clamped=True,
                    tag="storage_budget",
                    width=150,
                )
                dpg.add_input_int(
                    label="Maximum unused age (days)",
                    default_value=7,
                    min_value=1,
                    min_clamped=True,
                    tag="storage_age",
                    width=150,
                )
                dpg.add_checkbox(label="Enable automatic retention", tag="storage_auto", default_value=False)
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Preview retention policy", callback=lambda: self.preview_policy())
                    dpg.add_button(label="Apply reviewed policy", callback=lambda: self.apply_policy())
                dpg.add_text(
                    "Legacy exports remain protected until explicitly selected for cleanup. Pinned or active archives cannot be removed.",
                    wrap=0,
                )
                dpg.add_input_text(tag="storage_result", multiline=True, readonly=True, width=-1, height=240)

    def status(self, message):
        dpg.set_value("storage_status", message)

    def ready(self):
        client = getattr(self.app, "client", None)
        if not client or not getattr(client, "user", None):
            self.status("Sign in as a service administrator, then refresh Storage usage.")
            return False
        if self.busy:
            self.status("A storage task is running. Wait for it to finish, then try again.")
            return False
        if self.client is not client:
            self.client = client
            self.scope = self.preview = self.policy_preview = self.report_id = None
        return True

    def run(self, work, done):
        if not self.ready():
            return
        client = self.client
        self.busy = True
        self.status("Working inside the configured root...")

        def success(result):
            self.busy = False
            if self.app.client is not client:
                self.scope = self.preview = self.policy_preview = None
                self.status("Connection changed. Refresh storage before continuing.")
                return
            done(result)

        def failed(exc):
            self.busy = False
            self.status(failure_text(exc, "Refresh Storage usage, check the reported issue, then try again."))

        self.app.submit(lambda: work(client), success, failed)

    def show(self):
        if dpg.does_item_exist("project_manager"):
            dpg.hide_item("project_manager")
        dpg.set_frame_callback(dpg.get_frame_count() + 2, lambda: dpg.show_item("storage_manager"))
        self.refresh()

    def refresh(self):
        def work(client):
            return client.request("GET", "/storage/usage", timeout=1200), client.request(
                "GET", f"/storage/export-cache?offset={self.offset}"
            )

        def done(pair):
            usage, listing = pair
            self.scope = listing["root_identity"]
            self.policy = listing["policy"]
            self.preview = self.policy_preview = None
            self.items = {a["id"]: a for a in listing["items"]}
            self.choices = {
                f"{a['id']} | {amount(a['bytes'])} | {a['state']}"
                + (" | pinned" if a["pinned"] else "")
                + (" | legacy protected" if a["legacy_protected"] else ""): a["id"]
                for a in listing["items"]
            }
            dpg.set_value("storage_scope", "Scope: " + listing["root"])
            dpg.set_value(
                "storage_usage",
                "\n".join(
                    f"{c['name']}: {amount(c['bytes'])}; {c['count']:,} files" for c in usage["categories"]
                )
                + f"\nCache accounted: {amount(listing['cached_bytes'])} / budget {amount(self.policy['max_bytes'])}",
            )
            dpg.configure_item("storage_picker", items=list(self.choices))
            dpg.set_value("storage_picker", next(iter(self.choices), ""))
            dpg.set_value("storage_budget", max(1, self.policy["max_bytes"] // 1024**3))
            dpg.set_value("storage_age", self.policy["max_age_days"])
            dpg.set_value("storage_auto", bool(self.policy["automatic_enabled"]))
            dpg.set_value(
                "storage_result",
                "\n".join(
                    usage["warnings"]
                    + (["Retention: " + listing["last_error"]] if listing.get("last_error") else [])
                )
                or "No scan warnings. Choose an archive and preview cleanup. Assets are report-only.",
            )
            self.status(
                f"Storage refreshed. Archives {self.offset + 1 if self.items else 0}–{self.offset + len(self.items)} of {listing['count']}."
            )

        self.run(work, done)

    def page(self, delta):
        self.offset = max(0, self.offset + delta)
        self.refresh()

    def selected(self):
        ident = self.choices.get(dpg.get_value("storage_picker"))
        if not ident:
            self.status("No archive selected. Refresh and choose a cached export first.")
        return ident

    def add_selected(self):
        ident = self.selected()
        if ident:
            ids = list(dict.fromkeys((dpg.get_value("storage_ids") + "\n" + ident).split()))
            dpg.set_value("storage_ids", "\n".join(ids))
            self.preview = None
            self.status("Archive added. Preview cleanup before applying.")

    def render(self, result):
        dpg.set_value("storage_result", json.dumps(result, indent=2, ensure_ascii=False))
        self.status("Task completed. Review the result below.")

    def adopt(self):
        self.run(lambda c: c.request("POST", "/storage/export-cache/adopt", {}, timeout=1200), self.render)

    def reprepare(self):
        ident = self.selected()
        if not ident or not self.ready():
            return
        project = self.app.project
        if not project or project["id"] != self.items[ident]["project_id"]:
            self.status(
                "This archive belongs to another project. Open its project, then select the archive again."
            )
            return
        if self.app.exports.busy:
            self.status("An export task is running. Wait for it to finish before preparing this snapshot.")
            return
        key = uid()

        def work(client):
            job_id = client.request("POST", f"/working-exports/{ident}/reprepare", {}, key=key)["job_id"]
            while not self.app.exit_requested:
                job = client.request("GET", f"/jobs/{job_id}")
                if job["state"] == "failed":
                    raise Problem(job["error"]["code"], job["error"]["message"])
                if job["state"] == "succeeded":
                    return {"job_id": job_id, "result": job["result"], "client": client}
                time.sleep(0.5)
            raise Problem("CANCELLED", "Desktop closed. Reopen storage to inspect the prepared job.")

        def done(prepared):
            if not self.app.project or self.app.project["id"] != project["id"]:
                self.status("Project changed. Reopen the original project to use its export.")
                return
            exports = self.app.exports
            exports.open(show=False)
            exports.prepared = prepared
            exports.set_busy(False)
            dpg.set_value("export_report", json.dumps(prepared["result"], indent=2))
            dpg.set_value(
                "export_status",
                "Prepared from the saved snapshot using the current converter. Review the result, then Save dataset.",
            )
            dpg.hide_item("storage_manager")
            exports.show_after_modal_closes("export_dialog")

        self.run(work, done)

    def pin(self, value):
        ident = self.selected()
        if ident:
            self.run(
                lambda c: c.request("PATCH", f"/storage/export-cache/{ident}", {"pinned": value}), self.render
            )

    def preview_cleanup(self):
        ids = dpg.get_value("storage_ids").split()
        if not ids:
            self.status("No archives selected. Add an archive to the selection, then preview cleanup.")
            return

        def done(result):
            self.preview = result
            self.apply_key = uid()
            self.render(result)
            self.status(
                f"Preview: {amount(result['reclaimable_bytes'])} eligible. Root: {result['root']}. Review before applying."
            )

        self.run(
            lambda c: c.request("POST", "/storage/export-cache/preview", {"artifact_ids": ids}, timeout=1200),
            done,
        )

    def apply_cleanup(self):
        if not self.ready():
            return
        if not self.preview or self.preview["root_identity"] != self.scope:
            self.status("No valid cleanup preview for this root. Refresh and preview cleanup first.")
            return
        token, key = self.preview["token"], self.apply_key

        def done(result):
            self.preview = None
            self.render(result)
            self.status(
                f"Cleanup finished: {amount(result['deleted_bytes'])} removed. Assets and history were retained."
            )

        self.run(
            lambda c: c.request(
                "POST", "/storage/export-cache/apply", {"token": token}, key=key, timeout=1200
            ),
            done,
        )

    def policy_values(self):
        return {
            "expected_generation": self.policy["generation"],
            "max_bytes": dpg.get_value("storage_budget") * 1024**3,
            "max_age_days": dpg.get_value("storage_age"),
            "automatic_enabled": dpg.get_value("storage_auto"),
        }

    def preview_policy(self):
        if not self.policy:
            self.status("No policy loaded. Refresh Storage usage first.")
            return
        body = self.policy_values()

        def done(result):
            self.policy_preview, self.policy_body = result, body
            self.render(result)

        self.run(lambda c: c.request("POST", "/storage/policy/preview", body), done)

    def apply_policy(self):
        if not self.ready():
            return
        if not self.policy_preview or self.policy_values() != self.policy_body:
            self.status("Policy changed or has no preview. Preview retention policy first.")
            return
        body = self.policy_body | {"preview_token": self.policy_preview["token"]}

        def done(result):
            self.policy, self.policy_preview = result, None
            self.render(result)

        self.run(lambda c: c.request("PATCH", "/storage/policy", body), done)

    def make_report(self):
        def done(result):
            self.report_id = result["id"]
            self.render(result)
            self.status("Report saved inside the configured root. Use Open report to inspect it here.")

        self.run(lambda c: c.request("POST", "/storage/reports?deep=true", {}, timeout=1200), done)

    def open_report(self):
        if not self.report_id:
            self.status("No report created in this session. Choose Inspect assets / create report first.")
            return
        self.run(lambda c: c.request("GET", f"/storage/reports/{self.report_id}"), self.render)
