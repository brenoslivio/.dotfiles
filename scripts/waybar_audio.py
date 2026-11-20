"""Select an available PipeWire output or microphone by its stable server name."""
from dataclasses import dataclass
from collections import Counter
import json
import os
import subprocess
import sys
import time

from desktop_menu import group, item, menu, notify, show_menu


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
            if name.startswith("bluez_") and description != label:
                label = f"{description} · {label}"
            current = name == default and device["active_port"] == port["name"]
            result.append(Route(kind, name, port["name"], label, current))
    return result


def available(kind):
    devices = json.loads(pactl("-f", "json", "list", kind + "s"))
    return routes(kind, devices, pactl("get-default-" + kind)) if devices else []


def headset_profiles(cards):
    for card in cards:
        if not card["name"].startswith("bluez_card."):
            continue
        profiles = card["profiles"]
        if profiles.get(card["active_profile"], {}).get("sources", 0):
            continue
        voice = [(v.get("priority", 0), k) for k, v in profiles.items()
                 if v.get("sources", 0) and v.get("available") not in (False, "no")]
        if voice:
            yield card, max(voice)[1]


def picker():
    root, choices = menu()
    for kind, heading in [("sink", "Output"), ("source", "Microphone")]:
        section = group(choices, heading, "section")
        items = available(kind)
        counts = Counter(route.label for route in items)
        for route in items:
            label = route.label if counts[route.label] == 1 else f"{route.label} · {route.device}"
            item(section, ("✓  " if route.current else "     ") + label,
                 {"action": "route", "kind": kind, "device": route.device, "port": route.port})
        if kind == "source":
            for card, profile in headset_profiles(json.loads(pactl("-f", "json", "list", "cards"))):
                name = card["properties"].get("device.description", card["name"])
                item(section, f"Use {name} microphone…",
                     {"action": "headset", "card": card["name"], "profile": profile})
        if not items:
            item(section, "No active devices")
    item(choices, "Open mixer", {"action": "mixer"})
    show_menu(root)


def select_route(kind, device, port):
    def selected():
        return next((r for r in available(kind) if (r.device, r.port) == (device, port)), None)
    if kind not in ("source", "sink") or selected() is None:
        raise ValueError("The device disconnected. Reopen the menu to choose another.")
    if port:
        pactl(f"set-{kind}-port", device, port)
    pactl("set-default-" + kind, device)
    for _ in range(10):
        route = selected()
        if route and route.current:
            return
        time.sleep(0.1)
    raise ValueError("The audio server did not confirm the selected device and port.")


def switch_headset(action):
    def cards():
        return json.loads(pactl("-f", "json", "list", "cards"))
    name, profile = action["card"], action["profile"]
    original = next((c["active_profile"] for c, p in headset_profiles(cards())
                     if c["name"] == name and p == profile), None)
    if original is None:
        raise ValueError("The headset configuration changed. Reopen the menu.")
    result = subprocess.run(["zenity", "--question", "--title", "Enable headset microphone?",
                             "--text", "Using the headset microphone switches Bluetooth playback to call quality.",
                             "--ok-label", "Use headset microphone", "--cancel-label", "Cancel"])
    if result.returncode:
        return
    if not any(c["name"] == name and c["active_profile"] == original for c in cards()):
        raise ValueError("The headset configuration changed. Reopen the menu.")
    pactl("set-card-profile", name, profile)
    try:
        for _ in range(20):
            card = next((c for c in cards() if c["name"] == name), None)
            if not card or card["active_profile"] not in (profile, original):
                break
            if card["active_profile"] == original:
                time.sleep(0.15)
                continue
            sources = [s for s in json.loads(pactl("-f", "json", "list", "sources"))
                       if str(s["properties"].get("device.id", s.get("card"))) == str(card["index"]) and not s["name"].endswith(".monitor")]
            if sources:
                s = sources[0]
                select_route("source", s["name"], s.get("active_port") or "")
                return
            time.sleep(0.15)
        raise ValueError("The headset microphone did not become available.")
    except (ValueError, subprocess.CalledProcessError):
        if any(c["name"] == name and c["active_profile"] == profile for c in cards()):
            pactl("set-card-profile", name, original)
        raise


def apply(action):
    if action["action"] == "mixer":
        subprocess.Popen(["pavucontrol"])
    elif action["action"] == "headset":
        switch_headset(action)
    elif action["action"] == "route":
        select_route(action["kind"], action["device"], action["port"])


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
        elif sys.argv[1:2] == ["apply"]:
            apply(json.loads(sys.argv[2]))
        else:
            picker()
    except ValueError as error:
        notify("Audio selection unavailable", str(error))
    except subprocess.CalledProcessError:
        notify("Audio control unavailable", "Check the device connection and try again.")
