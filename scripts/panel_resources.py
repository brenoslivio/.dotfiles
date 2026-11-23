"""Stream Linux memory or CPU usage and a per-program ranking to the panel."""

from collections import Counter
from collections import deque
import html
import json
import os
from pathlib import Path
import signal
import sys
import time


PROC = Path("/proc")
PAGE_KIB = os.sysconf("SC_PAGE_SIZE") // 1024


def process_info(path):
    command, fields = (path / "stat").read_bytes().rsplit(b") ", 1)
    fields = fields.split()
    if int(fields[6]) & 0x00200000 or fields[0] == b"Z":
        return None
    try:
        name = os.path.basename(os.readlink(os.fsencode(path / "exe"))).removesuffix(b" (deleted)")
    except PermissionError:
        name = command.split(b"(", 1)[1]
    name = name.decode("utf-8", "replace")
    if name.startswith(".") and name.endswith("-wrapped"):
        name = name[1:-len("-wrapped")]
    return (path.name, int(fields[19])), name, int(fields[11]) + int(fields[12]), int(fields[21]) * PAGE_KIB


def processes():
    for entry in os.scandir(PROC):
        if not entry.name.isdecimal():
            continue
        path = PROC / entry.name
        try:
            info = process_info(path)
            if info:
                yield info
        except (OSError, IndexError, ValueError):
            continue  # Exited or inaccessible during the snapshot.


def size(kib):
    if kib >= 1024**2:
        return f"{kib / 1024**2:.1f} GiB"
    return f"{kib / 1024:.0f} MiB"


def emit(percent, heading, subheading, programs, format_value, history, **details):
    lines = [f"<b>{heading}</b>", "", subheading]
    ranking = []
    for name, value in programs.most_common(5):
        name = "".join(c if c.isprintable() else " " for c in name)
        lines.append(f"<tt>{format_value(value):>9}</tt>   {html.escape(name)}")
        ranking.append({"name": name, "value": format_value(value)})
    now = time.monotonic()
    history.append((now, percent))
    while history[0][0] < now - 60:
        history.popleft()
    print(json.dumps({"text": str(percent), "tooltip": "\n".join(lines), "programs": ranking,
                      "history": [(round(now - stamp, 1), value) for stamp, value in history],
                      **details}), flush=True)


def program_memory():
    programs = Counter()
    estimates = {}
    for (pid, start), name, _, rss in processes():
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
        estimates[f"{pid}/{start}"] = estimate
    return programs, estimates


def memory():
    next_ranking = 0
    history = deque()
    while True:
        if time.monotonic() >= next_ranking:
            programs, estimates = program_memory()
            next_ranking = time.monotonic() + 10
        info = dict(line.split(":", 1) for line in (PROC / "meminfo").read_text().splitlines())
        total = int(info["MemTotal"].split()[0])
        used = total - int(info["MemAvailable"].split()[0])
        percent = 100 * used // total
        swap_total = int(info["SwapTotal"].split()[0])
        swap_used = swap_total - int(info["SwapFree"].split()[0])
        emit(percent, f"{size(used)} of {size(total)} used ({percent}%)",
             "Top programs by memory", programs, size, history, used=size(used), total=size(total),
             estimates=estimates, available=size(total - used), swap=f"{size(swap_used)} / {size(swap_total)}" if swap_total else "Off")
        time.sleep(1)


def cpu_times():
    result = {}
    with (PROC / "stat").open() as f:
        for line in f:
            fields = line.split()
            if not fields[0].startswith("cpu"):
                break
            # Guest time is already included in user/nice.
            times = list(map(int, fields[1:9]))
            result[fields[0]] = sum(times), times[3] + times[4]
    return result


def utilization(previous, current):
    elapsed = current[0] - previous[0]
    if elapsed <= 0:
        return 0
    return max(0, min(100, round(100 * (1 - (current[1] - previous[1]) / elapsed))))


def cpu():
    history = deque()
    baseline = cpu_times()
    previous = {key: ticks for key, _, ticks, _ in processes()}
    while True:
        time.sleep(1)
        times = cpu_times()
        elapsed = times["cpu"][0] - baseline["cpu"][0]
        current = {}
        members = []
        programs = Counter()
        for key, name, ticks, rss in processes():
            current[key] = ticks
            # A newly observed PID needs a baseline before it can be ranked.
            delta = max(0, ticks - previous.get(key, ticks))
            programs[name] += delta
            members.append({"pid": int(key[0]), "start": key[1], "name": name, "rss": rss,
                            "cpu": 100 * delta / max(1, elapsed)})
        if elapsed > 0:
            percent = utilization(baseline["cpu"], times["cpu"])
            cores = [{"name": name[3:], "percent": utilization(baseline.get(name, ticks), ticks)}
                     for name, ticks in times.items() if name != "cpu"]
            emit(percent, f"Total CPU usage  {percent}%", "Top programs by CPU",
                 programs, lambda ticks: f"{100 * ticks / elapsed:.1f}%", history, cores=cores, members=members)
        previous, baseline = current, times


def force_quit(name, members):
    result = Counter()
    for pid, start in set((int(pid), int(start)) for pid, start in members):
        try:
            # Pin the kernel process object first. A reused PID can never receive the signal.
            fd = os.pidfd_open(pid)
            try:
                info = process_info(PROC / str(pid))
                if info and info[:2] == ((str(pid), start), name):
                    signal.pidfd_send_signal(fd, signal.SIGKILL)
                    result["signalled"] += 1
                else:
                    result["gone"] += 1
            finally:
                os.close(fd)
        except (FileNotFoundError, ProcessLookupError):
            result["gone"] += 1
        except PermissionError:
            result["denied"] += 1
        except OSError:
            result["failed"] += 1
    return dict(result)


if __name__ == "__main__":
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    if sys.argv[1] == "force-quit":
        target = json.loads(sys.stdin.readline())
        print(json.dumps(force_quit(target["name"], target["members"])))
    else:
        {"memory": memory, "cpu": cpu}[sys.argv[1]]()
