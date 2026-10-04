"""Strict inputs for the split engine; released-version verification is an adapter concern."""

from typing import Literal
from uuid import UUID

from pydantic import Field, StrictBool, model_validator

from .contracts import StrictModel

Partition = Literal["train", "val", "test"]


class Ratios(StrictModel):
    train: int = Field(ge=1, le=10000, strict=True)
    val: int = Field(ge=0, le=10000, strict=True)
    test: int = Field(ge=0, le=10000, strict=True)

    @model_validator(mode="after")
    def total(self):
        if self.train + self.val + self.test != 10000:
            raise ValueError("Partition ratios must sum to 10,000 basis points.")
        return self


class PinnedAssignment(StrictModel):
    image_id: UUID
    partition: Partition


class SplitConfig(StrictModel):
    strategy: Literal["random", "stratified", "group", "stratified_group"] = "stratified_group"
    ratios_bps: Ratios = Field(default_factory=lambda: Ratios(train=7000, val=2000, test=1000))
    seed: int = Field(default=42, ge=0, le=2**32 - 1, strict=True)
    algorithm_version: Literal["vl-split-1"] = "vl-split-1"
    require_group_key: StrictBool = True
    missing_group_policy: Literal["error", "singleton"] = "error"
    strict_class_coverage: StrictBool = False
    size_tolerance_bps: int = Field(default=500, ge=0, le=10000, strict=True)
    class_tolerance_bps: int = Field(default=1000, ge=0, le=10000, strict=True)
    pinned_assignments: list[PinnedAssignment] = Field(default_factory=list, max_length=50000)


class SplitItem(StrictModel):
    image_id: UUID
    asset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    annotation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    group_key: str | None = Field(default=None, min_length=1, max_length=1024)
    class_ids: list[UUID] = Field(default_factory=list, max_length=10000)
    verified_empty: StrictBool = False


class SplitInput(StrictModel):
    input_schema_version: Literal["split-projection-1"] = "split-projection-1"
    project_id: UUID
    version_id: UUID
    version_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_type: Literal["detection", "segmentation", "classification"]
    class_ids: list[UUID] = Field(min_length=1, max_length=10000)
    enforce_group_split: StrictBool = True
    items: list[SplitItem] = Field(min_length=1, max_length=50000)

    @model_validator(mode="after")
    def identities_and_labels(self):
        classes = set(self.class_ids)
        if len(classes) != len(self.class_ids):
            raise ValueError("Schema class IDs must be unique.")
        if len({i.image_id for i in self.items}) != len(self.items):
            raise ValueError("Each image ID must occur exactly once.")
        for item in self.items:
            if len(set(item.class_ids)) != len(item.class_ids) or not set(item.class_ids) <= classes:
                raise ValueError("Image class presence must use unique IDs from the schema.")
            if self.task_type == "classification":
                if len(item.class_ids) != 1 or item.verified_empty:
                    raise ValueError("Classification requires exactly one class per image.")
            elif bool(item.class_ids) == item.verified_empty:
                raise ValueError("Each image needs class presence or verified-empty confirmation.")
        return self


def normalized_input(value):
    data = SplitInput.model_validate(value).model_dump(mode="json")
    data["class_ids"].sort()
    data["items"].sort(key=lambda item: item["image_id"])
    for item in data["items"]:
        item["class_ids"].sort()
    return data


def normalized_config(value):
    data = SplitConfig.model_validate(value).model_dump(mode="json")
    data["pinned_assignments"].sort(key=lambda pin: (pin["image_id"], pin["partition"]))
    return data
