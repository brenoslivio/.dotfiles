"""Read GitHub update status for the panel. Only the systemd oneshot contacts GitHub."""
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile

import update

BRANCH = "automation/flake-update"
WEB = f"https://github.com/{update.REPOSITORY}"
UNIT = "dotfiles-update-check.service"
STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "dotfiles"
RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", "/run/user/" + str(os.getuid()))) / "dotfiles-updates"
CACHE = STATE / "indicator.json"


def latest(workflow, **filters):
    runs = update.api_json(f"actions/workflows/{workflow}/runs", per_page=1, **filters)["workflow_runs"]
    return runs[0] if runs else None


def run_key(run):
    return [run["id"], run["run_attempt"]]


def ci_status(run):
    if not run:
        return "CI pending"
    if run["conclusion"] == "action_required" or run["status"] == "waiting":
        return "CI needs approval"
    if run["status"] != "completed":
        return "CI running"
    return "passed" if run["conclusion"] == "success" else "CI failed"


def proposal(previous):
    prs = update.api_json("pulls", head=f"{update.REPOSITORY.split('/')[0]}:{BRANCH}",
                 base="main", state="open", per_page=1)
    if not prs:
        run = latest("update.yml", branch="main")
        if run and ci_status(run) in {"CI failed", "CI needs approval"}:
            return {"text": "Flake proposal needs attention", "attention": True, "run": run["id"]}
        return {}
    pr = prs[0]
    sha = pr["head"]["sha"]
    run = latest(update.WORKFLOW, event="pull_request", branch=BRANCH, head_sha=sha)
    label = ci_status(run)
    if not run:
        suites = update.pages(f"commits/{sha}/check-suites", "check_suites")
        if any(s["app"]["slug"] == "github-actions" and s["conclusion"] == "action_required" for s in suites):
            label = "CI needs approval"
    key = [pr["number"], sha, run_key(run)] if run else None
    if label == "passed":
        if previous.get("verified") == key:
            return previous
        jobs = update.pages(f"actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs", "jobs")
        try:
            update.validate_jobs(jobs)
            label = "ready for review"
        except update.UpdateError:
            label = "CI failed"
    result = {"pr": pr["number"], "text": f"PR #{pr['number']} · {label}",
              "attention": label in {"ready for review", "CI failed", "CI needs approval"}}
    if run:
        result["run"] = run["id"]
    if label == "ready for review":
        result["verified"] = key
    return result


def system(previous):
    sha = update.api_json("git/ref/heads/main")["object"]["sha"]
    run = latest(update.WORKFLOW, event="push", branch="main", head_sha=sha)
    label = ci_status(run)
    result = {"text": "Current main · " + label, "attention": label in {"CI failed", "CI needs approval"}}
    if run:
        result["run"] = run["id"]
    if label != "passed":
        return result
    key = [sha, *run_key(run)]
    if previous.get("verified") == key and previous.get("expires", 0) > time.time():
        path, expires = previous["path"], previous["expires"]
    else:
        try:
            manifest = update.evidence(sha)
        except update.UpdateError as error:
            return {**result, "text": str(error), "attention": True}
        if [manifest["run_id"], manifest["run_attempt"]] != [str(n) for n in run_key(run)]:
            return {**result, "text": "Current main · CI changed during check"}
        path = manifest["system_path"]
        expires = datetime.fromisoformat(manifest["expires_at"]).timestamp() if manifest.get("expires_at") else 0
    local = update.system_label(path, update.read_state(STATE))
    text = {"active": "Laptop up to date", "scheduled for next boot": "Update scheduled for next boot"}.get(local)
    return {**result, "verified": key, "path": path, "expires": expires,
            "text": text or "Tested system update ready · run up", "attention": text is None}


