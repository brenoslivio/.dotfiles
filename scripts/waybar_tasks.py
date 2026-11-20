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
            "tooltip": "\n".join([*tooltip, "Right-click to add a task"])}


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


def save_task(path, project, text):
    path = path.resolve(strict=True)
    if not os.access(path, os.W_OK):
        raise PermissionError("The task note is read-only.")
    # Re-read at submission so edits made while Rofi was open are included.
    for _ in range(3):
        before = version(path.stat())
        lines = read_lines(path)
        insert_task(lines, project, text)
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


def capture(path, state):
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = hashlib.sha256(os.fsencode(path.absolute())).hexdigest()
    draft = state / (key + ".json")
    with (state / (key + ".lock")).open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        previous = json.loads(draft.read_text()) if draft.exists() else {}
        try:
            projects = project_names(read_lines(path))
        except (OSError, UnicodeError):
            projects = []
        project = previous.get("project", "")
        if projects:
            choice = dialog("Project", projects, selected=projects.index(project) if project in projects else 0)
            if choice is None:
                return
            project = projects[choice]
        message = f"Add to {project}" if projects else "No projects available. Enter saves a local draft."
        answer = dialog("New task", message=message, initial=previous.get("text", ""))
        if answer is None or not answer.strip():
            return
        text = " ".join(answer.splitlines()).strip()
        with tempfile.NamedTemporaryFile(dir=state, mode="w", encoding="utf-8", delete=False) as stream:
            json.dump({"project": project, "text": text}, stream)
        os.replace(stream.name, draft)
        try:
            if not projects:
                raise ValueError("Open capture again when the Tasks section is available.")
            save_task(path, project, text)
        except (OSError, UnicodeError, ValueError) as error:
            notify("Task kept as a draft", str(error))
            return
        draft.unlink()
        notify("Task added", project)


if __name__ == "__main__":
    note = Path(os.environ.get("TASKS_FILE") or Path.home() / "Dropbox/Ikiru/Ikiru.md")
    if sys.argv[1:] == ["capture"]:
        capture(note, Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "dotfiles/task-capture")
    else:
        print(json.dumps(status(note)))
