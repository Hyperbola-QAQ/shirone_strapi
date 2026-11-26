"""Exercise the ordinary transaction's failure handler with two previously deployed component images."""
import json
import os
from pathlib import Path
import runpy
import subprocess

root = Path.cwd()
ci = root / "deploy/ci"
state = Path("/home/github-actions/.local/state/shirone-release")
modules = runpy.run_path(str(ci / "automatic-release-adapter.py"))
Base = modules["Adapter"]
git = modules["gitops"]
tx = runpy.run_path(str(ci / "automatic-release-transaction.py"))
current_source = "f5e75a6a0d8914fd3a23934bef56ae900544869a"
current_manifest = "a910d7771b32c78a854a2c774d9bac00faf3aeb0"
candidate_manifest = "e59d883cfb6bae76363da25dc6fb9d7be6cefa3c"
baseline = "536af1ea55ea5315bedc1689f7636faebfd13fb8"
head = os.environ["GITHUB_SHA"]
run = int(os.environ["GITHUB_RUN_ID"])


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def image(rev, component):
    manifest = git.git(root, "show", f"{rev}:deploy/k8s/{component}.yaml")
    lines = [line.split()[1] for line in manifest.splitlines() if line.strip().startswith("image:")]
    require(len(lines) == 1, "Unexpected component manifest")
    return lines[0]


class Drill(Base):
    injected = False

    def admit(self, run_id, source):
        require(git.remote_head(root) == head == source and self._git("rev-parse", "HEAD^") == baseline,
                "Unexpected dispatch head or parent")
        require((state / "run-43666801073-complete.json").is_file(), "Signed deployment completion missing")
        receipt = json.loads((state / "run-43666801073-snapshot.json").read_text())["data"]
        require(receipt["source"] == current_source and receipt["rollback_safe"], "Unexpected signed release record")
        old_source = "79dda4c4376325136d4934ff71441c8f401fce9b"
        require(receipt["previous_source"] == old_source, "Unexpected candidate release source")
        require(not self._git("diff", "--name-only", old_source, current_source, "--",
                              "cms", "Dockerfile", "pnpm-lock.yaml"), "CMS or dependency inputs changed")
        require(modules["project_name_only"](self._git("show", old_source + ":package.json"),
                                             self._git("show", current_source + ":package.json")),
                "Root package change differs from reviewed rename")
        self.targets = {name: image(candidate_manifest, name) for name in ("cms", "ssr")}
        for name, target in self.targets.items():
            require(receipt["components"][name] == {"uid": self._live(name)["uid"], "image": target},
                    "Candidate image or deployment identity differs")
            require(image(current_manifest, name) != target, "Both images must change")
        return {"source": current_source, "manifests": {
            name: target.split("@")[1] for name, target in self.targets.items()}}

    def snapshot(self, admission):
        snap = super().snapshot(admission)
        require(snap["previous_source"] == current_source and all(
            item["image"] == image(current_manifest, name) for name, item in snap["components"].items()),
            "Baseline differs from rehearsed production pair")
        self.head = head
        return snap

    def preview(self, admission, snap):
        self.verify_restored(admission, snap)
        subprocess.run(["python3", str(ci / "check-git-push.py")], check=True)

    def promote(self, component, admission, snap):
        target = self.targets[component]
        old = snap["components"][component]
        self.pending_commit = (component, self.head, old["image"], target)
        self.head = git.commit_manifest(root, component, self.head, old["image"], target)
        self.pending_commit = None
        subprocess.run(["bash", str(ci / "promote-reviewed.sh"), component, self.head, old["uid"],
                        old["image"], target, "--apply"], check=True)

    def verify(self, component, admission, snap):
        super().verify(component, admission, snap)
        if component == "ssr":
            for name in ("cms", "ssr"):
                super().verify(name, admission, snap)
                print("Candidate ready:", name, self.targets[name], flush=True)
            self.verify_all(admission, snap)
            print("Candidate pair ready; original published search probe passed.", flush=True)
            negative = {**snap, "search_probe": {**snap["search_probe"], "url": f"/posts/nonexistent-drill-{run}/"}}
            try:
                self.verify_all(admission, negative)
            except ValueError as exc:
                if str(exc) == "published search probe is missing":
                    self.injected = True
                    print("Controlled published-search acceptance failure.", flush=True)
                raise
            raise RuntimeError("Unexpected success of negative probe")

    def verify_restored(self, admission, snap):
        super().verify_restored(admission, snap)
        subprocess.run(["curl", "--fail", "--silent", "--show-error", "--location", "--max-time", "20",
                        "--output", "/dev/null", "https://hyperbola.cc" + snap["search_probe"]["url"]], check=True)


adapter = Drill(root, {}, 0, ".", ".", ".", "", state / "previous-release.json")
try:
    tx["execute"](adapter, state, run, head)
except RuntimeError as exc:
    require(adapter.injected and str(exc) == "Release failed; previous state was restored and verified",
            f"Automatic recovery acceptance failed: {exc}")
    for phase in ("cms-verified", "ssr-intent", "restore-intent", "restored"):
        require((state / f"run-{run}-{phase}.json").is_file(), f"Missing {phase} receipt")
    require(not (state / f"run-{run}-complete.json").exists(), "Failed deployment was marked successful")
    print("Release failed as intended. Automatic recovery verified Git, images, site, admin, search and article.")
else:
    raise RuntimeError("Expected release failure did not occur")
