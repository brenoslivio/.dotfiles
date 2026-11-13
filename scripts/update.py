#!/usr/bin/env python3
"""Install only CI-verified revisions; keep activation separate from checkout state."""
import argparse
import fcntl
import io
import json
import os
from pathlib import Path
import pwd
import re
import socket
import subprocess
import sys
import tempfile
import zipfile

REPOSITORY = "brenoslivio/.dotfiles"
WORKFLOW = "ci.yml"
HOST = "ahimsa"
USER = "brenoslivio"
HOSTS = {
    "ahimsa": {"user": USER, "jobs": {"checks", "ahimsa-build", "ahimsa-ready"}},
    "ahimsa-vps": {"user": "root", "jobs": {"checks", "vps-build", "ahimsa-vps-ready"}},
}
REQUIRED_JOBS = HOSTS[HOST]["jobs"]
STORE_PATH = re.compile(r"/nix/store/[0-9a-df-np-sv-z]{32}-[^/\s]+")
SHA = re.compile(r"[0-9a-f]{40}")


class UpdateError(RuntimeError):
    pass


def run(*args, capture=True, binary=False):
    result = subprocess.run(args, check=True, stdout=subprocess.PIPE if capture else None,
                            text=not binary)
    return result.stdout if binary else (result.stdout or "").strip()


def api(endpoint, *, binary=False):
    return run("gh", "api", "--hostname", "github.com", f"repos/{REPOSITORY}/{endpoint}", binary=binary)


def api_json(endpoint):
    return json.loads(api(endpoint))


def pages(endpoint, key):
    result = []
    for page in range(1, 101):
        join = "&" if "?" in endpoint else "?"
        batch = api_json(f"{endpoint}{join}per_page=100&page={page}")[key]
        result.extend(batch)
        if len(batch) < 100:
            return result
    raise UpdateError("GitHub response exceeded the pagination limit.")


def validate_run(workflow, candidate, sha):
    if not (candidate.get("workflow_id") == workflow["id"]
            and candidate.get("path") == ".github/workflows/ci.yml"
            and candidate.get("head_sha") == sha
            and candidate.get("head_branch") == "main"
            and candidate.get("event") == "push"
            and candidate.get("repository", {}).get("full_name") == REPOSITORY
            and candidate.get("head_repository", {}).get("full_name") == REPOSITORY
            and candidate.get("status") == "completed"
            and candidate.get("conclusion") == "success"):
        raise UpdateError("The latest post-merge CI run has not passed for this exact revision.")


def validate_jobs(jobs, host=HOST):
    for name in HOSTS[host]["jobs"]:
        matches = [job for job in jobs if job["name"] == name]
        if len(matches) != 1 or matches[0].get("status") != "completed" or matches[0].get("conclusion") != "success":
            raise UpdateError(f"Required CI job did not pass: {name}")


def validate_manifest(manifest, sha, candidate, host=HOST):
    expected = {"schema": 1, "repository": REPOSITORY, "sha": sha, "host": host,
                "system": "x86_64-linux", "user": HOSTS[host]["user"], "event": "push",
                "run_id": str(candidate["id"]), "run_attempt": str(candidate["run_attempt"])}
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise UpdateError("CI evidence does not identify this revision, host, and run attempt.")
    for key in (("system_path", "home_path") if host == HOST else ("system_path",)):
        if not STORE_PATH.fullmatch(manifest.get(key, "")):
            raise UpdateError(f"Invalid {key} in CI evidence.")
    return manifest


def evidence(sha, host=HOST):
    if not SHA.fullmatch(sha):
        raise UpdateError("Invalid commit SHA.")
    workflow = api_json(f"actions/workflows/{WORKFLOW}")
    candidates = pages(f"actions/workflows/{workflow['id']}/runs?head_sha={sha}&event=push&branch=main", "workflow_runs")
    if not candidates:
        raise UpdateError("No post-merge CI run exists for this revision.")
    candidate = max(candidates, key=lambda item: (item["id"], item["run_attempt"]))
    validate_run(workflow, candidate, sha)
    attempt = candidate["run_attempt"]
    validate_jobs(pages(f"actions/runs/{candidate['id']}/attempts/{attempt}/jobs", "jobs"), host)
    name = f"{host}-{sha}-{attempt}"
    artifacts = [item for item in pages(f"actions/runs/{candidate['id']}/artifacts", "artifacts")
                 if item["name"] == name and not item["expired"]]
    if len(artifacts) != 1:
        raise UpdateError("CI evidence is missing or expired; rerun CI for this revision.")
    with zipfile.ZipFile(io.BytesIO(api(f"actions/artifacts/{artifacts[0]['id']}/zip", binary=True))) as archive:
        info = archive.getinfo("manifest.json")
        if info.file_size > 16384:
            raise UpdateError("CI evidence is unexpectedly large.")
        manifest = json.loads(archive.read(info))
    manifest = validate_manifest(manifest, sha, candidate, host)
    manifest["ci_url"] = candidate["html_url"]
    return manifest


