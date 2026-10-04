"""Account and project membership administration through the public API."""

import dearpygui.dearpygui as dpg

from .domain import Problem, uid


class TeamPanel:
    def __init__(self, desktop):
        self.app = desktop
        self.busy = False
        self.pending = None
        self.users = {}
        self.member_choices = {}
        self.selected_user = None
        self.project = None

    def build(self):
        with dpg.window(
            label="Team & users",
            tag="team",
            modal=True,
            show=False,
            no_close=True,
            width=820,
            height=650,
            pos=(230, 90),
        ):
            dpg.add_text("Loading...", tag="team_status", wrap=765)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Refresh", callback=lambda: self.refresh())
                dpg.add_button(
                    label="Retry last request", tag="team_retry", enabled=False, callback=lambda: self.retry()
                )
                dpg.add_button(label="Close", callback=lambda: self.close())
            with dpg.tab_bar():
                with dpg.tab(label="Project members"):
                    dpg.add_text("Choose a project in the workspace first.", tag="team_project")
                    dpg.add_text("1. Choose a user    2. Choose a role    3. Add / update role")
                    dpg.add_combo(
                        [], label="User", tag="team_member_picker", width=430, callback=self.pick_member
                    )
                    with dpg.child_window(tag="team_members", height=160):
                        pass
                    dpg.add_input_text(label="User ID", tag="team_member_id", width=430)
                    dpg.add_text(
                        "Administrators can choose any enabled account above. Maintainers can also paste a supplied user ID.",
                        wrap=740,
                    )
                    dpg.add_combo(
                        ["viewer", "annotator", "reviewer", "maintainer"],
                        default_value="annotator",
                        label="Project role",
                        tag="team_role",
                        width=240,
                    )
                    dpg.add_text(
                        "Viewer: read only. Annotator: edit. Reviewer: edit and review.\nMaintainer: manage this project and its members.",
                        wrap=740,
                    )
                    with dpg.group(horizontal=True):
                        dpg.add_button(
                            label="Add / update role",
                            tag="team_set_role",
                            callback=lambda: self.member(False),
                        )
                        dpg.add_button(
                            label="Remove from project",
                            tag="team_remove_role",
                            callback=lambda: self.member(True),
                        )
                    dpg.add_text("Role changes revoke the user's current leases in this project.", wrap=740)
                with dpg.tab(label="Accounts (administrator)", tag="team_accounts"):
                    dpg.add_combo([], label="Account", tag="team_user", width=470, callback=self.select_user)
                    dpg.add_input_text(label="User ID", tag="team_user_id", readonly=True, width=430)
                    dpg.add_input_text(label="Username (new account)", tag="team_username", width=350)
                    dpg.add_input_text(label="Display name", tag="team_display", width=350)
                    dpg.add_input_text(
                        label="Password (12+ characters)", tag="team_password", password=True, width=350
                    )
                    dpg.add_text(
                        "Leave password empty to keep it when updating. Resetting it revokes sessions.",
                        wrap=740,
                    )
                    dpg.add_checkbox(label="Account disabled", tag="team_disabled")
                    dpg.add_checkbox(label="Revoke all sessions and editing leases", tag="team_revoke")
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="New account form", callback=lambda: self.clear_user())
                        dpg.add_button(label="Create account", callback=lambda: self.create_user())
                        dpg.add_button(label="Update selected account", callback=lambda: self.update_user())
                        dpg.add_button(
                            label="Use selected account for project role", callback=lambda: self.use_user()
                        )
                    dpg.add_text(
                        "New accounts have no project access until a project role is assigned.", wrap=740
                    )

    def message(self, text):
        dpg.set_value("team_status", text)

    def open(self):
        if not self.app.client.user:
            self.app.message("Sign in before opening Team & users.")
            return
        dpg.show_item("team")
        self.refresh()

    def close(self):
        if self.busy:
            self.message("Wait for the current request to finish.")
            return
        self.pending = None
        dpg.set_value("team_password", "")
        dpg.hide_item("team")

    def refresh(self):
        if self.busy:
            return
        self.busy = True
        self.message("Loading accounts and project membership...")
        client = self.app.client
        project_id = self.app.project["id"] if self.app.project else None

        def work():
            me = client.request("GET", "/me")
            users = client.list_all("/users") if me["is_admin"] else []
            project = client.request("GET", f"/projects/{project_id}") if project_id else None
            members = client.request("GET", f"/projects/{project_id}/members") if project_id else None
            return me, users, project, members

        def done(result):
            self.busy = False
            me, users, self.project, members = result
            self.users = {f"{u['username']} ({u['display_name']})": u for u in users}
            candidates = users if me["is_admin"] else (members["items"] if members else [])
            self.member_choices = {
                f"{u['username']} ({u['display_name']})": u for u in candidates if not u["disabled"]
            }
            dpg.configure_item("team_member_picker", items=list(self.member_choices))
            current_id = dpg.get_value("team_member_id")
            dpg.set_value(
                "team_member_picker",
                next((label for label, u in self.member_choices.items() if u["id"] == current_id), ""),
            )
            dpg.configure_item("team_user", items=list(self.users))
            dpg.configure_item("team_accounts", show=bool(me["is_admin"]))
            self.clear_user()
            dpg.delete_item("team_members", children_only=True)
            manage = bool(self.project and self.project["can_manage_members"])
            for tag in ("team_set_role", "team_remove_role"):
                dpg.configure_item(tag, enabled=manage)
            if self.project:
                self.project["project_revision"] = members["project_revision"]
                if self.app.project and self.app.project["id"] == project_id:
                    self.app.project.update(
                        {k: self.project[k] for k in ("can_edit", "can_manage_members", "project_revision")}
                    )
                dpg.set_value(
                    "team_project",
                    f"{self.project['name']} / membership revision {members['project_revision']}",
                )
                for item in members["items"]:
                    dpg.add_selectable(
                        label=f"{item['username']} - {item['display_name']} - {item['role']}"
                        + (" (disabled)" if item["disabled"] else ""),
                        parent="team_members",
                        callback=self.select_member,
                        user_data=item,
                    )
            else:
                dpg.set_value("team_project", "Choose a project in the workspace first.")
            self.message(
                "Loaded. Only administrators manage accounts; project maintainers manage membership."
            )

        self.app.submit(work, done, self.failed)

    def failed(self, exc):
        self.busy = False
        self.message(
            exc.message if isinstance(exc, Problem) else "Request failed. Refresh before continuing."
        )
        retryable = bool(self.pending and isinstance(exc, Problem) and exc.status >= 500)
        dpg.configure_item("team_retry", enabled=retryable)
        if not retryable:
            self.pending = None

    def mutate(self, method, path, body):
        if self.busy:
            return
        self.pending = (self.app.client, method, path, body, uid())
        self.retry()

    def retry(self):
        if self.busy or not self.pending:
            return
        self.busy = True
        client, method, path, body, key = self.pending
        self.message("Saving...")
        dpg.configure_item("team_retry", enabled=False)

        def done(result):
            self.busy = False
            self.pending = None
            dpg.set_value("team_password", "")
            self.refresh()

        self.app.submit(lambda: client.request(method, path, body, key=key), done, self.failed)

    def clear_user(self):
        self.selected_user = None
        for tag in ("team_user", "team_user_id", "team_username", "team_display", "team_password"):
            dpg.set_value(tag, "")
        dpg.set_value("team_disabled", False)
        dpg.set_value("team_revoke", False)

    def select_user(self, sender, label):
        self.selected_user = self.users.get(label)
        if self.selected_user:
            for tag, key in (
                ("team_user_id", "id"),
                ("team_username", "username"),
                ("team_display", "display_name"),
                ("team_disabled", "disabled"),
            ):
                dpg.set_value(
                    tag, bool(self.selected_user[key]) if key == "disabled" else self.selected_user[key]
                )
            dpg.set_value("team_password", "")
            dpg.set_value("team_revoke", False)

    def use_user(self):
        if self.selected_user:
            dpg.set_value("team_member_id", self.selected_user["id"])
            self.message("Account selected for Project members. Choose the role and Add / update role.")

    def select_member(self, sender, value, item):
        dpg.set_value("team_member_id", item["id"])
        dpg.set_value("team_role", item["role"])
        dpg.set_value(
            "team_member_picker",
            next((label for label, u in self.member_choices.items() if u["id"] == item["id"]), ""),
        )

    def pick_member(self, sender, label):
        selected = self.member_choices.get(label)
        if selected:
            dpg.set_value("team_member_id", selected["id"])
            if "role" in selected:
                dpg.set_value("team_role", selected["role"])

    def create_user(self):
        if self.selected_user:
            self.message("Choose New account form before creating another account.")
            return
        self.mutate(
            "POST",
            "/users",
            {
                "username": dpg.get_value("team_username"),
                "display_name": dpg.get_value("team_display"),
                "password": dpg.get_value("team_password"),
            },
        )

    def update_user(self):
        if not self.selected_user:
            self.message("Select an account first.")
            return
        body = {
            "expected_user_revision": self.selected_user["user_revision"],
            "display_name": dpg.get_value("team_display"),
            "disabled": dpg.get_value("team_disabled"),
            "revoke_sessions": dpg.get_value("team_revoke"),
        }
        password = dpg.get_value("team_password")
        if password:
            body["password"] = password
        self.mutate("PATCH", f"/users/{self.selected_user['id']}", body)

    def member(self, remove):
        if not self.project:
            self.message("Choose a project first.")
            return
        ident = dpg.get_value("team_member_id").strip()
        if not ident:
            self.message("Select a member or enter a user ID.")
            return
        body = {"expected_project_revision": self.project["project_revision"]}
        if not remove:
            body["role"] = dpg.get_value("team_role")
        self.mutate("DELETE" if remove else "PUT", f"/projects/{self.project['id']}/members/{ident}", body)
