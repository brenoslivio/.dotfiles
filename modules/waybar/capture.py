"""Report active desktop captures to the WirePlumber volume button."""
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from selectors import DefaultSelector, EVENT_READ


def update_graph(graph, batch):
    for obj in batch:
        key = obj["id"]
        info = obj.get("info")
        if info is None:
            graph.pop(key, None)
            continue
        kind = obj["type"].rsplit(":", 1)[-1]
        if kind in ("Client", "Node", "Link"):
            # Drop the large format/parameter lists from the monitored snapshot.
            graph[key] = (kind, {k: info[k] for k in
                                 ("props", "state", "input-node-id", "output-node-id") if k in info})


BROWSERS = {"brave": "Brave", "chromium": "Chromium", "chrome": "Google Chrome",
            "firefox": "Firefox", "firefox-esr": "Firefox"}


def camera_devices():
    devices = set()
    for entry in Path("/sys/class/video4linux").glob("video*"):
        try:
            number = (entry / "dev").read_text().strip()
            properties = Path("/run/udev/data", "c" + number).read_text()
        except OSError:
            continue
        if any(":capture:" in line for line in properties.splitlines()
               if line.startswith("E:ID_V4L_CAPABILITIES=")):
            devices.add("/dev/" + entry.name)
    return devices


def camera_owners(devices):
    """Read descriptor targets only. Opening the webcam ourselves would affect its state."""
    owners = set()
    if not devices:
        return owners
    for proc in Path("/proc").glob("[0-9]*"):
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            for fd in (proc / "fd").iterdir():
                try:
                    target = os.readlink(fd)
                except OSError:
                    continue
                if target in devices:
                    name = (proc / "comm").read_text().strip()
                    # Brokers open the physical device on behalf of PipeWire consumers.
                    if name not in {"pipewire", "wireplumber", "pipewire-pulse"}:
                        owners.add(name)
                    break
        except OSError:
            continue
    return owners


def capture_status(graph, direct_cameras):
    apps = defaultdict(set)
    names_by_binary = {}

    def props(object_id):
        return graph.get(object_id, ("", {}))[1].get("props", {})

    for kind, link in graph.values():
        if kind != "Link" or link.get("state") != "active":
            continue
        source = props(link["output-node-id"])
        stream = props(link["input-node-id"])
        source_class = source.get("media.class", "")
        stream_class = stream.get("media.class", "")
        if source_class.startswith("Audio/Source") and stream_class.startswith("Stream/Input/Audio"):
            if str(stream.get("stream.monitor", "")).lower() == "true":
                continue
            resource = "microphone"
        elif source_class.startswith("Video/Source") and stream_class.startswith("Stream/Input/Video"):
            producer = props(source.get("client.id")).get("application.process.binary", "")
            if source.get("media.role") == "Camera" or source.get("device.api") in {"v4l2", "libcamera"}:
                resource = "camera"
            # Hyprland puts the stream ID in media.name when node.name is the Nix wrapper.
            elif (source.get("media.role") == "Screen"
                  or any(source.get(key, "").startswith("xdph-streaming-") for key in ("media.name", "node.name"))
                  or producer.removeprefix(".").startswith("xdg-desktop-portal-")):
                resource = "screen sharing"
            else:
                continue
        else:
            continue
        client = props(stream.get("client.id"))
        binary = stream.get("application.process.binary") or client.get("application.process.binary")
        name = (BROWSERS.get(binary) or stream.get("application.name") or client.get("application.name")
                or stream.get("node.name") or "Unknown application")
        name = " ".join(name.split())[:80]
        if binary:
            names_by_binary[binary] = name
        apps[name].add(resource)

    for binary in direct_cameras:
        name = names_by_binary.get(binary) or BROWSERS.get(binary, binary)
        apps[" ".join(name.split())[:80]].add("camera")

    icons = {"screen sharing": "󰍹", "camera": "", "microphone": ""}
    active = set().union(*apps.values())
    details = []
    for name, resources in sorted(apps.items(), key=lambda item: item[0].casefold()):
        ordered = [key for key in icons if key in resources]
        label = ordered[0] if len(ordered) == 1 else ", ".join(ordered[:-1]) + " and " + ordered[-1]
        details.append(f"{name} · {label.capitalize()}")
    return {"icon": next((icon for key, icon in icons.items() if key in active), ""),
            "multiple": len(active) > 1, "details": "\n".join(details)}


def main():
    from inotify_simple import INotify, flags

    graph, owners = {}, set()
    buffer = bytearray()
    previous = None
    rescan_devices = True
    due = time.monotonic() + 0.65
    with INotify() as notify, DefaultSelector() as selector:
        directory = notify.add_watch("/dev", flags.CREATE | flags.DELETE | flags.MOVED_FROM | flags.MOVED_TO)
        selector.register(notify, EVENT_READ)
        selector.register(sys.stdin.buffer, EVENT_READ)
        while True:
            timeout = None if due is None else max(0, due - time.monotonic())
            for key, _ in selector.select(timeout):
                if key.fileobj is notify:
                    for event in notify.read():
                        if event.wd == directory and not event.name.startswith("video"):
                            continue
                        if event.wd == directory or event.mask & (flags.Q_OVERFLOW | flags.IGNORED):
                            rescan_devices = True
                        # Ignore short camera probes, including those made during hotplug.
                        due = time.monotonic() + 0.65
                else:
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        return
                    buffer.extend(chunk)
                    # pw-dump indents nested arrays. Only the outer batch ends at column zero.
                    while (end := buffer.find(b"\n]\n")) != -1:
                        update_graph(graph, json.loads(buffer[:end + 2]))
                        del buffer[:end + 3]
            if due is not None and time.monotonic() >= due:
                if rescan_devices:
                    # Adding a watch twice reuses it. Linux removes watches for deleted devices.
                    for device in Path("/dev").glob("video[0-9]*"):
                        try:
                            notify.add_watch(device, flags.OPEN | flags.CLOSE_WRITE | flags.CLOSE_NOWRITE)
                        except OSError:
                            pass  # The device may disappear during enumeration.
                    rescan_devices = False
                owners = camera_owners(camera_devices())
                due = None
            status = capture_status(graph, owners)
            if status != previous:
                print(json.dumps(status), flush=True)
                previous = status


if __name__ == "__main__":
    main()
