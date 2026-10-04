import copy
import hashlib
import itertools
import json
import os
import random
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest
from pydantic import ValidationError

from visionlabel.domain import Problem, canonical, digest
from visionlabel.split_contracts import normalized_config, normalized_input
from visionlabel.splitting import PARTITIONS, compare_previews, effective_groups, plan_split, targets


def ident(n):
    return f"00000000-0000-4000-8000-{n:012d}"


def source(count=16):
    return {
        "project_id": ident(900),
        "version_id": ident(901),
        "version_manifest_sha256": "a" * 64,
        "task_type": "detection",
        "class_ids": [ident(800), ident(801)],
        "enforce_group_split": True,
        "items": [
            {
                "image_id": ident(i + 1),
                "asset_sha256": hashlib.sha256(f"asset-{i}".encode()).hexdigest(),
                "annotation_sha256": hashlib.sha256(f"annotation-{i}".encode()).hexdigest(),
                "group_key": f"unit-{i // 2}",
                "class_ids": [ident(800 + i % 2)],
                "verified_empty": False,
            }
            for i in range(count)
        ],
    }


def config(strategy="stratified_group", **overrides):
    return {
        "strategy": strategy,
        "ratios_bps": {"train": 5000, "val": 2500, "test": 2500},
        "seed": 42,
        "require_group_key": True,
        "size_tolerance_bps": 0,
        "class_tolerance_bps": 0,
        **overrides,
    }


def run(data=None, options=None):
    return plan_split(normalized_input(data or source()), normalized_config(options or config()))


def partitions(result):
    return {i["image_id"]: i["partition"] for i in result["assignments"]}


def assert_no_leakage(data, result, group_aware=True):
    mapping = partitions(result)
    assert len(mapping) == len(result["assignments"]) == len(data["items"])
    assets, groups = {}, {}
    for item in data["items"]:
        part = mapping[item["image_id"]]
        assert assets.setdefault(item["asset_sha256"], part) == part
        if group_aware and item["group_key"] is not None:
            assert groups.setdefault(item["group_key"], part) == part


@pytest.mark.parametrize("strategy", ["random", "stratified", "group", "stratified_group"])
def test_all_strategies_repeat_exactly_and_do_not_mutate_inputs(strategy):
    data = source()
    grouped = strategy in ("group", "stratified_group")
    data["enforce_group_split"] = grouped
    options = config(strategy, class_tolerance_bps=10000 if strategy == "random" else 0)
    before = copy.deepcopy((data, options))
    first = run(data, options)
    assert first["status"] == "PASSED", first["diagnostics"]
    assert_no_leakage(data, first, grouped)
    data["items"].reverse()
    data["class_ids"].reverse()
    second = run(data, options)
    assert canonical(first) == canonical(second)
    assert [first["diagnostics"]["partitions"][p]["actual_image_count"] for p in PARTITIONS] == [8, 4, 4]
    assert options == before[1]
    if not grouped:
        assert any(w["code"] == "GROUPS_IGNORED" for w in first["diagnostics"]["warnings"])


def test_random_largest_remainder_and_independent_seed_order():
    data = source(10)
    data["enforce_group_split"] = False
    options = config(
        "random",
        ratios_bps={"train": 3334, "val": 3333, "test": 3333},
        size_tolerance_bps=1000,
        class_tolerance_bps=10000,
    )
    result = run(data, options)
    assert result["status"] == "PASSED"
    # Independently calculate the documented SHA ordering, then fixed 4/3/3 quotas.
    ordered = sorted(
        (i["image_id"] for i in data["items"]),
        key=lambda value: hashlib.sha256(("42|vl-split-1|" + value).encode()).digest(),
    )
    expected = {
        image: "train" if index < 4 else "val" if index < 7 else "test" for index, image in enumerate(ordered)
    }
    assert partitions(result) == expected
    assert targets(2, {"train": 5000, "val": 2500, "test": 2500}) == {"train": 1, "val": 1, "test": 0}


