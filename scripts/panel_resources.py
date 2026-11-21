"""Stream Linux memory or CPU usage and a per-program ranking to the panel."""

from collections import Counter
import html
import json
import os
from pathlib import Path
import signal
import sys
import time


PROC = Path("/proc")
PAGE_KIB = os.sysconf("SC_PAGE_SIZE") // 1024


def processes():
    for entry in os.scandir(PROC):
        if not entry.name.isdecimal():
            continue
        path = PROC / entry.name
        try:
            # comm is parenthesized and may contain spaces or closing parentheses.
            command, fields = (path / "stat").read_bytes().rsplit(b") ", 1)
            fields = fields.split()  # starts at field 3 (state)
            if int(fields[6]) & 0x00200000:  # PF_KTHREAD
                continue
            try:
                name = os.path.basename(os.readlink(os.fsencode(path / "exe")))
                name = name.removesuffix(b" (deleted)")
            except PermissionError:
                name = command.split(b"(", 1)[1]
            name = name.decode("utf-8", "replace")
            if name.startswith(".") and name.endswith("-wrapped"):
                name = name[1:-len("-wrapped")]
            identity = (entry.name, int(fields[19]))  # PID and start time
            yield identity, name, int(fields[11]) + int(fields[12]), int(fields[21]) * PAGE_KIB
        except (OSError, IndexError, ValueError):
            continue  # Exited or inaccessible during the snapshot.


def size(kib):
    if kib >= 1024**2:
        return f"{kib / 1024**2:.1f} GiB"
    return f"{kib / 1024:.0f} MiB"


def emit(percent, heading, subheading, programs, format_value):
    lines = [f"<b>{heading}</b>", "", subheading]
    for name, value in programs.most_common(5):
        name = "".join(c if c.isprintable() else " " for c in name)
        lines.append(f"<tt>{format_value(value):>9}</tt>   {html.escape(name)}")
    print(json.dumps({"text": str(percent), "tooltip": "\n".join(lines)}), flush=True)


def program_memory():
    programs = Counter()
    for (pid, _), name, _, rss in processes():
        if not rss:
            continue
        estimate = rss
        try:
            # PSS divides shared pages among their users (e.g. browser renderers).
            with (PROC / pid / "smaps_rollup").open("rb") as rollup:
                for line in rollup:
                    if line.startswith(b"Pss:"):
                        estimate = int(line.split()[1])
                        break
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            pass  # Restricted maps still expose resident memory.
        programs[name] += estimate
    return programs


def memory():
    next_ranking = 0
    while True:
        if time.monotonic() >= next_ranking:
            programs = program_memory()
            next_ranking = time.monotonic() + 10
        info = dict(line.split(":", 1) for line in (PROC / "meminfo").read_text().splitlines())
        total = int(info["MemTotal"].split()[0])
        used = total - int(info["MemAvailable"].split()[0])
        percent = 100 * used // total
        emit(percent, f"{size(used)} of {size(total)} used ({percent}%)",
             "Top programs by memory", programs, size)
        time.sleep(1)


def cpu_times():
    with (PROC / "stat").open() as f:
        # Guest time is already included in user/nice.
        times = [int(t) for t in f.readline().split()[1:9]]
    return sum(times), times[3] + times[4]


def cpu():
    prev_total, prev_idle = cpu_times()
    previous = {key: ticks for key, _, ticks, _ in processes()}
    while True:
        time.sleep(1)
        total, idle = cpu_times()
        elapsed = total - prev_total
        current = {}
        programs = Counter()
        for key, name, ticks, _ in processes():
            current[key] = ticks
            # A newly observed PID needs a baseline before it can be ranked.
            programs[name] += max(0, ticks - previous.get(key, ticks))
        if elapsed > 0:
            percent = round(100 * (1 - (idle - prev_idle) / elapsed))
            emit(percent, f"Total CPU usage  {percent}%", "Top programs by CPU",
                 programs, lambda ticks: f"{100 * ticks / elapsed:.1f}%")
        previous, prev_total, prev_idle = current, total, idle


if __name__ == "__main__":
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    {"memory": memory, "cpu": cpu}[sys.argv[1]]()
