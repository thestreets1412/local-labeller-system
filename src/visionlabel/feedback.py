"""Local feedback routing. No network calls or changes to authorization policy."""

import dearpygui.dearpygui as dpg

from .domain import Problem

# More specific foreground dialogs precede their parent panels.
SURFACES = (
    ("checkpoint_browser", "ds_browser_status"),
    ("conflict_dialog", "conflict_status"),
    ("recovery_dialog", "recovery_status"),
    ("dirty_dialog", "dirty_status"),
    ("review_reject", "review_reject_status"),
    ("review_settings", "review_settings_status"),
    ("connection", "connection_status"),
    ("new_project", "new_project_status"),
    ("yolo_dialog", "yolo_status"),
    ("storage_manager", "storage_status"),
    ("dataset_manager", "ds_status"),
    ("project_manager", "pm_status"),
    ("export_dialog", "export_status"),
    ("team", "team_status"),
    ("statistics", "statistics_status"),
)


def active_surface():
    for window, status in SURFACES:
        if dpg.does_item_exist(window) and dpg.is_item_shown(window):
            return status
    return "status"


def failure_text(exc, next_step):
    reason = exc.message if isinstance(exc, Problem) else type(exc).__name__
    uncertain = isinstance(exc, Problem) and exc.code in ("DISCONNECTED", "SERVER_STOPPING")
    prefix = "Response not received; the operation result is unknown" if uncertain else "Could not complete"
    return f"{prefix}: {reason.rstrip('.')}. {next_step}"


BUSY = "Another operation is running. Wait for it to finish, then try again."
PROJECT = "No project is selected. Select a project, then try again."
IMAGE = "No image is open. Open an image, then try again."


def resize_messages():
    extras = (
        ("main", "status"),
        ("main", "review_availability"),
        ("dataset_manager", "ds_availability"),
        ("dataset_manager", "ds_progress"),
        ("export_dialog", "export_availability"),
        ("team", "team_availability"),
    )
    for window, tag in SURFACES + extras:
        if dpg.does_item_exist(tag) and dpg.is_item_shown(window):
            width = max(120, int(dpg.get_item_rect_size(window)[0]) - 40)
            if dpg.get_item_configuration(tag).get("wrap") != width:
                dpg.configure_item(tag, wrap=width)
