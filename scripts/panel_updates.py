"""Read GitHub update status for the panel. Only the systemd oneshot contacts GitHub."""
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlencode
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
    if run["status"] in {"requested", "queued", "pending"}:
        return "CI pending"
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
    if prs[0]["draft"]:
        return {}
    result = pr_status(prs[0], previous)
    if result:
        result["text"] = f"Friday update · #{result['pr']} · {result['status']}"
    return result


def pr_run(pr):
    head = pr["head"]
    query = urlencode({"event": "pull_request", "branch": head["ref"], "head_sha": head["sha"]})
    runs = update.pages(f"actions/workflows/{update.WORKFLOW}/runs?{query}", "workflow_runs")
    for run in runs:
        associated = run["pull_requests"]
        if any(p["number"] == pr["number"] for p in associated):
            return run
        # GitHub can omit PR associations for fork runs. Disambiguate branches
        # with the same name and commit using their source repository.
        source = run.get("head_repository") or {}
        if not associated and head["repo"] and source.get("id") == head["repo"]["id"]:
            return run
    return None


def pr_status(pr, previous):
    sha = pr["head"]["sha"]
    run = pr_run(pr)
    label = ci_status(run)
    if not run:
        suites = update.pages(f"commits/{sha}/check-suites", "check_suites")
        if any(s["app"]["slug"] == "github-actions" and s["conclusion"] == "action_required"
               and (not s.get("pull_requests") or any(p["number"] == pr["number"] for p in s["pull_requests"]))
               for s in suites):
            label = "CI needs approval"
    key = [pr["number"], sha, run_key(run)] if run else None
    if label == "passed" and previous.get("verified") != key:
        jobs = update.pages(f"actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs", "jobs")
        try:
            update.validate_jobs(jobs)
        except update.UpdateError:
            label = "CI failed"
    result = {"pr": pr["number"]}
    if run:
        result["run"] = run["id"]
    attention = label in {"CI failed", "CI needs approval"}
    if label == "passed":
        # Reviews and branch rules can change without a new CI run.
        detail = update.api_json(f"pulls/{pr['number']}")
        if detail["state"] != "open" or detail["draft"] or detail["base"]["ref"] != "main":
            return {}
        if detail["head"]["sha"] != sha:
            return {"pr": pr["number"], "status": "CI pending", "attention": False}
        result["verified"] = key
        state = detail.get("mergeable_state")
        attention = True
        if detail.get("mergeable") is False or state == "dirty":
            label = "CI passed · merge blocked by conflicts"
        elif state == "behind":
            label = "CI passed · merge blocked until branch is updated"
        elif state == "blocked":
            label = "CI passed · merge blocked by GitHub"
        elif detail.get("mergeable") and state in {"clean", "has_hooks", "unstable"}:
            label = "CI passed · ready to merge"
        else:
            label = "CI passed · GitHub checking mergeability"
            attention = False
    return {**result, "status": label, "attention": attention}


def ordinary_prs(previous):
    prs = update.pages("pulls?state=open&base=main")
    old = {item["pr"]: item for item in previous}
    result = []
    for pr in prs:
        head = pr["head"]
        if pr["draft"] or (head["ref"] == BRANCH and (head["repo"] or {}).get("full_name") == update.REPOSITORY):
            continue
        status = pr_status(pr, old.get(pr["number"], {}))
        if not status:
            continue
        status["title"] = pr["title"]
        status["text"] = f"Pull request · #{pr['number']} · {pr['title']} · {status['status']}"
        result.append(status)
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
    return {**result, "verified": key, "path": path, "expires": expires}


def active_revision():
    try:
        return json.loads(update.run("/run/current-system/sw/bin/nixos-version", "--json")).get("configurationRevision")
    except (OSError, ValueError, subprocess.CalledProcessError):
        return None


def system_view(desktop):
    if not desktop.get("verified") or not desktop.get("path"):
        return desktop
    state = update.read_state(STATE)
    local = update.system_label(desktop["path"], state)
    text = {"active": "Laptop up to date", "scheduled for next boot": "Update scheduled for next boot"}.get(local)
    applied = state.get("last_system_action", {})
    if not text and (applied.get("sha"), applied.get("path"), applied.get("choice")) == (
            desktop["verified"][0], desktop["path"], "switch"):
        if active_revision() in (None, applied["sha"]):
            text = "Latest tested main already applied · a different system build is active"
    if not text:
        repo = Path(os.environ.get("DOTFILES_REPO", Path.home() / ".dotfiles")).resolve()
        try:
            update.clean_checkout(repo)
        except update.UpdateError as error:
            text = "Tested main available · " + str(error)
        except (OSError, subprocess.CalledProcessError):
            text = "Tested main available · checkout unavailable for updating"
    return {**desktop, "text": text or "Tested system update ready · run up", "attention": text is None}


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
    for name, fetch in (("proposal", proposal), ("system", system), ("pull_requests", ordinary_prs)):
        try:
            data[name] = fetch(data.get(name, [] if name == "pull_requests" else {}))
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
    proposals = (data.get("proposal", {}), *data.get("pull_requests", []))
    prs = [item for item in proposals if item.get("pr")]
    desktop = system_view(data.get("system", {}))
    update_ready = desktop.get("verified") and desktop.get("attention")
    if update_ready or any(item.get("attention") for item in prs):
        classes.append("attention")
    elif prs:
        classes.append("pending")
    for status in (*proposals, desktop):
        if status.get("text"):
            lines.append(status["text"])
    if data.get("checked"):
        lines.append(datetime.fromtimestamp(data["checked"]).strftime("Last checked %a %d %b · %H:%M"))
    elif not lines:
        lines.append("Click to check for updates")
    return {"text": "●", "tooltip": "\n".join(lines), "class": classes}


def links(data):
    result = {}
    pr = data.get("proposal", {})
    if pr.get("pr"):
        result[f"Friday update · #{int(pr['pr'])}"] = f"{WEB}/pull/{int(pr['pr'])}"
    if pr.get("run"):
        result["View proposal CI run"] = f"{WEB}/actions/runs/{int(pr['run'])}"
    for item in data.get("pull_requests", []):
        number = int(item["pr"])
        result[f"Pull request · #{number} · {item['title']}"] = f"{WEB}/pull/{number}"
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
