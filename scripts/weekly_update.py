"""Watch the Friday proposal without changing the checkout or activating a system."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import socket
import subprocess
import sys
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import update

ZONE = ZoneInfo("America/Sao_Paulo")
BRANCH = "automation/flake-update"
WEB = f"https://github.com/{update.REPOSITORY}"

NOTIFY = ["notify-send", "--app-name=Dotfiles", "--icon=system-software-update",
          "--category=x-dotfiles.weekly-update", "--urgency=normal", "--expire-time=0"]


@dataclass(frozen=True)
class Notice:
    key: str
    title: str
    body: str
    button: str = ""
    url: str = ""


@dataclass(frozen=True)
class Proposal:
    status: str
    notice: Notice | None = None
    number: int | None = None
    merge_sha: str | None = None


def window(now):
    friday = now.replace(hour=21, minute=0, second=0, microsecond=0)
    friday -= timedelta(days=(now.weekday() - 4) % 7)
    if now < friday:
        friday -= timedelta(weeks=1)
    return friday, friday + timedelta(days=2)


def latest_run(workflow, **filters):
    query = urlencode({**filters, "per_page": 1})
    runs = update.api_json(f"actions/workflows/{workflow}/runs?{query}")["workflow_runs"]
    return runs[0] if runs else None


def open_proposal(pr):
    number, sha = pr["number"], pr["head"]["sha"]
    ci = latest_run(update.WORKFLOW, event="pull_request", head_sha=sha, branch=BRANCH)
    status = "pending"
    if ci:
        result = ci["conclusion"] or ci["status"]
        if result in {"action_required", "waiting"}:
            status = "approval"
        elif ci["status"] == "completed":
            status = "failed"
            if result == "success":
                jobs = update.pages(f"actions/runs/{ci['id']}/attempts/{ci['run_attempt']}/jobs", "jobs")
                try:
                    update.validate_jobs(jobs)
                    status = "ready"
                except update.UpdateError:
                    pass
    else:
        # Some approval gates create a check suite before there is a workflow run.
        suites = update.pages(f"commits/{sha}/check-suites", "check_suites")
        if any(s["app"]["slug"] == "github-actions" and s["conclusion"] == "action_required" for s in suites):
            status = "approval"
    if status == "pending":
        return Proposal(status, number=number)
    title, detail = {
        "ready": ("Friday update is ready for review", "Package checks passed."),
        "approval": ("Friday update needs attention", "GitHub is waiting for approval to run checks."),
        "failed": ("Friday update needs attention", "Required checks did not pass."),
    }[status]
    return Proposal(status, Notice(f"pr:{number}:{sha}:{status}", title, f"PR #{number} · {detail}",
                                   "Open pull request", f"{WEB}/pull/{number}"), number)


def scheduled_workflow(start):
    midnight = start.replace(hour=0).astimezone(timezone.utc)
    return latest_run("update.yml", branch="main", event="schedule", created=">=" + midnight.isoformat())


def proposal_status(start, run):
    query = urlencode({"head": f"{update.REPOSITORY.split('/')[0]}:{BRANCH}", "base": "main"})
    opened = update.api_json(f"pulls?{query}&state=open&per_page=1")
    if opened:
        return open_proposal(opened[0])
    if not run or run["status"] != "completed":
        return Proposal("waiting")
    if run["conclusion"] != "success":
        return Proposal("workflow-failed")
    closed = update.api_json(f"pulls?{query}&state=closed&sort=created&direction=desc&per_page=1")
    if closed and datetime.fromisoformat(closed[0]["closed_at"]) >= start.replace(hour=0):
        pr = closed[0]
        if pr["merged_at"]:
            return Proposal("merged", number=pr["number"], merge_sha=pr["merge_commit_sha"])
        return Proposal("closed", number=pr["number"])
    # A successful weekly workflow exits with no PR only when inputs are unchanged.
    return Proposal("unchanged")


def tested_system(proposal, state):
    sha = update.api_json("git/ref/heads/main")["object"]["sha"]
    if proposal.merge_sha and proposal.merge_sha != sha:
        comparison = update.api_json(f"compare/{proposal.merge_sha}...{sha}")
        if comparison["status"] != "ahead":
            raise update.UpdateError("Waiting for main to include the merged proposal.")
    label = update.system_label(update.evidence(sha)["system_path"], state)
    title, detail = {
        "active": ("Friday check complete", "Your laptop is up to date."),
        "scheduled for next boot": ("Update scheduled for next boot", "The tested system is selected for your next boot."),
        "prepared; run up to review": ("NixOS update ready", "The tested system is prepared. Run up to review it."),
        "available; run up to review": ("NixOS update ready", "A tested system is available. Run up to review it."),
    }[label]
    return Notice(f"{sha}:{label}", title, detail)


def show(notice):
    if not notice.url:
        update.run(*NOTIFY, notice.title, notice.body)
        return
    # Type=notify returns after SwayNC accepts delivery. Only the transient
    # service waits for the button, so the updater can release its file lock.
    update.run("systemd-run", "--user", "--quiet", "--collect", "--service-type=notify",
               "--property=TimeoutStartSec=20s", "--property=PartOf=graphical-session.target",
               "--setenv=PATH", sys.executable, str(Path(__file__).resolve()),
               notice.title, notice.body, notice.button, notice.url)


def action_popup(title, body, button, url):
    with subprocess.Popen([*NOTIFY, "--print-id", f"--action=open={button}",
                           title, body], stdout=subprocess.PIPE, text=True) as process:
        notification_id = process.stdout.readline().strip()
        if not notification_id.isdecimal() or int(notification_id) == 0:
            process.terminate()
            raise update.UpdateError("The desktop did not accept the notification.")
        address = os.environ["NOTIFY_SOCKET"]
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as channel:
            channel.sendto(b"READY=1", "\0" + address[1:] if address.startswith("@") else address)
        if process.stdout.readline().strip() == "open":
            update.run("brave", url, capture=False)


def poll(week, state, start):
    run = scheduled_workflow(start)
    failed = run and run["status"] == "completed" and run["conclusion"] != "success"
    if failed:
        key = f"{run['id']}:{run['run_attempt']}"
        if week.get("failed_run") != key:
            show(Notice(key, "Friday update check failed", "GitHub could not complete the weekly proposal.",
                        "Open workflow run", f"{WEB}/actions/runs/{run['id']}"))
            week["failed_run"] = key
    else:
        week.pop("failed_run", None)
    proposal = proposal_status(start, run)
    settled = proposal.status in {"merged", "closed", "unchanged"}
    week["awaiting_review"] = False
    if proposal.status in {"waiting", "workflow-failed"}:
        return
    notice = proposal.notice
    try:
        system = tested_system(proposal, state)
    except (update.UpdateError, subprocess.CalledProcessError) as error:
        print(f"Desktop update verification deferred: {error}", file=sys.stderr)
        system = None  # Main CI or network failures must not hide actionable PRs.
    if proposal.status == "unchanged" and system is None and not week.get("no_changes"):
        show(Notice("unchanged", "Friday check complete",
                    "No dependency changes this week. Verification of the current desktop revision is pending."))
        week["no_changes"] = True
    new_pr = notice and week.get("proposal_notice") != notice.key
    new_system = system and state.get("notified") != system.key
    actionable = system and not system.key.endswith(":active")
    daily = state.get("daily_notice", {})
    reported_this_week = system and (week.get("system_reported") == system.key or
                                     (daily.get("key") == system.key and daily["at"] >= start.timestamp()))
    if new_pr:
        body = notice.body
        if actionable:
            body += "\n" + system.body
        show(Notice(notice.key, notice.title, body, notice.button, notice.url))
        week["proposal_notice"] = notice.key
        if actionable:
            state["notified"] = system.key
    elif actionable and (new_system or (settled and not reported_this_week)):
        body = system.body
        if proposal.status == "unchanged":
            body += "\nNo new dependency changes this week."
        button = url = ""
        if proposal.number and not settled:
            body += f"\nWeekly PR #{proposal.number} is still open."
            button, url = "Open pull request", f"{WEB}/pull/{proposal.number}"
        show(Notice(system.key, system.title, body, button, url))
        state["notified"] = system.key
    elif settled and system and not actionable:
        body = {"unchanged": "No dependency changes this week.", "closed": f"PR #{proposal.number} was closed.",
                "merged": f"PR #{proposal.number} was merged."}[proposal.status]
        if not (proposal.status == "unchanged" and week.get("no_changes")):
            show(Notice(system.key, system.title, body + " " + system.body))
        state["notified"] = system.key
    if actionable and (new_pr or new_system or settled or reported_this_week):
        week["system_reported"] = system.key
    week["awaiting_review"] = bool(notice and week.get("proposal_notice") == notice.key)
    week["done"] = bool(settled and system)


def monitor(directory, now=None):
    now = (now or datetime.now(ZONE)).astimezone(ZONE)
    start, cutoff = window(now)
    state = update.read_state(directory)
    week = state.get("friday", {})
    date = start.date().isoformat()
    if week.get("date") != date:
        if now > cutoff and now.date() != cutoff.date() and os.getenv("TRIGGER_UNIT") != "weeklyUpdate.timer":
            return
        week = {"date": date}
        state["friday"] = week
    if week.get("done"):
        return
    if now >= cutoff:
        if not week.get("awaiting_review") and not week.get("failed_run"):
            show(Notice("cutoff", "Friday update check incomplete",
                        "The weekly check ended before an outcome could be confirmed."))
        week["done"] = True
    else:
        try:
            poll(week, state, start)
        finally:
            # Preserve deliveries even if a later request fails or the laptop goes offline.
            update.atomic_json(directory / "state.json", state)
        return
    update.atomic_json(directory / "state.json", state)


if __name__ == "__main__":
    action_popup(*sys.argv[1:])
