"""Read and capture tasks in the Tasks section of the configured Markdown note."""
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time

from desktop_menu import dialog, notify


def task_section(lines):
    start = next((i + 1 for i, line in enumerate(lines) if re.fullmatch(r"##\s+Tasks\s*", line)), len(lines))
    end = next((i for i in range(start, len(lines)) if re.match(r"^#{1,6}\s", lines[i])), len(lines))
    return range(start, end)


def entries(lines):
    for i in task_section(lines):
        match = re.match(r"^([ \t]*)-[ \t]+(.+?)\s*$", lines[i])
        if match and match[2].strip():
            yield i, match[1], match[2].strip()


def project_names(lines):
    return [text for _, indent, text in entries(lines) if not indent]


def read_lines(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return stream.readlines()


def status(path):
    try:
        items = list(entries(read_lines(path)))
    except (OSError, UnicodeError):
        return {"text": "0", "tooltip": f"Task file unavailable: {html.escape(str(path))}\nRight-click to keep a draft"}
    tooltip = [("  ✓ " if indent else "• ") + html.escape(text) for _, indent, text in items]
    return {"text": str(sum(bool(indent) for _, indent, _ in items)),
            "tooltip": "\n".join([*tooltip, "Right-click to add or edit tasks"])}


def insert_task(lines, project, text):
    items = list(entries(lines))
    matches = [i for i, indent, name in items if not indent and name == project]
    if len(matches) != 1:
        raise ValueError("The project was renamed, removed, or appears more than once.")
    start, = matches
    end = next((i for i, indent, _ in items if i > start and not indent), task_section(lines).stop)
    indents = [indent for i, indent, _ in items if start < i < end and indent]
    if not indents:
        indents = [indent for _, indent, _ in items if indent]
    indent = min(indents, key=lambda value: len(value.expandtabs()), default="  ")
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    newline = "\r\n" if lines[start].endswith("\r\n") or any(line.endswith("\r\n") for line in lines) else "\n"
    trailing_newline = end < len(lines) or lines[-1].endswith(("\n", "\r"))
    if not lines[end - 1].endswith(("\n", "\r")):
        lines[end - 1] += newline
    lines.insert(end, indent + "- " + text + (newline if trailing_newline else ""))


def version(stat):
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def save_task(path, project, text, target=None):
    path = path.resolve(strict=True)
    if not os.access(path, os.W_OK):
        raise PermissionError("The task note is read-only.")
    # Re-read at submission so edits made while the editor was open are included.
    for _ in range(3):
        before = version(path.stat())
        lines = read_lines(path)
        if target is None:
            insert_task(lines, project, text)
        else:
            replace_task(lines, target, text)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".task-", delete=False,
                                         mode="w", encoding="utf-8", newline="") as stream:
            temp = Path(stream.name)
            try:
                stream.writelines(lines)
                stream.flush()
                os.fsync(stream.fileno())
                shutil.copystat(path, temp)
                os.utime(temp, None)
                if before == version(path.stat()):
                    os.replace(temp, path)
                    return
            finally:
                temp.unlink(missing_ok=True)
    raise ValueError("The note is changing. Try again after syncing.")


def project_tasks(lines, project):
    if project_names(lines).count(project) != 1:
        return []
    tasks, parents = [], []
    current = None
    for index, indent, text in entries(lines):
        if not indent:
            current = text
            parents.clear()
        elif current == project:
            depth = len(indent.expandtabs())
            while parents and parents[-1][0] >= depth:
                parents.pop()
            tasks.append((index, [p[1] for p in parents] + [text]))
            parents.append((depth, text))
    return tasks


def edit_choices(lines, project):
    tasks = project_tasks(lines, project)
    paths = [path for _, path in tasks]
    fingerprint = hashlib.sha256(json.dumps(paths).encode()).hexdigest()
    choices = []
    for position, (index, path) in enumerate(tasks):
        target = {"project": project, "path": path}
        label = " › ".join(path)
        if paths.count(path) > 1:
            # Identical siblings have no stable Markdown ID. Trust their position
            # only while the project's task list still matches the menu snapshot.
            target.update(position=position, snapshot=fingerprint)
            neighbor = paths[position - 1][-1] if position else project
            label += f"  (line {index + 1}, after {neighbor[:48]})"
        choices.append((label, target))
    return choices


def locate(lines, target):
    project = target["project"]
    for (index, _), (_, candidate) in zip(project_tasks(lines, project), edit_choices(lines, project)):
        if candidate == target:
            return index
    raise ValueError("The original task changed, disappeared, or is ambiguous.")


def replace_task(lines, target, text):
    index = locate(lines, target)
    line = lines[index]
    start = line.index(target["path"][-1], re.match(r"^[ \t]*-[ \t]+", line).end())
    end = start + len(target["path"][-1])
    lines[index] = line[:start] + text + line[end:]


