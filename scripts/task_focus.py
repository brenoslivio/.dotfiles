"""Persist focus intervals and calendar deadlines for the Markdown tasks notepad."""
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, time as daytime, timedelta
import fcntl
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from uuid import uuid4
from zoneinfo import ZoneInfo

import task_board
import task_plan
from panel_tasks import BLOCK, entries, note_key, read_lines, section_body, task_label, update_note, write_draft, legacy_drafts

CONTROLS = {"pause", "resume", "finish", "extend"}


def source_name(note):
    path = note.absolute()
    return "~/" + str(path.relative_to(Path.home())) if path.is_relative_to(Path.home()) else str(path)


def identify(note, state, base, row):
    """Anchor the selected saved line, preserving external edits and line endings."""
    new_block = "task-" + uuid4().hex[:12]

    def select(lines):
        section, body = section_body(lines)
        if body != base:
            raise ValueError("The note changed. Reopen Tasks to use its latest version.")
        index = section.start + row
        items = {i: text for i, indent, text in entries(lines) if indent}
        title = task_label(items.get(index, ""))
        if row < 0 or not title:
            raise ValueError("Place the cursor on an indented task bullet.")
        match = BLOCK.search(items[index])
        if match:
            block = match[1]
            if sum(bool(m and m[1] == block) for m in map(BLOCK.search, lines)) != 1:
                raise ValueError("This block ID occurs twice in the note. Give each task a unique ID.")
        else:
            block = new_block
            line = lines[index]
            content = line.rstrip()
            lines[index] = content + " ^" + block + line[len(content):]
        return block, title, section_body(lines)[1], not match

    state.mkdir(parents=True, exist_ok=True)
    with (state / (note_key(note) + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        block, title, body, added = select(read_lines(note))
        if added:
            def edit(lines):
                nonlocal block, title, body
                block, title, body, _ = select(lines)
            update_note(note, edit)
    return block, title, body


def wall_timestamp(day, clock, zone):
    naive = datetime.strptime(f"{day} {clock}", "%Y-%m-%d %H:%M")
    stamp = int(naive.replace(tzinfo=zone).timestamp())
    if datetime.fromtimestamp(stamp, zone).replace(tzinfo=None) != naive:
        raise ValueError("That local time does not exist on this date.")
    return stamp


def duration(value, now, zone=None):
    value = value.strip().lower()
    if not value:
        return None
    if re.fullmatch(r"\d{1,2}:\d{2}", value):
        today = datetime.fromtimestamp(now, zone).date()
        end = wall_timestamp(today, value, zone)
        if end <= now:
            end = wall_timestamp(today + timedelta(days=1), value, zone)
        return end - now
    match = re.fullmatch(r"(?:(\d+)\s*h(?:ours?)?\s*)?(?:(\d+)\s*(?:m(?:in(?:utes?)?)?)?)?", value)
    if match:
        minutes = int(match[1] or 0) * 60 + int(match[2] or 0)
        if minutes > 0:
            return minutes * 60
    raise ValueError("Enter a positive duration (37m, 1h 15m) or an end time (14:40).")


def deadline(day, clock, zone):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ValueError("Enter a date as YYYY-MM-DD.")
    date.fromisoformat(day)
    if not clock:
        return {"date": day}
    if not re.fullmatch(r"\d{2}:\d{2}", clock):
        raise ValueError("Enter a 24-hour time as HH:MM.")
    return {"at": wall_timestamp(day, clock, zone)}


@contextmanager
def locked(path):
    # Lock the stable directory inode since atomic replacement changes the file inode.
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def read_history(path):
    try:
        history = json.loads(path.read_text())
    except FileNotFoundError:
        return {"version": 1, "sessions": [], "deadlines": {}}
    if not isinstance(history, dict) or history.get("version") != 1 or not isinstance(
            history.get("sessions"), list) or not isinstance(history.get("deadlines"), dict):
        raise ValueError("Unrecognized task-history.json format.")
    return history


def write_history(path, history):
    with tempfile.NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", delete=False) as stream:
        temp = Path(stream.name)
        try:
            json.dump(history, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)


def active_session(history):
    sessions = history["sessions"]
    if sessions and sessions[-1]["status"] != "finished":
        return sessions[-1]
    return None


def stop_interval(session, end):
    start = session.pop("running_since", None)
    if start is not None:
        end = max(start, end)
        session["intervals"].append([start, end])
        session["focused_seconds"] += end - start


def cutoff(session):
    if session and session["status"] == "running" and session["planned_seconds"] is not None:
        return session["running_since"] + session["planned_seconds"] - session["focused_seconds"]
    return None


def expire(history, now):
    session = active_session(history)
    end = cutoff(session)
    if end is None or end > now:
        return None
    stop_interval(session, end)
    session.update(status="expired", ended_at=end)
    return session


def finish(session, now):
    stop_interval(session, now)
    session.update(status="finished", ended_at=session.get("ended_at", now))


def change_session(session, action, req, now, zone):
    if not session or session["id"] != req.get("session"):
        raise ValueError("The focus session has changed.")
    status = session["status"]
    if "expiry" in req and (status != "expired" or session.get("ended_at") != req["expiry"]):
        raise ValueError("That timer notification has already been handled.")
    if action == "finish":
        finish(session, now)
    elif action == "pause" and status == "running":
        stop_interval(session, now)
        session["status"] = "paused"
    elif action == "resume" and status == "paused":
        session.update(status="running", running_since=now)
    elif action == "extend" and status == "expired":
        extra = duration(req["duration"], now, zone)
        if extra is None:
            raise ValueError("Enter the extra time to focus.")
        session["planned_seconds"] += extra
        session.update(status="running", running_since=now)
        del session["ended_at"]
    else:
        raise ValueError("This control no longer applies to the current session.")


def settle_edit(note, path, history, pending):
    """Replay history effects only for note edits that reached disk."""
    if not pending.exists():
        return
    effect = json.loads(pending.read_text())
    lines = read_lines(note)
    section_body(lines)
    items = {n.key: n for n in task_board.tree(lines)}
    deleted = set(effect["removed"]) - items.keys()
    completed = {key for key in effect["completed"] if key in items and items[key].done}
    deadlines = history["deadlines"].get(source_name(note), {})
    for key in deleted:
        deadlines.pop(key, None)
    session = active_session(history)
    if session and session["id"] == effect["session"] and session["task"] in deleted | completed:
        expire(history, effect["at"])
        finish(session, effect["at"])
    write_history(path, history)
    pending.unlink()


def board_edit(note, state, path, history, req, now, pending):
    session = active_session(history)
    state.mkdir(parents=True, exist_ok=True)
    result = {}

    def edit(lines):
        result.update(task_board.edit(lines, req))
        if result["removed"] or result["completed"]:
            write_draft(pending, {**result, "at": now, "session": session["id"] if session and
                                  session["source"] == source_name(note) else None})

    with (state / (note_key(note) + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        update_note(note, edit)
        settle_edit(note, path, history, pending)
    return result


def board_anchor(note, state, req):
    state.mkdir(parents=True, exist_ok=True)
    result = {}
    def resolve(lines):
        row = task_board.target(task_board.tree(lines), req["target"])
        if req["action"] == "start" and (not row.depth or row.done):
            raise ValueError("Select an open task to focus.")
        if req["action"] == "planAdd" and (not row.depth or row.done):
            raise ValueError("Choose an open task for today.")
        result.update(key=task_board.attach(lines, row), title=row.title)
    with (state / (note_key(note) + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if req["target"]["key"].startswith(":"):
            update_note(note, resolve)
        else:
            resolve(read_lines(note))
    return result["key"], result["title"]


def history_day(history, day, now):
    start = int(datetime.combine(day, daytime.min).timestamp())
    stop = int(datetime.combine(day + timedelta(days=1), daytime.min).timestamp())
    records = []
    earlier = later = None
    for s in reversed(history["sessions"]):
        started = s["started_at"]
        seconds = 0
        included = start <= started < stop
        spans = [(started, started), *s["intervals"]]
        running = s.get("running_since")
        total = s["focused_seconds"]
        if running is not None:
            end = min(now, cutoff(s) or now)
            spans.append((running, end))
            total += max(0, end - running)
            included |= start <= now < stop and running <= now < (cutoff(s) or stop)
        for a, b in spans:
            overlap = max(0, min(b, stop) - max(a, start))
            included |= overlap > 0
            seconds += overlap
            last = max(a, b - 1)
            if a < start:
                candidate = min(start - 1, last)
                earlier = candidate if earlier is None else max(earlier, candidate)
            if last >= stop:
                candidate = max(a, stop)
                later = min(later if later is not None else candidate, candidate)
        if included:
            records.append({"id": s["id"], "title": s["title"], "started": started, "seconds": seconds,
                            "total": total, "status": s["status"], "running": running, "cutoff": cutoff(s)})
    def local_date(stamp):
        return datetime.fromtimestamp(stamp).date().isoformat() if stamp is not None else ""
    records.sort(key=lambda record: record["started"], reverse=True)
    return {"day": day.isoformat(), "start": start, "stop": stop, "asOf": now, "records": records,
            "earlier": local_date(earlier), "later": local_date(later)}


def edit_history(history, req):
    sessions = history["sessions"]
    if req["action"] == "deleteRecord":
        for i, s in enumerate(sessions):
            if s["id"] == req["recordId"]:
                if s["status"] != "finished":
                    raise ValueError("Finish the session before deleting its record.")
                sessions.pop(i)
                return {"undo": {"record": s, "next": sessions[i]["id"] if i < len(sessions) else None}}
        raise ValueError("This focus record has already been removed.")
    receipt = req["undo"]
    s = receipt["record"]
    if s["status"] != "finished" or "running_since" in s:
        raise ValueError("Only a finished record can be restored.")
    if (not all(isinstance(s.get(k), str) for k in ("id", "title", "task", "source"))
            or not all(isinstance(s.get(k), int) for k in ("started_at", "ended_at", "focused_seconds"))
            or "planned_seconds" not in s or not isinstance(s.get("intervals"), list)
            or any(not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(t, int) for t in pair)
                   or pair[0] > pair[1] for pair in s["intervals"])):
        raise ValueError("The deleted record is incomplete.")
    if not any(other["id"] == s["id"] for other in sessions):
        # An active session must stay last, even if it started after the deletion.
        index = next((i for i, other in enumerate(sessions) if other["id"] == receipt["next"]
                      or other["status"] != "finished" or other["started_at"] > s["started_at"]), len(sessions))
        sessions.insert(index, s)
    return {}


def deadline_hint(rows, deadlines, today):
    names = {r.key: r.title for r in rows}
    groups = {}
    for row in rows:
        due = deadlines.get(row.key)
        if due:
            days = (date.fromisoformat(due["date"]) - today).days
            if days > 2:
                continue
            label = row.title + (" · " + names[row.project] if row.depth else " · Project")
            if days < 0:
                label += f" · {-days} day{'s' if days < -1 else ''} late"
            group = "Overdue" if days < 0 else ("Due today", "Tomorrow", "Day after tomorrow")[days]
            groups.setdefault(group, []).append((days, label))
    level = "urgent" if "Overdue" in groups or "Due today" in groups else "soon" if groups else ""
    hint = "\n\n".join(group + "\n" + "\n".join(label for _, label in sorted(groups[group]))
                       for group in ("Overdue", "Due today", "Tomorrow", "Day after tomorrow") if group in groups)
    return {"level": level, "text": hint}


def apply(note, state, path, req, now=None):
    zone = ZoneInfo(req["zone"]) if req.get("zone") else None
    action = req["action"]
    with locked(path):
        now = int(time.time()) if now is None else now
        history = read_history(path)
        if action == "historyDay":
            return history_day(history, date.fromisoformat(req["day"]), now)
        pending = state / (note_key(note) + ".board-pending.json")
        settle_edit(note, path, history, pending)
        if action == "syncCompletion":
            session = active_session(history)
            if session and session["id"] == req["session"] and session["source"] == source_name(note):
                if any(row.key == session["task"] and row.done for row in task_board.tree(read_lines(note))):
                    last = session.get("running_since", session["intervals"][-1][1] if session["intervals"] else session["started_at"])
                    ended = max(last, min(now, int(note.stat().st_mtime)))
                    expire(history, ended)
                    finish(session, ended)
                    write_history(path, history)
            return {}
        expired = expire(history, now)
        if expired:
            write_history(path, history)
        session = active_session(history)
        if action == "tick":
            return {"expired": expired}
        if action in task_plan.ACTIONS:
            day = datetime.fromtimestamp(now).date().isoformat()
            if req["day"] != day:
                raise ValueError("A new day has started. Review today's plan.")
            plan_path = path.with_name("task-plan.json")
            data = task_plan.read(plan_path)
            days = data["sources"].setdefault(source_name(note), {})
            result = {}
            if action == "planAdd":
                result["key"], _ = board_anchor(note, state, req)
            items = [row.display() for row in task_board.tree(read_lines(note))]
            plan = task_plan.project(days, day, items)
            entry = days.setdefault(day, {"tasks": [], "dismissed": []})
            task_plan.edit(entry, plan, {**req, **result}, items)
            try:
                write_history(plan_path, data)
            except OSError as exc:
                return {**result, "error": f"Could not save today's plan: {exc}"}
            return result
        if action in task_board.ACTIONS:
            return board_edit(note, state, path, history, req, now, pending)
        if action in {"deleteRecord", "undoDelete"}:
            result = edit_history(history, req)
        elif action in CONTROLS:
            change_session(session, action, req, now, zone)
            result = {}
        elif action in ("start", "deadline", "clearDeadline"):
            if action == "start" and (session and session["id"]) != (req.get("session") or None):
                raise ValueError("The focus session changed. Check the current task and try again.")
            planned = duration(req["duration"], now, zone) if action == "start" else None
            due = deadline(req["date"].strip(), req.get("time", "").strip(), zone) if action == "deadline" else None
            if "target" in req:
                if "expectedDue" in req:
                    current = view(note, history, zone, now)["deadlines"].get(req["target"]["key"])
                    if req["expectedDue"] != current:
                        raise ValueError("The deadline changed. Reopen the date picker to review it.")
                block, title = board_anchor(note, state, req)
                result = {"key": block}
            else:
                block, title, body = identify(note, state, req["base"], req["line"])
                result = {"body": body, "task": block}
            source = source_name(note)
            if action == "start":
                if session:
                    finish(session, now)
                history["sessions"].append({
                    "id": uuid4().hex, "source": source, "task": block, "title": title,
                    "started_at": now, "planned_seconds": planned, "focused_seconds": 0,
                    "intervals": [], "running_since": now, "status": "running",
                })
            else:
                deadlines = history["deadlines"].setdefault(source, {})
                if due:
                    deadlines[block] = {**due, "title": title}
                else:
                    deadlines.pop(block, None)
        else:
            raise ValueError("Unknown focus action.")
        try:
            write_history(path, history)
        except OSError as exc:
            # The note may already contain its new block ID. Keep the editor in sync for retry.
            return {**result, "error": f"Could not save task history: {exc}"}
        return result


def view(note, history, zone, now, plan_path=None):
    board_error = ""
    try:
        rows = task_board.tree(read_lines(note))
    except (OSError, ValueError) as exc:
        rows, board_error = [], str(exc)
    titles = {row.key: row.title for row in rows if not row.done}
    source = source_name(note)
    today = datetime.fromtimestamp(now).date()
    midnight = int(datetime.combine(today, daytime.min).timestamp())
    totals, daily = Counter(), Counter()
    today_seconds = 0
    for s in history["sessions"]:
        seconds = sum(max(0, min(end, now) - max(start, midnight)) for start, end in s["intervals"])
        today_seconds += seconds
        if s["source"] == source:
            key = s["task"]
            totals[key] += s["focused_seconds"]
            daily[key] += seconds
    deadlines = {}
    for key, due in history["deadlines"].get(source, {}).items():
        if key not in titles:
            continue
        moment = datetime.fromtimestamp(due["at"], zone) if "at" in due else None
        deadlines[key] = {"date": moment.date().isoformat() if moment else due["date"],
                          "time": moment.strftime("%H:%M") if moment else "", "title": titles[key]}
    active = active_session(history)
    focus = None
    if active:
        same_note = active["source"] == source
        focus = {k: active.get(k) for k in ("id", "task", "title", "status", "running_since", "planned_seconds", "focused_seconds")}
        if same_note:
            focus["title"] = titles.get(active["task"], active["title"])
        focus.update(cutoff=cutoff(active), sameNote=same_note)
    items = [n.display() for n in rows]
    plan = {"tasks": [], "carry": []}
    if plan_path is not None:
        try:
            days = task_plan.read(plan_path)["sources"].get(source, {})
            plan = task_plan.project(days, today.isoformat(), items)
        except (ValueError, OSError) as exc:
            plan["error"] = str(exc)
    return {"active": focus, "totals": totals, "today": daily, "midnight": midnight, "plan": plan,
            "todaySeconds": today_seconds, "localDay": today.isoformat(),
            "urgency": deadline_hint(rows, deadlines, datetime.fromtimestamp(now, zone).date()),
            "deadlines": deadlines, "zone": zone.key if zone else "", "items": items,
            "boardError": board_error}


def signature(path):
    try:
        stat = path.stat()
        return stat.st_ino, stat.st_mtime_ns, stat.st_size
    except FileNotFoundError:
        return None


def watch(note, state, path, zone_name):
    zone = ZoneInfo(zone_name) if zone_name else None
    previous = end = None
    children = []
    pending = state / (note_key(note) + ".board-pending.json")
    plan_path = path.with_name("task-plan.json")
    while True:
        try:
            now = int(time.time())
            key = (signature(path), signature(plan_path), signature(note), signature(state), date.today(), datetime.fromtimestamp(now, zone).date())
            if key != previous or (end is not None and now >= end):
                history = read_history(path)
                session = active_session(history)
                value = view(note, history, zone, now, plan_path)
                if session and session["source"] == source_name(note) and any(
                        n["key"] == session["task"] and n["done"] for n in value["items"]):
                    apply(note, state, path, {"action": "syncCompletion", "session": session["id"]})
                    continue
                end = cutoff(session)
                if pending.exists() or (end is not None and now >= end):
                    expired = apply(note, state, path, {"action": "tick"})["expired"]
                    if expired:
                        children.append(subprocess.Popen([sys.executable, __file__, "notify", expired["id"],
                                                          str(expired["ended_at"]), expired["title"]],
                                                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL))
                    continue
                value["draft"] = (state / (note_key(note) + ".notepad.json")).exists()
                value["legacy"] = bool(legacy_drafts(note, state))
                print(json.dumps(value), flush=True)
                previous = key
        except (OSError, ValueError, KeyError, TypeError) as exc:
            if previous != str(exc):
                print(json.dumps({"error": str(exc)}), flush=True)
            previous = str(exc)
        children = [child for child in children if child.poll() is None]
        time.sleep(1)


if __name__ == "__main__":
    repo = Path(os.environ.get("DOTFILES_REPO") or Path.home() / ".dotfiles")
    path = repo / "config/quickshell/task-history.json"
    note = Path(os.environ.get("TASKS_FILE") or Path.home() / "Dropbox/Ikiru/Ikiru.md")
    state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "dotfiles/task-capture"
    if sys.argv[1] == "watch":
        watch(note, state, path, sys.argv[2])
    else:
        try:
            if sys.argv[1] == "notify":
                answer = subprocess.run(["notify-send", "--app-name=Desktop panel", "--icon=appointment-soon-symbolic", "--action=extend=Extend 5 min",
                                         "--action=finish=Finish", "--", "Focus time is up", html.escape(sys.argv[4])],
                                        text=True, capture_output=True).stdout.strip()
                if answer in ("extend", "finish"):
                    apply(note, state, path, {"action": answer, "duration": "5m", "session": sys.argv[2],
                                             "expiry": int(sys.argv[3])})
            else:
                req = json.loads(sys.stdin.readline())
                result = apply(note, state, path, req)
                if req.get("board"):
                    zone = ZoneInfo(req["zone"]) if req.get("zone") else None
                    result["view"] = view(note, read_history(path), zone, int(time.time()), path.with_name("task-plan.json"))
                print(json.dumps(result))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(json.dumps({"error": str(exc)}))