def git(repo, *args):
    return run("git", "-C", str(repo), *args)


def clean_checkout(repo):
    if git(repo, "status", "--porcelain", "--untracked-files=all"):
        raise UpdateError("Commit or remove local changes, including untracked files, before updating.")
    if git(repo, "symbolic-ref", "--short", "HEAD") != "main":
        raise UpdateError("Switch to main before updating.")
    for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply", "BISECT_LOG"):
        path = Path(git(repo, "rev-parse", "--git-path", marker))
        if not path.is_absolute():
            path = repo / path
        if path.exists():
            raise UpdateError("Finish the current Git operation before updating.")
    origin = git(repo, "remote", "get-url", "origin").removesuffix(".git")
    if origin not in {f"git@github.com:{REPOSITORY}", f"https://github.com/{REPOSITORY}",
                      f"ssh://git@github.com/{REPOSITORY}"}:
        raise UpdateError("origin does not match the trusted GitHub repository.")


def source_url(repo, sha):
    return f"git+{repo.as_uri()}?rev={sha}"


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        temporary = stream.name
    os.replace(temporary, path)


def read_state(directory):
    path = directory / "state.json"
    return json.loads(path.read_text()) if path.exists() else {}


def resolved(path):
    return str(Path(path).resolve()) if Path(path).exists() else None


def system_status():
    return {"active": resolved("/run/current-system"),
            "boot_default": resolved("/nix/var/nix/profiles/system"),
            "known_good": resolved("/nix/var/nix/profiles/dotfiles-known-good")}


def preserve_good():
    active = system_status()["active"]
    if not active or not STORE_PATH.fullmatch(active):
        raise UpdateError("Cannot identify the active NixOS system.")
    run("sudo", "nix-env", "--profile", "/nix/var/nix/profiles/dotfiles-known-good",
        "--set", active, capture=False)
    print(f"Protected known-good system: {active}")


def build_candidate(repo, sha, manifest, directory, home, host=HOST):
    attr = f"homeConfigurations.{USER}.activationPackage" if home else f"nixosConfigurations.{host}.config.system.build.toplevel"
    link = directory / ("pending-home" if home else "pending-system")
    staging = directory / ("building-home" if home else "building-system")
    result = json.loads(run("nix", "build", "--json", "--no-update-lock-file", "--no-write-lock-file",
                            "--out-link", str(staging), f"{source_url(repo, sha)}#{attr}"))
    path = result[0]["outputs"]["out"]
    if path != manifest["home_path" if home else "system_path"]:
        staging.unlink(missing_ok=True)
        raise UpdateError("The local build differs from the system recorded by CI; activation refused.")
    # Keep the previous pending root until its verified replacement is protected.
    run("nix-store", "--add-root", str(link), "--indirect", "--realise", path)
    staging.unlink(missing_ok=True)
    return path


def activation_choice(home=False):
    choices = {"1": "switch", "2": "later"} if home else {"1": "switch", "2": "boot", "3": "later"}
    print("1) Apply now  2) Later" if home else "1) Apply now  2) Next boot  3) Later")
    return choices.get(input("Choice [Later]: ").strip(), "later")