def write_draft(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", delete=False) as stream:
        json.dump(data, stream)
    os.replace(stream.name, path)


def note_key(path):
    return hashlib.sha256(os.fsencode(path.absolute())).hexdigest()


def snapshot(path):
    try:
        return read_lines(path)
    except (OSError, UnicodeError):
        return []


def task_choices(path, state):
    choices = []
    lines = snapshot(path)
    projects = project_names(lines)
    if projects:
        add, edit = [], []
        choices.extend([{"label": "Add task…", "children": add}, {"label": "Edit task…", "children": edit}])
        for project in dict.fromkeys(projects):
            if projects.count(project) > 1:
                disabled = {"label": project + " (duplicate project)"}
                add.append(disabled)
                edit.append(disabled)
                continue
            add.append({"label": project, "target": {"action": "add", "project": project}})
            tasks = [{"label": label, "target": {"action": "edit", "target": target}}
                     for label, target in edit_choices(lines, project)]
            edit.append({"label": project, "children": tasks} if tasks else {"label": project + " (empty)"})
    else:
        choices.extend([{"label": "Add task…", "target": {"action": "add", "project": ""}}, {"label": "Edit task…"}])
    for file in sorted(state.glob(note_key(path) + ".edit-*.json")):
        draft = json.loads(file.read_text())
        choices.append({"label": "Resume edit · " + draft["text"], "target": {"action": "resume", "draft": file.name}})
    return choices


def save_dialog(path, state, action):
    key = note_key(path)
    lines = snapshot(path)
    mode = action["action"]
    if mode == "resume":
        filename = action["draft"]
        if not re.fullmatch(re.escape(key) + r"\.edit-[0-9a-f]{64}\.json", filename):
            raise ValueError("Unknown draft.")
        draft = state / filename
        previous = json.loads(draft.read_text())
        target = previous["target"]
        project = target["project"]
        try:
            locate(lines, target)
        except ValueError:
            options = [(p + " › " + label, t) for p in dict.fromkeys(project_names(lines))
                       for label, t in edit_choices(lines, p)]
            if not options:
                notify("Edit draft kept", "Reopen when the note and its tasks are available.")
                return
            choice = dialog("Recover edit draft", [label for label, _ in options],
                            message="The original task changed. Choose the task to replace.")
            if choice is None:
                return
            target = options[choice][1]
            project = target["project"]
    elif mode == "edit":
        target = action["target"]
        project = target["project"]
        identity = hashlib.sha256(json.dumps(target, sort_keys=True).encode()).hexdigest()
        draft = state / f"{key}.edit-{identity}.json"
        previous = json.loads(draft.read_text()) if draft.exists() else {}
    else:
        target = None
        project = action.get("project", "")
        draft = state / (key + ".json")
        previous = json.loads(draft.read_text()) if draft.exists() else {}
        if mode == "capture" and (projects := project_names(lines)):
            choice = dialog("Add task", projects, message="Choose a project")
            if choice is None:
                return
            project = projects[choice]
    title = ("Edit task" if target else "Add task") + (f" · {project}" if project else "")
    message = "Task" if project else "No projects available. Save keeps a local draft."
    answer = dialog(title, message=message, initial=previous.get("text", target["path"][-1] if target else ""))
    if answer is None or not answer.strip():
        return
    text = " ".join(answer.splitlines()).strip()
    write_draft(draft, {"project": project, "target": target, "text": text})
    try:
        if not project:
            raise ValueError("Open Add task again when the Tasks section is available.")
        save_task(path, project, text, target)
    except (OSError, UnicodeError, ValueError) as error:
        notify("Edit draft kept" if target else "Task kept as a draft", str(error))
        return
    draft.unlink()
    notify("Task edited" if target else "Task added", project)


def capture(path, state, action=None):
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / (note_key(path) + ".lock")).open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        save_dialog(path, state, action or {"action": "capture"})


if __name__ == "__main__":
    note = Path(os.environ.get("TASKS_FILE") or Path.home() / "Dropbox/Ikiru/Ikiru.md")
    state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "dotfiles/task-capture"
    if sys.argv[1:] == ["choices"]:
        print(json.dumps(task_choices(note, state)))
    elif sys.argv[1:] == ["watch"]:
        previous = None
        while True:
            current = status(note)
            if current != previous:
                print(json.dumps(current), flush=True)
                previous = current
            time.sleep(1)
    elif sys.argv[1:2] == ["apply"]:
        capture(note, state, json.loads(sys.argv[2]))
    elif sys.argv[1:] == ["capture"]:
        capture(note, state)
    else:
        print(json.dumps(status(note)))