def cached():
    try:
        return json.loads(CACHE.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def watch():
    from inotify_simple import INotify, flags

    STATE.mkdir(parents=True, exist_ok=True)
    with INotify() as watcher:
        mask = flags.CREATE | flags.MOVED_TO | flags.DELETE | flags.CLOSE_WRITE
        watcher.add_watch(STATE, mask)
        watcher.add_watch(RUNTIME, mask)
        while True:
            print(json.dumps(view(cached(), (RUNTIME / "checking").exists(), (RUNTIME / "manual").exists())), flush=True)
            while not any(e.name in {CACHE.name, "checking", "manual"} or e.mask & flags.Q_OVERFLOW
                          for e in watcher.read()):
                pass


def check():
    data = cached()
    if data.get("retry_after", 0) > time.time():
        return
    (RUNTIME / "checking").touch()
    errors = []
    for name, fetch in (("proposal", proposal), ("system", system)):
        try:
            data[name] = fetch(data.get(name, {}))
        except update.GitHubError as error:
            print(f"{name}: {error}", file=sys.stderr)
            errors.append(error.summary)
            if error.retry_after:
                data["retry_after"] = error.retry_after
                break
        except (update.UpdateError, subprocess.SubprocessError, OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
            print(f"{name}: {error}", file=sys.stderr)
            errors.append(str(error) if isinstance(error, update.UpdateError) else "Could not verify " + name)
    data["error"] = " · ".join(dict.fromkeys(errors))
    if not errors:
        data["checked"] = time.time()
        data.pop("retry_after", None)
    update.atomic_json(CACHE, data)


def view(data, checking, manual):
    classes, lines = [], []
    if checking or manual:
        classes.append("manual" if manual else "checking")
        lines.append("Checking for updates…")
    if data.get("error"):
        lines.append(data["error"])
        if data.get("retry_after", 0) > time.time():
            lines.append(datetime.fromtimestamp(data["retry_after"]).strftime("Retry after %H:%M"))
    for section in ("proposal", "system"):
        status = data.get(section, {})
        if status.get("text"):
            lines.append(status["text"])
        if status.get("attention") and "attention" not in classes:
            classes.append("attention")
    if data.get("checked"):
        lines.append(datetime.fromtimestamp(data["checked"]).strftime("Last checked %a %d %b · %H:%M"))
    elif not lines:
        lines.append("Click to check for updates")
    return {"text": "●", "tooltip": "\n".join(lines), "class": classes}


def links(data):
    result = {}
    pr = data.get("proposal", {})
    if pr.get("pr"):
        result["Open update PR"] = f"{WEB}/pull/{int(pr['pr'])}"
    if pr.get("run"):
        result["View proposal CI run"] = f"{WEB}/actions/runs/{int(pr['run'])}"
    main = data.get("system", {})
    if main.get("run"):
        result["View main CI run"] = f"{WEB}/actions/runs/{int(main['run'])}"
    return result


def main(args):
    RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=True)
    manual = RUNTIME / "manual"
    checking = RUNTIME / "checking"
    if args == ["manual"]:
        manual.touch()
        result = subprocess.run(["systemctl", "--user", "start", "--no-block", UNIT])
        if result.returncode:
            manual.unlink(missing_ok=True)
        return result.returncode
    if args == ["check"]:
        check()
    elif args == ["finish"]:
        if os.environ.get("SERVICE_RESULT", "success") != "success":
            data = cached()
            data["error"] = "Update check interrupted · click to retry"
            update.atomic_json(CACHE, data)
        manual.unlink(missing_ok=True)
        checking.unlink(missing_ok=True)
    elif args == ["watch"]:
        watch()
    elif args == ["choices"]:
        print(json.dumps([{"label": label, "target": url} for label, url in links(cached()).items()]
                         or [{"label": "No update links yet"}]))
    elif args == ["status"]:
        print(json.dumps(view(cached(), checking.exists(), manual.exists())))
    elif len(args) == 2 and args[0] == "apply":
        url = json.loads(args[1])
        if url in links(cached()).values():
            subprocess.Popen(["xdg-open", url])
    else:
        raise ValueError("Unknown indicator action")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