def test_connected_components_transitively_merge_group_and_asset_identity():
    data = source(8)
    # unit-0 links 1/2; hash connects 2/3; unit-1 links 3/4.
    data["items"][2]["asset_sha256"] = data["items"][1]["asset_sha256"]
    result = run(data, config(size_tolerance_bps=10000, class_tolerance_bps=10000))
    assert result["status"] == "PASSED"
    assert result["diagnostics"]["effective_groups"] == 3
    assert len({partitions(result)[ident(i)] for i in range(1, 5)}) == 1
    assert_no_leakage(data, result)
    data["enforce_group_split"] = False
    random_result = run(data, config("random", size_tolerance_bps=10000, class_tolerance_bps=10000))
    assert_no_leakage(data, random_result, False)


@pytest.mark.parametrize(
    "require,policy,expected",
    [(True, "singleton", "FAILED"), (False, "error", "FAILED"), (False, "singleton", "PASSED")],
)
def test_missing_group_policy_is_explicit(require, policy, expected):
    data = source()
    for item in data["items"]:
        item["group_key"] = None
    result = run(data, config(require_group_key=require, missing_group_policy=policy))
    assert result["status"] == expected
    if expected == "PASSED":
        assert result["diagnostics"]["effective_groups"] == 16
        assert result["diagnostics"]["warnings"][0]["code"] == "MISSING_GROUP_SINGLETON"
    else:
        assert result["diagnostics"]["violations"][0]["code"] == "MISSING_GROUP"


def test_group_policy_cannot_be_disabled_by_random_strategy():
    result = run(options=config("random"))
    assert result["status"] == "FAILED" and not result["assignment_complete"]
    assert result["diagnostics"]["violations"][0]["code"] == "GROUP_POLICY"


def test_pins_expand_to_whole_component_and_conflicts_fail():
    options = config(pinned_assignments=[{"image_id": ident(1), "partition": "test"}])
    result = run(options=options)
    assert result["status"] == "PASSED"
    assert partitions(result)[ident(1)] == partitions(result)[ident(2)] == "test"
    options["pinned_assignments"].append({"image_id": ident(2), "partition": "train"})
    failed = run(options=options)
    assert failed["status"] == "FAILED"
    assert any(v["code"] == "CONFLICTING_PINS" for v in failed["diagnostics"]["violations"])


@pytest.mark.parametrize(
    "pins,code",
    [
        ([{"image_id": ident(100), "partition": "train"}], "UNKNOWN_PIN"),
        ([{"image_id": ident(1), "partition": "test"}], "DISABLED_PARTITION_PIN"),
    ],
)
def test_invalid_pins(pins, code):
    result = run(options=config(ratios_bps={"train": 8000, "val": 2000, "test": 0}, pinned_assignments=pins))
    assert result["status"] == "FAILED"
    assert any(v["code"] == code for v in result["diagnostics"]["violations"])


def test_nonzero_partition_repair_and_zero_partitions():
    data = source(3)
    data["enforce_group_split"] = False
    options = config(
        "random",
        ratios_bps={"train": 9998, "val": 1, "test": 1},
        size_tolerance_bps=10000,
        class_tolerance_bps=10000,
    )
    result = run(data, options)
    assert result["status"] == "PASSED"
    assert set(partitions(result).values()) == set(PARTITIONS)
    result = run(options=config(ratios_bps={"train": 10000, "val": 0, "test": 0}))
    assert result["status"] == "PASSED"
    assert set(partitions(result).values()) == {"train"}


def test_impossible_group_count_and_pinned_empty_partition():
    result = run(source(4))
    assert result["status"] == "FAILED"
    assert any(
        v["code"] == "TOO_FEW_GROUPS" and v["proven_infeasible"] for v in result["diagnostics"]["violations"]
    )
    data = source(6)
    pins = [{"image_id": i["image_id"], "partition": "train"} for i in data["items"]]
    result = run(data, config(pinned_assignments=pins))
    assert result["status"] == "FAILED"
    assert result["diagnostics"]["violations"][0]["code"] == "PINNED_EMPTY_PARTITION"