def update(repo, directory, home=False):
    clean_checkout(repo)
    git(repo, "fetch", "origin", "+refs/heads/main:refs/remotes/origin/main")
    sha = git(repo, "rev-parse", "refs/remotes/origin/main")
    manifest = evidence(sha)
    clean_checkout(repo)
    try:
        git(repo, "merge-base", "--is-ancestor", "HEAD", sha)
    except subprocess.CalledProcessError as exc:
        raise UpdateError("Local main is ahead or diverged; resolve it before updating.") from exc
    print(f"Verified {sha}\n{manifest['ci_url']}", flush=True)
    print(git(repo, "log", "--oneline", f"HEAD..{sha}") or "Checkout already current; checking activation separately.")
    git(repo, "merge", "--ff-only", sha)
    clean_checkout(repo)
    if git(repo, "rev-parse", "HEAD") != sha:
        raise UpdateError("Checkout changed during the update; retry from clean main.")
    path = build_candidate(repo, sha, manifest, directory, home)
    state = read_state(directory)
    kind = "home" if home else "system"
    state[f"pending_{kind}"] = {"sha": sha, "path": path, "ci_url": manifest["ci_url"]}
    atomic_json(directory / "state.json", state)
    status = system_status()
    print(json.dumps(status, indent=2))
    print(f"Candidate: {path}")
    if (not home and status["active"] == path and status["boot_default"] == path
            and not state.get("activation_intent")):
        print("Already active and selected for next boot.")
        return
    old = state.get("applied_home", {}).get("path") if home else status["active"]
    if old and Path(old).exists():
        run("nix", "store", "diff-closures", old, path, capture=False)
    if not home:
        print("Activation preview:", flush=True)
        run("sudo", f"{path}/bin/switch-to-configuration", "dry-activate", capture=False)
    choice = activation_choice(home)
    state[f"pending_{kind}"]["choice"] = choice
    atomic_json(directory / "state.json", state)
    if choice == "later":
        print("Candidate retained. Active system and existing boot default are unchanged.")
        return
    # Persist intent before activation. If interrupted, status reads actual system links.
    state["activation_intent"] = {"kind": kind, "sha": sha, "path": path, "choice": choice}
    atomic_json(directory / "state.json", state)
    if home:
        run(f"{path}/activate", capture=False)
        state["applied_home"] = {"sha": sha, "path": path}
    else:
        if not status["known_good"]:
            preserve_good()
        run("sudo", "nixos-rebuild", choice, "--store-path", path, capture=False)
        state["last_system_action"] = {"sha": sha, "path": path, "choice": choice}
    state.pop("activation_intent", None)
    atomic_json(directory / "state.json", state)
    print("Activation completed." if choice == "switch" else "Scheduled for next boot; no reboot requested.")


def notify(directory, host=HOST):
    sha = api_json("git/ref/heads/main")["object"]["sha"]
    manifest = evidence(sha) if host == HOST else evidence(sha, host)
    status = system_status() if host == HOST else {}
    state = read_state(directory)
    path = manifest["system_path"]
    command = "up" if host == HOST else "up-vps"
    if status.get("active") == path:
        label = "active"
    elif status.get("boot_default") == path:
        label = "scheduled for next boot"
    elif state.get("pending_system", {}).get("path") == path:
        label = f"prepared; run {command} to review"
    else:
        label = f"available; run {command} to review"
    key = f"{sha}:{label}"
    if state.get("notified") != key:
        if label != "active":
            run("notify-send", f"Tested NixOS update: {host}", f"{sha[:12]}: {label}", capture=False)
        state["notified"] = key
        atomic_json(directory / "state.json", state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["up", "home", "up-vps", "status-vps", "confirm-vps", "rollback-vps", "notify", "status", "mark-good", "rollback", "rollback-good"], nargs="?", default="up")
    args = parser.parse_args()
    if socket.gethostname() != HOST:
        raise UpdateError(f"This updater supports {HOST} only.")
    if os.geteuid() == 0:
        raise UpdateError("Run as your normal user; privileged actions use sudo.")
    if pwd.getpwuid(os.getuid()).pw_name != USER:
        raise UpdateError(f"Run as {USER}.")
    directory = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "dotfiles"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "update.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise UpdateError("Another updater operation is running.") from exc
        if args.command.endswith("-vps"):
            # Share exception types when this file is launched as a CLI script.
            sys.modules["update"] = sys.modules[__name__]
            import vps_update
            repo = Path(os.environ.get("DOTFILES_REPO", str(Path.home() / ".dotfiles"))).resolve()
            vps_update.dispatch(args.command, repo, directory / "ahimsa-vps")
        elif args.command == "status":
            print(json.dumps({**read_state(directory), **system_status()}, indent=2))
        elif args.command == "mark-good":
            preserve_good()
        elif args.command == "notify":
            errors = []
            for host, target in [(HOST, directory), ("ahimsa-vps", directory / "ahimsa-vps")]:
                try:
                    notify(target, host)
                except (UpdateError, subprocess.CalledProcessError, OSError, ValueError, KeyError) as exc:
                    errors.append(f"{host}: {exc}")
            if errors:
                raise UpdateError("; ".join(errors))
        elif args.command == "rollback":
            run("sudo", "nixos-rebuild", "switch", "--rollback", capture=False)
        elif args.command == "rollback-good":
            path = system_status()["known_good"]
            if not path:
                raise UpdateError("No protected known-good system exists.")
            run("sudo", "nixos-rebuild", "switch", "--store-path", path, capture=False)
        else:
            repo = Path(os.environ.get("DOTFILES_REPO", str(Path.home() / ".dotfiles"))).resolve()
            update(repo, directory, args.command == "home")


if __name__ == "__main__":
    try:
        main()
    except (UpdateError, subprocess.SubprocessError, OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        sys.exit(f"Update stopped: {error}")
    except (KeyboardInterrupt, EOFError):
        sys.exit("Update interrupted. Run dotfiles-status to inspect the current state.")
