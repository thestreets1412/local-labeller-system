from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Content(StrictModel):
    verified_empty: StrictBool = False
    image_labels: list[str] = Field(default_factory=list, max_length=1)
    shapes: list[dict] = Field(default_factory=list, max_length=10000)


class Save(StrictModel):
    expected_revision: int = Field(ge=0, strict=True)
    expected_state_revision: int = Field(ge=0, strict=True)
    class_schema_id: UUID
    content: Content


class Login(StrictModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class ProjectCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    task_type: Literal["detection", "classification", "segmentation"] = "detection"
    initial_classes: list[str] = Field(min_length=1, max_length=100)


class YoloImport(StrictModel):
    class_schema_id: str = Field(min_length=36, max_length=36)
    class_mapping: dict[str, str] = Field(min_length=1, max_length=1000)
    empty_is_verified: StrictBool = False


class ImportRequest(StrictModel):
    source_alias: Literal["inbox"] = "inbox"
    relative_paths: list[str] = Field(min_length=1, max_length=50000)
    dry_run: bool = False
    yolo: YoloImport | None = None


class ClaimRequest(StrictModel):
    mode: Literal["edit"] = "edit"
    client_instance_id: UUID


class UserCreate(StrictModel):
    username: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=1024)


class UserUpdate(StrictModel):
    expected_user_revision: int = Field(ge=1, strict=True)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    disabled: StrictBool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=1024)
    revoke_sessions: StrictBool = False


class MemberUpdate(StrictModel):
    expected_project_revision: int = Field(ge=1, strict=True)
    role: Literal["viewer", "annotator", "reviewer", "maintainer"]


class MemberRemove(StrictModel):
    expected_project_revision: int = Field(ge=1, strict=True)