def test_rare_class_and_tolerances_are_never_silently_relaxed():
    data = source()
    for item in data["items"]:
        item["class_ids"] = [ident(800)]
    data["items"][0]["class_ids"] = [ident(801)]
    strict = run(data, config(strict_class_coverage=True))
    assert strict["status"] == "FAILED"
    assert any(
        v["code"] == "RARE_CLASS" and v["proven_infeasible"] for v in strict["diagnostics"]["violations"]
    )
    relaxed = run(data, config(class_tolerance_bps=10000))
    assert relaxed["status"] == "PASSED"
    assert any(w["code"] == "CLASS_COVERAGE" for w in relaxed["diagnostics"]["warnings"])
    precise = run(data)
    assert precise["status"] == "FAILED"
    assert precise["config"]["class_tolerance_bps"] == 0
    assert any(
        v["code"] == "CLASS_TOLERANCE" and not v["proven_infeasible"]
        for v in precise["diagnostics"]["violations"]
    )


def test_image_presence_multilabel_and_verified_empty_pseudo_class():
    data = source()
    for index, item in enumerate(data["items"]):
        item["class_ids"] = [] if index % 2 else [ident(800), ident(801)]
        item["verified_empty"] = bool(index % 2)
    result = run(data)
    assert result["status"] == "PASSED"
    for cls in (ident(800), ident(801), "__empty__"):
        assert result["diagnostics"]["classes"][cls]["total_images"] == 8
        assert [
            result["diagnostics"]["classes"][cls]["partitions"][p]["actual_image_count"] for p in PARTITIONS
        ] == [4, 2, 2]


@pytest.mark.parametrize(
    "change",
    [
        {"seed": -1},
        {"seed": True},
        {"seed": 2**32},
        {"algorithm_version": "unknown"},
        {"size_tolerance_bps": 10001},
        {"ratios_bps": {"train": 5000, "val": 2000, "test": 0}},
        {"ratios_bps": {"train": 0, "val": 5000, "test": 5000}},
    ],
)
def test_invalid_config_rejected(change):
    with pytest.raises(ValidationError):
        normalized_config(config(**change))


def test_invalid_source_and_classification():
    data = source()
    data["task_type"] = "classification"
    assert run(data)["status"] == "PASSED"
    data["items"][0]["class_ids"] = [ident(800), ident(801)]
    with pytest.raises(ValidationError):
        normalized_input(data)
    data = source()
    data["items"].append(copy.deepcopy(data["items"][0]))
    with pytest.raises(ValidationError):
        normalized_input(data)


def test_small_group_fixture_matches_independent_global_objective_minimum():
    data = source(8)
    data["items"][0]["group_key"] = "singleton-a"
    data["items"][7]["group_key"] = "singleton-b"
    options = config(size_tolerance_bps=10000, class_tolerance_bps=10000)
    result = run(data, options)
    groups = effective_groups(normalized_input(data)["items"], True)
    all_classes = [ident(800), ident(801)]

    def objective(mapping):
        score = Fraction()
        for p, ratio in options["ratios_bps"].items():
            assigned = [
                item for g, dest in zip(groups, mapping, strict=True) if dest == p for item in g["items"]
            ]
            score += (Fraction(len(assigned), 8) - Fraction(ratio, 10000)) ** 2
            for cls in all_classes:
                n = sum(cls in item["class_ids"] for item in assigned)
                score += (Fraction(n, 4) - Fraction(ratio, 10000)) ** 2 / 2
        return score

    candidates = (a for a in itertools.product(PARTITIONS, repeat=len(groups)) if set(a) == set(PARTITIONS))
    optimum = min(objective(a) for a in candidates)
    actual = tuple(partitions(result)[g["items"][0]["image_id"]] for g in groups)
    assert objective(actual) == optimum  # Only this small fixture; no global-optimum claim in general.


def test_order_seed_state_and_process_hash_seed_independence(tmp_path):
    data, options = source(), config()
    expected = canonical(run(data, options))
    random.seed(999)
    random.shuffle(data["items"])
    assert canonical(run(data, options)) == expected
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"source": data, "config": options}), encoding="utf-8")
    code = "import json,sys; from visionlabel.split_contracts import normalized_input,normalized_config; from visionlabel.splitting import plan_split; from visionlabel.domain import canonical; r=json.load(open(sys.argv[1])); sys.stdout.buffer.write(canonical(plan_split(normalized_input(r['source']),normalized_config(r['config']))))"
    for seed in ("1", "9173"):
        result = subprocess.run(
            [sys.executable, "-c", code, str(request)],
            env=dict(os.environ, PYTHONHASHSEED=seed),
            capture_output=True,
            check=True,
        )
        assert result.stdout == expected


