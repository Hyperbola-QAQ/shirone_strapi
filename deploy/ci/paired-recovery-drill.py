"""One-time rehearsal for the two recorded November releases on the deployment runner."""
import json
import os
from pathlib import Path
import runpy
import subprocess

root = Path.cwd()
ci = root / "deploy/ci"
state = Path("/home/github-actions/.local/state/shirone-release")
baseline = "a910d7771b32c78a854a2c774d9bac00faf3aeb0"
drill_parent = "3bc55410df4f7195c90afbbe97d94163901fa3ec"
current_source = "f5e75a6a0d8914fd3a23934bef56ae900544869a"
older_source = "79dda4c4376325136d4934ff71441c8f401fce9b"
older_manifest = "e59d883cfb6bae76363da25dc6fb9d7be6cefa3c"
adapter_code = runpy.run_path(str(ci / "automatic-release-adapter.py"))
lock_class = runpy.run_path(str(ci / "automatic-release-lock.py"))["ReleaseLock"]
ops = adapter_code["gitops"]
adapter = adapter_code["Adapter"](root, {}, 0, ".", ".", ".", "", state / "previous-release.json")


def require(value, message):
    if not value:
        raise RuntimeError(message)


def admission(snapshot):
    return {"manifests": {name: item["image"].split("@")[1] for name, item in snapshot["components"].items()}}


def verify_public_pair(snapshot):
    adapter.verify_restored({}, snapshot)
    article = snapshot["search_probe"]["url"]
    require(article.startswith("/posts/"), "Unexpected published article path")
    subprocess.run(["curl", "--fail", "--location", "--silent", "--show-error",
                    "--retry", "3", "--max-time", "20", "--output", "/dev/null",
                    "https://hyperbola.cc" + article], check=True)
    for name in ("cms", "ssr"):
        print(name, snapshot["components"][name]["image"], flush=True)


def logged_release(number):
    require((state / f"run-{number}-complete.json").is_file(), "Missing completed release receipt")
    return json.loads((state / f"run-{number}-snapshot.json").read_text())["data"]


def check_manifest(snapshot, rev):
    for component, item in snapshot["components"].items():
        manifest = ops.git(root, "show", f"{rev}:deploy/k8s/{component}.yaml")
        require([line.strip() for line in manifest.splitlines() if line.strip().startswith("image:")] ==
                ["image: " + item["image"]], "Release receipt and historical manifest differ")


with lock_class(state):
    head = ops.remote_head(root)
    require(head == os.environ["GITHUB_SHA"] == ops.git(root, "rev-parse", "HEAD"), "main changed")
    marker = state / "paired-drill-20261126-second.intent"
    finished = state / "paired-drill-20261126-second.complete"
    require(not finished.exists(), "Drill was already completed")
    recovering = marker.exists()
    if recovering:
        origin = marker.read_text().strip()
        require(ops.git(root, "rev-parse", origin + "^") == drill_parent, "Unknown drill origin")
        subprocess.run(["git", "merge-base", "--is-ancestor", origin, head], check=True)
        changes = ops.git(root, "diff", "--name-only", origin, head).splitlines()
        require(set(changes) <= {"deploy/k8s/cms.yaml", "deploy/k8s/ssr.yaml"}, "Unexpected changes since drill")
    else:
        require(ops.git(root, "rev-parse", head + "^") == drill_parent, "Unexpected release baseline")
    older = logged_release(43666801073)
    require(older["previous_source"] == older_source and older["source"] == current_source and older["rollback_safe"], "Unexpected prior pair")
    current = json.loads((state / "previous-release.json").read_text())
    require(current["source"] == current_source and current["rollback_compatible"] is True, "Unexpected final release")
    for component in ("ssr", "cms"):
        require(current["components"][component]["uid"] == older["components"][component]["uid"], "Deployment identity changed")
    check_manifest(current, baseline)
    check_manifest(older, older_manifest)
    adapter.head = head
    if not recovering:
        verify_public_pair(current)
        subprocess.run(["python3", str(ci / "check-git-push.py")], check=True)
        with marker.open("x") as receipt:
            receipt.write(head + "\n")
            receipt.flush()
            os.fsync(receipt.fileno())
    try:
        if not recovering:
            adapter.restore(admission(current), older)
            verify_public_pair(older)
            print("Prior production pair and published search verified", flush=True)
    finally:
        adapter.restore(admission(older), current)
        verify_public_pair(current)
        print("Original production pair and published search verified", flush=True)
    require(not recovering, "Interrupted attempt reconciled to original release; separate review required")
    finished.touch(exist_ok=False)
