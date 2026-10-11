"""Cross-file consistency checks. These catch the boring breakages that only
show up after a deploy: an entry point renamed in pyproject but not in the
job, an app command pointing at a moved file, a resource file not included."""

import itertools
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load(path: str):
    return yaml.safe_load((ROOT / path).read_text())


def test_bundle_targets_and_host():
    bundle = load("databricks.yml")
    assert set(bundle["targets"]) == {"dev", "staging", "prod"}
    assert bundle["targets"]["dev"]["default"] is True
    assert bundle["targets"]["prod"]["mode"] == "production"
    for t in bundle["targets"].values():
        assert t["workspace"]["host"] == "https://dbc-d40d7b72-eeb2.cloud.databricks.com"
        assert t["variables"]["schema"].startswith("retail_")


def test_every_job_entry_point_exists_in_pyproject():
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["scripts"]
    jobs = load("resources/jobs.yml")["resources"]["jobs"]
    used = {t["python_wheel_task"]["entry_point"] for job in jobs.values() for t in job["tasks"]}
    assert used <= set(scripts), used - set(scripts)
    for target in scripts.values():
        module, func = target.split(":")
        mod = __import__(module, fromlist=[func])
        assert callable(getattr(mod, func))


def test_etl_task_graph_is_a_chain():
    tasks = load("resources/jobs.yml")["resources"]["jobs"]["retail_etl"]["tasks"]
    order = [t["task_key"] for t in tasks]
    assert order == ["setup", "generate", "bronze", "silver", "gold", "quality_gate"]
    for prev, task in itertools.pairwise(tasks):
        assert task["depends_on"] == [{"task_key": prev["task_key"]}]


def test_app_wiring():
    app_yaml = load("app.yaml")
    script = app_yaml["command"][-1]
    assert (ROOT / script).exists()
    value_from = {e["valueFrom"] for e in app_yaml["env"] if "valueFrom" in e}
    declared = {
        r["name"]
        for r in load("resources/apps.yml")["resources"]["apps"]["retail_app"]["resources"]
    }
    assert value_from == declared


def test_requirements_cover_runtime_deps():
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    reqs = (ROOT / "requirements.txt").read_text()
    for d in deps:
        assert d.split(">")[0] in reqs
