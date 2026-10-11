"""Working review controls, queues and per-user resume cursor."""

from typing import Any

import dearpygui.dearpygui as dpg

from .domain import Problem, uid


class ReviewPanel:
    def __init__(self, app):
        self.app = app
        self.busy = False
        self.pending = None
        self.overview: dict[str, Any] = {"total": 0, "image_ids": [], "counts": {}}
        self.generation = 0

    def build(self):
        with dpg.window(
            tag="review_reject", label="Reject annotation", modal=True, show=False, width=470, height=220
        ):
            dpg.add_combo(
                ["Wrong class", "Missing object", "Box needs adjustment", "Other"],
                default_value="Wrong class",
                tag="review_reason",
                width=300,
            )
            dpg.add_input_text(label="Details", tag="review_comment", width=350)
            dpg.add_button(label="Reject and save reason", callback=lambda: self.reject())
            dpg.add_button(label="Cancel", callback=lambda: dpg.hide_item("review_reject"))
        with dpg.window(
            tag="review_settings", label="Review settings", modal=True, show=False, width=500, height=220
        ):
            dpg.add_checkbox(label="Allow self-review for this project", tag="review_self")
            dpg.add_input_text(label="Reason (required)", tag="review_setting_reason", width=320)
            dpg.add_button(label="Save setting", callback=self.save_setting)
            dpg.add_button(label="Cancel", callback=lambda: dpg.hide_item("review_settings"))
        with dpg.window(tag="review_history", label="Review history", show=False, width=700, height=450):
            dpg.add_input_text(tag="review_history_text", multiline=True, readonly=True, width=-1, height=-1)
        self.app.text_inputs.extend(["review_comment", "review_setting_reason"])

    def refresh(self):
        app = self.app
        if not app.project:
            return
        pid, client = app.project["id"], app.client
        self.generation += 1
        generation = self.generation

        def done(data):
            if (
                app.client is client
                and app.project
                and app.project["id"] == pid
                and generation == self.generation
            ):
                self.overview = data
                self.position()

        app.submit(lambda: client.request("GET", f"/projects/{pid}/review-overview"), done)

    def position(self):
        app = self.app
        ids = self.overview["image_ids"]
        iid = app.image["id"] if app.image else None
        ordinal = ids.index(iid) + 1 if iid in ids else 0
        dpg.set_viewport_title(f"VisionLabel - Annotation workspace: [{ordinal}/{self.overview['total']}]")
        counts = self.overview["counts"]
        dpg.set_value(
            "review_counts",
            " / ".join(
                f"{name}: {counts.get(state, 0)}"
                for name, state in [
                    ("PASS", "REVIEWED_PASS"),
                    ("NG", "REVIEWED_NG"),
                    ("Pending", "IN_PROGRESS"),
                    ("Unlabeled", "UNLABELED"),
                ]
            ),
        )
        queue_ids = [i["id"] for i in app.images if not i.get("pinned_outside_queue")]
        number = queue_ids.index(iid) + 1 if iid in queue_ids else 0
        dpg.set_value(
            "image_count", f"Queue: {number}/{len(queue_ids)} | Project: {ordinal}/{self.overview['total']}"
        )

    def remember(self):
        app = self.app
        if app.store and app.project and app.image:
            app.store.save_review_cursor(
                app.project["id"], dpg.get_value("filter"), dpg.get_value("search"), app.image["id"]
            )

    def resume(self):
        app = self.app
        if not app.store or not app.project:
            return
        iid = app.store.review_cursor(app.project["id"], dpg.get_value("filter"), dpg.get_value("search"))
        ids = [i["id"] for i in app.images if not i.get("pinned_outside_queue")]
        # A reviewed cursor may have left the pending queue. Continue after its
        # stable project position, without treating skipped items as reviewed.
        if iid not in ids:
            order = self.overview["image_ids"]
            after = order.index(iid) if iid in order else -1
            candidates = set(ids)
            iid = next((x for x in order[after + 1 :] if x in candidates), ids[0] if ids else None)
        if iid:
            app.guard(lambda: app.open_image(iid))

    def eligible(self):
        app = self.app
        return bool(
            app.project
            and app.project.get("can_review")
            and app.head
            and app.head["status"] == "IN_PROGRESS"
            and not app.blocked
            and not app.busy
            and not self.busy
            and not app.canvas.gesture
        )

    def request(self, decision):
        if not self.eligible():
            self.app.message(
                "Review requires a saved IN_PROGRESS image and reviewer or maintainer permission."
            )
            return
        if decision == "reject":
            dpg.show_item("review_reject")
        else:
            self.app.guard(lambda: self.decide("accept", ""))

    def reject(self):
        reason, detail = dpg.get_value("review_reason"), dpg.get_value("review_comment").strip()
        if reason == "Other" and not detail:
            self.app.message("Enter a rejection reason.")
            return
        dpg.hide_item("review_reject")
        self.app.guard(
            lambda: self.decide(
                "reject", detail if reason == "Other" else reason + (": " + detail if detail else "")
            )
        )

    def decide(self, decision, comment):
        app = self.app
        if not self.eligible() or app.editor.dirty:
            return
        iid, client, head = app.image["id"], app.client, dict(app.head)
        body = {
            "expected_revision": head["revision"],
            "expected_state_revision": head["state_revision"],
            "annotation_sha256": head["annotation_sha256"],
            "decision": decision,
            "comment": comment,
        }
        if not self.pending or self.pending["image_id"] != iid or self.pending["body"] != body:
            self.pending = {"image_id": iid, "body": body, "key": uid(), "claim_key": uid(), "claim": None}
        pending, old_claim = self.pending, app.claim
        self.busy = True
        app.claim = None
        ids = [i["id"] for i in app.images]
        index = ids.index(iid) if iid in ids else -1
        target = next((i["id"] for i in app.images[index + 1 :] if i["status"] == "IN_PROGRESS"), None)
        advance = dpg.get_value("review_advance")
        app.message("Saving review...")

        def work():
            if not pending["claim"]:
                if old_claim and old_claim.get("mode") == "review":
                    pending["claim"] = old_claim
                else:
                    if old_claim:
                        client.request("DELETE", f"/images/{iid}/claim", claim=old_claim)
                    pending["claim"] = client.request(
                        "POST",
                        f"/images/{iid}/claim",
                        {"mode": "review", "client_instance_id": client.instance},
                        key=pending["claim_key"],
                    )
            return client.request(
                "POST", f"/images/{iid}/reviews", body, key=pending["key"], claim=pending["claim"]
            )

        def done(result):
            self.busy = False
            self.pending = None
            if not app.image or app.image["id"] != iid or app.client is not client:
                return
            app.image_query_generation += 1
            app.head.update(result)
            app.image["status"] = result["status"]
            for image in app.images:
                if image["id"] == iid:
                    image["status"] = result["status"]
            self.refresh()
            app.populate_images()
            app.message(result["status"] + (": " + comment if comment else ""))
            if advance and target:
                app.open_image(target)
            else:
                app.open_image(
                    iid,
                    on_loaded=lambda: app.message(
                        "Review saved. No further pending image in this queue."
                        if advance
                        else "Review saved."
                    ),
                )

        def failed(exc):
            self.busy = False
            app.claim = pending["claim"]
            if isinstance(exc, Problem) and exc.code not in ("DISCONNECTED", "SERVER_STOPPING"):
                self.pending = None
            app.error(exc)

        app.submit(work, done, failed)

    def show_history(self):
        if not self.app.image:
            return
        iid = self.app.image["id"]

        def done(result):
            if not self.app.image or self.app.image["id"] != iid:
                return
            lines = ["Review history", ""]
            for item in result["items"]:
                state = "PASS" if item["decision"] == "accept" else "NG"
                applicability = "Current" if item["applicable"] else "Superseded"
                lines.append(f"{state} | Revision {item['annotation_revision']} | {applicability}")
                lines.append(f"{item['reviewer_name']} | {item['created_at']} (UTC)")
                if item["comment"]:
                    lines.append("Reason: " + item["comment"])
                lines.append("")
            if not result["items"]:
                lines.append("This image has no review decisions yet.")
            dpg.set_value("review_history_text", "\n".join(lines))
            dpg.show_item("review_history")

        self.app.submit(lambda: self.app.client.request("GET", f"/images/{iid}/reviews"), done)

    def show_settings(self):
        if self.app.project and self.app.project.get("can_manage_members"):
            dpg.set_value("review_self", bool(self.app.project["allow_self_review"]))
            dpg.show_item("review_settings")

    def save_setting(self):
        app = self.app
        if self.busy or not app.project:
            return
        body = {
            "expected_project_revision": app.project["project_revision"],
            "allow_self_review": dpg.get_value("review_self"),
            "reason": dpg.get_value("review_setting_reason"),
        }
        pid = app.project["id"]
        self.busy = True

        def done(result):
            self.busy = False
            if app.project and app.project["id"] == pid:
                app.project.update(result)
            dpg.hide_item("review_settings")

        def failed(exc):
            self.busy = False
            app.error(exc)

        app.submit(
            lambda: app.client.request("PUT", f"/projects/{pid}/review-settings", body, key=uid()),
            done,
            failed,
        )
