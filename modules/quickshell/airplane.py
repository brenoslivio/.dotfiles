"""Toggle Wi-Fi and Bluetooth rfkill switches and restore the previous preferences."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

TYPES = ("wlan", "bluetooth")
NM = "org.freedesktop.NetworkManager"
NM_PATH = "/org/freedesktop/NetworkManager"
ADAPTER = "org.bluez.Adapter1"


def state_file():
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "quickshell-airplane/radios.json"


def switches():
    rows = {}
    for node in Path("/sys/class/rfkill").glob("rfkill*"):
        try:
            kind = (node / "type").read_text().strip()
            if kind in TYPES:
                rows[node.name[6:]] = (kind, (node / "name").read_text().strip(),
                                       (node / "soft").read_text().strip() == "1",
                                       (node / "hard").read_text().strip() == "1")
        except FileNotFoundError:
            continue  # USB adapters can disappear during enumeration.
    return rows


def status():
    rows = switches()
    restore = state_file().exists()
    return {"available": bool(rows) or restore, "restore": restore,
            "on": restore and bool(rows) and all(soft or hard for _, _, soft, hard in rows.values())}


def run(*args):
    result = subprocess.run(args, text=True, capture_output=True, timeout=6)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"{args[0]} failed")
    return result.stdout


def bus(*args):
    return run("busctl", "--system", "--json=short", *args)


def wifi_enabled():
    return json.loads(bus("get-property", NM, NM_PATH, NM, "WirelessEnabled"))["data"]


def adapters():
    objects = json.loads(bus("call", "org.bluez", "/", "org.freedesktop.DBus.ObjectManager",
                             "GetManagedObjects"))["data"][0]
    return {props[ADAPTER]["Address"]["data"]: (path, props[ADAPTER]["Powered"]["data"])
            for path, props in objects.items() if ADAPTER in props}


def save_previous(path, rows):
    soft = {}
    for kind, name, blocked, _ in rows.values():
        soft.setdefault(kind, {})[name] = blocked
    saved = {"switches": soft, "wifi": wifi_enabled() if "wlan" in soft else None,
             "bluetooth": {addr: power for addr, (_, power) in adapters().items()} if "bluetooth" in soft else {}}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(saved))
    tmp.replace(path)
    return saved


def restore(saved, kinds):
    for kind in kinds:
        previous = saved["switches"][kind]
        # Restore the type default as well as adapters with individual blocks.
        blocked = all(previous.values())
        run("rfkill", "block" if blocked else "unblock", kind)
        for idx, (typ, name, soft, _) in switches().items():
            if typ == kind and soft != previous.get(name, blocked):
                run("rfkill", "block" if previous.get(name, blocked) else "unblock", idx)
    wifi = saved["wifi"]
    if "wlan" in kinds and wifi_enabled() != wifi:
        bus("set-property", NM, NM_PATH, NM, "WirelessEnabled", "b", str(wifi).lower())
        if wifi_enabled() != wifi:
            raise RuntimeError("Wi-Fi settings have not finished restoring. Try Restore radios again.")
    # BlueZ may recreate the controller after the platform switch is released.
    for attempt in range(16):
        rows = switches().values()
        if "bluetooth" not in kinds or not saved["bluetooth"] or not any(k == "bluetooth" and not (s or h) for k, _, s, h in rows):
            break
        live = adapters()
        for addr, (path, powered) in live.items():
            desired = saved["bluetooth"].get(addr, powered)
            if powered != desired:
                bus("set-property", "org.bluez", path, ADAPTER, "Powered", "b", str(desired).lower())
        if all(addr in live and live[addr][1] == desired for addr, desired in saved["bluetooth"].items()):
            break
        if attempt == 15:
            raise RuntimeError("Bluetooth has not finished restoring. Try Restore radios again.")
        time.sleep(0.2)
    for kind, name, soft, hard in switches().values():
        previous = saved["switches"].get(kind, {})
        if kind in kinds and name in previous and not hard and soft != previous[name]:
            raise RuntimeError("Radio settings have not finished restoring. Try Restore radios again.")


def change(action, path):
    if action == "off":
        if path.exists():
            saved = json.loads(path.read_text())
            restore(saved, saved["switches"])
            path.unlink()
        return
    rows = switches()
    if not rows:
        raise RuntimeError("No wireless radios are available.")
    existing = path.exists()
    saved = json.loads(path.read_text()) if existing else save_previous(path, rows)
    changed = []
    try:
        for kind in saved["switches"]:
            run("rfkill", "block", kind)
            changed.append(kind)
        if not all(soft or hard for _, _, soft, hard in switches().values()):
            raise RuntimeError("A wireless radio is still on.")
    except (OSError, RuntimeError, subprocess.SubprocessError):
        if not existing:
            restore(saved, changed)
            path.unlink()
        raise


if __name__ == "__main__":
    if sys.argv[1:] not in (["on"], ["off"]):
        sys.exit("Usage: airplane on|off")
    try:
        path = state_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            change(sys.argv[1], path)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as err:
        sys.exit(f"Airplane Mode: {err}")