def test_compare_detects_asset_and_group_test_to_train_across_versions():
    old_source = normalized_input(source())
    old = run(old_source)
    old_test = next(i for i in old_source["items"] if partitions(old)[i["image_id"]] == "test")
    new_source = copy.deepcopy(old_source)
    new_source["version_id"] = ident(902)
    new_source["version_manifest_sha256"] = "b" * 64
    new_source["items"][0]["asset_sha256"] = old_test["asset_sha256"]
    new_source["items"][0]["group_key"] = old_test["group_key"]
    options = config(
        size_tolerance_bps=10000,
        class_tolerance_bps=10000,
        pinned_assignments=[{"image_id": ident(1), "partition": "train"}],
    )
    new = run(new_source, options)
    comparison = compare_previews(old_source, old, new_source, new)
    assert any(
        item["image_id"] == ident(1) and item["same_asset"] and item["same_group"]
        for item in comparison["test_to_train_leakage"]
    )
    new["input_sha256"] = "0" * 64
    with pytest.raises(Problem):
        compare_previews(old_source, old, new_source, new)


def test_preview_cli_writes_diagnostics_and_refuses_overwrite(tmp_path):
    input_path, config_path, output = (
        tmp_path / name for name in ("input.json", "config.json", "preview.json")
    )
    input_path.write_text(json.dumps(source()), encoding="utf-8")
    config_path.write_text(json.dumps(config()), encoding="utf-8")
    command = [
        sys.executable,
        "-m",
        "visionlabel.split_preview",
        "--input",
        str(input_path),
        "--config",
        str(config_path),
        "--output",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    original = output.read_bytes()
    document = json.loads(original)
    assert document["canonical_split"] is False and document["provenance_verified"] is False
    assert document["report"]["status"] == "PASSED"
    assert digest(original) in result.stdout
    assert subprocess.run(command, capture_output=True).returncode == 1
    assert output.read_bytes() == original
    config_path.write_text(
        json.dumps(
            config(
                strict_class_coverage=True,
                pinned_assignments=[
                    {"image_id": ident(1), "partition": "val"},
                    {"image_id": ident(2), "partition": "train"},
                ],
            )
        ),
        encoding="utf-8",
    )
    command[-1] = str(tmp_path / "failed.json")
    assert subprocess.run(command, capture_output=True).returncode == 2
    assert json.loads(Path(command[-1]).read_bytes())["report"]["status"] == "FAILED"


def test_frozen_vl_split_1_golden_vectors():
    fixture = Path(__file__).parent / "fixtures/splitting"
    golden = json.loads((fixture / "golden-vl-split-1.json").read_text())
    for strategy, expected in golden.items():
        data = json.loads((fixture / "source.json").read_text())
        data["enforce_group_split"] = strategy in ("group", "stratified_group")
        options = config(strategy, class_tolerance_bps=10000 if strategy == "random" else 0)
        result = run(data, options)
        assert [a["partition"] for a in result["assignments"]] == expected["partitions_by_image_id"]
        assert digest(canonical(result)) == expected["sha256"]


def test_varied_component_sizes_preserve_exact_coverage_and_pins():
    rng = random.Random(173)
    for count in range(12, 33):
        data = source(count)
        for item in data["items"]:
            item["group_key"] = f"unit-{rng.randrange(8)}"
        data["items"][-1]["asset_sha256"] = data["items"][0]["asset_sha256"]
        options = config(
            size_tolerance_bps=10000,
            class_tolerance_bps=10000,
            pinned_assignments=[{"image_id": ident(1), "partition": "test"}],
        )
        result = run(data, options)
        if result["assignment_complete"]:
            assert_no_leakage(data, result)
            assert partitions(result)[ident(1)] == "test"
            assert all(result["diagnostics"]["partitions"][p]["actual_group_count"] > 0 for p in PARTITIONS)
        else:
            assert any(v["proven_infeasible"] for v in result["diagnostics"]["violations"])
