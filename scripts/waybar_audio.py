"""Select an available PipeWire output or microphone by its stable server name."""
from dataclasses import dataclass
import html
import json
import os
import subprocess
import sys

from desktop_menu import dialog, notify


def pactl(*args):
    return subprocess.check_output(["pactl", *args], text=True, env={**os.environ, "LC_ALL": "C"}).strip()


@dataclass(frozen=True)
class Route:
    kind: str
    device: str
    port: str
    label: str
    current: bool


def routes(kind, devices, default):
    result = []
    for device in devices:
        name = device["name"]
        if kind == "source" and name.endswith(".monitor"):
            continue
        description = device["description"].replace("\n", " ")
        ports = device.get("ports") or []
        if not ports:
            result.append(Route(kind, name, "", description, name == default))
        for port in ports:
            if port["availability"] == "not available":
                continue
            label = port["description"].replace("\n", " ")
            if label != description:
                label += " · " + description.removesuffix(" Analog Stereo")
            current = name == default and device["active_port"] == port["name"]
            result.append(Route(kind, name, port["name"], label, current))
    return result


def available(kind):
    devices = json.loads(pactl("-f", "json", "list", kind + "s"))
    return routes(kind, devices, pactl("get-default-" + kind)) if devices else []


def picker():
    rows, actions = [], []
    for kind, heading in [("sink", "Output"), ("source", "Microphone")]:
        items = available(kind)
        title = heading if items else heading + " · No devices available"
        rows.append(f"<b>{title}</b>\0nonselectable\x1ftrue")
        actions.append(None)
        for route in items:
            rows.append(("✓  " if route.current else "     ") + html.escape(route.label))
            actions.append(route)
    rows.append("Open mixer")
    first = next((i for i, route in enumerate(actions) if route), len(actions))
    selection = dialog("Audio", rows, selected=first, markup=True)
    if selection is None:
        return
    if selection == len(actions):
        subprocess.Popen(["pavucontrol"])
        return
    route = actions[selection]
    if route is None:
        return
    # Re-resolve hot-plugged devices after the dialog, before changing the default.
    if not any((r.device, r.port) == (route.device, route.port) for r in available(route.kind)):
        notify("Audio device disconnected", "Open the picker to choose another device.")
        return
    if route.port:
        pactl(f"set-{route.kind}-port", route.device, route.port)
    pactl("set-default-" + route.kind, route.device)


def mic_mute():
    source = pactl("get-default-source")
    pactl("set-source-mute", source, "toggle")
    muted = pactl("get-source-mute", source) == "Mute: yes"
    subprocess.run(["notify-send", "-e", "-u", "low", "-t", "1600",
                    "-h", "string:x-canonical-private-synchronous:mic-mute",
                    "Microphone muted" if muted else "Microphone on"], check=True)


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["mic-mute"]:
            mic_mute()
        else:
            picker()
    except subprocess.CalledProcessError:
        notify("Audio control unavailable", "Check the device connection and try again.")
