"""Manage the laptop/HDMI layout and the display picker."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

PANEL = "eDP-1"
HDMI = "HDMI-A-1"
MIRROR = "Mirror"
EXTERNAL_ONLY = "Docked"
LAPTOP_MAIN = "Extend · Laptop main"
EXTERNAL_MAIN = "Extend · External main"
MODES = (MIRROR, EXTERNAL_ONLY, LAPTOP_MAIN, EXTERNAL_MAIN)
# The secondary workspace stays associated with its physical screen.
SECONDARY = {LAPTOP_MAIN: ("external", HDMI), EXTERNAL_MAIN: ("laptop", PANEL)}
LEGACY_MODES = {"Mirrored": MIRROR, "External only": EXTERNAL_ONLY, "Disjoint": LAPTOP_MAIN}
RUNTIME = Path(os.environ["XDG_RUNTIME_DIR"]) / ("displays-" + os.environ["WAYLAND_DISPLAY"])
PREFERENCE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "hyprdocked/mode"


def write_mode(path, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as tmp:
        tmp.write(mode + "\n")
    os.replace(tmp.name, path)


def read_mode(path):
    try:
        mode = path.read_text().strip()
        return mode if mode in MODES else LEGACY_MODES.get(mode)
    except FileNotFoundError:
        return None


def connected():
    # DRM drops the connector before Hyprland drops its cached monitor.
    return any(p.read_text().strip() == "connected"
               for p in Path("/sys/class/drm").glob(f"card*-{HDMI}/status"))


def ctl(*args):
    return subprocess.check_output(["hyprctl", *args], text=True, timeout=4).strip()


def query(*args):
    return json.loads(ctl("-j", *args))


def monitors():
    return {m["name"]: m for m in query("monitors", "all")}


def active(output):
    return output and not output["disabled"] and output["width"] > 0 and output["height"] > 0


def primary_output(mode):
    return HDMI if mode in (EXTERNAL_ONLY, EXTERNAL_MAIN) else PANEL


def topology(outputs):
    panel, hdmi = outputs.get(PANEL), outputs.get(HDMI)
    if not active(hdmi):
        return "Laptop" if active(panel) else None
    if active(panel) and hdmi["mirrorOf"] in (PANEL, str(panel["id"])):
        return MIRROR
    if hdmi["mirrorOf"] == "none":
        if not active(panel):
            return EXTERNAL_ONLY
        if hdmi["x"] >= panel["x"] + panel["width"] / panel["scale"]:
            return "Extended"
    return None


def extended_mode():
    # A config reload clears these bindings even if both outputs stay on.
    rules = {r["workspaceString"]: r for r in query("workspacerules") if r["enabled"]}
    for mode, (name, output) in SECONDARY.items():
        side = rules.get("name:" + name, {})
        if (side.get("default") and side.get("monitor") == output
                and rules.get("1", {}).get("monitor") == primary_output(mode)):
            return mode
    return None


def request_mode(mode):
    if mode not in MODES:
        sys.exit("Unknown display layout.")
    if not connected():
        sys.exit("The HDMI display is disconnected.")
    write_mode(RUNTIME / "request", mode)


def picker(action):
    plugged = connected()
    current = topology(monitors()) if plugged else "Laptop"
    if current == "Extended":
        current = extended_mode()
    if action == "status":
        print(json.dumps({"connected": plugged, "current": current, "modes": MODES if plugged else [],
                          "text": "󰍹" if plugged else "", "tooltip": f"Displays · {current or 'Switching…'}"}))
        return
    if not plugged:
        return
    rows = [mode + ("  ✓" if mode == current else "") for mode in MODES]
    result = subprocess.run(
        ["rofi", "-dmenu", "-p", "Displays", "-no-custom", "-format", "i",
         "-me-select-entry", "", "-me-accept-entry", "MousePrimary",
         "-selected-row", str(MODES.index(current) if current in MODES else 0),
         "-theme-str", "window { location: northeast; anchor: northeast; x-offset: 14px; "
                       "y-offset: 6px; width: 260px; padding: 6px; } "
                       "mainbox { children: [listview]; } listview { lines: 4; } "
                       "element { children: [element-text]; }"],
        input="\n".join(rows), text=True, stdout=subprocess.PIPE,
    )
    if result.returncode == 0:
        request_mode(MODES[int(result.stdout)])


def unlocked():
    return query("locked")["locked"] is False


def evaluate(lua):
    reply = ctl("eval", lua)
    if reply != "ok":
        raise RuntimeError(reply)


def monitor(output, position="0x0", mirror=""):
    evaluate(f"hl.monitor({{output='{output}', mode='preferred', position='{position}', "
             f"scale=1, disabled=false, mirror='{mirror}'}})")


def wait_for(check):
    for _ in range(20):
        if check(monitors()):
            return
        time.sleep(0.1)
    raise RuntimeError("Timed out waiting for the monitor change")


def configure_outputs(mode, outputs):
    # A docked HDMI output may still have a fixed position of 0x0. Give it a
    # relative position before the laptop panel reclaims the origin.
    if mode != EXTERNAL_ONLY and connected() and active(outputs.get(HDMI)) and not active(outputs.get(PANEL)):
        monitor(HDMI, position="auto-right")
    if mode != EXTERNAL_ONLY:
        if not active(outputs.get(PANEL)):
            monitor(PANEL)
        wait_for(lambda m: active(m.get(PANEL)))
    if mode == "Laptop":
        return
    if not connected() or not unlocked():
        raise RuntimeError("HDMI disconnected or session locked")
    if mode == MIRROR:
        monitor(HDMI, position="auto-right", mirror=PANEL)
    else:
        monitor(HDMI, position="auto-right")
        wait_for(lambda m: active(m.get(HDMI)) and m[HDMI]["mirrorOf"] == "none")
        if mode == EXTERNAL_ONLY:
            if not connected() or not unlocked():
                raise RuntimeError("HDMI disconnected or session locked")
            evaluate(f"hl.monitor({{output='{PANEL}', disabled=true}})")


def workspace_rules(mode):
    primary = primary_output(mode)
    side_name, side_output = SECONDARY.get(mode, ("", primary))
    # Exact rules also cover the first use of Super+7 through Super+0 from HDMI.
    evaluate(f"""
        for i = 1, 10 do
            hl.workspace_rule({{workspace=tostring(i), monitor='{primary}'}})
        end
        for _, name in ipairs({{'external', 'laptop'}}) do
            local secondary = name == '{side_name}'
            hl.workspace_rule({{workspace='name:' .. name, default=secondary,
                               monitor=secondary and '{side_output}' or '{primary}'}})
        end
    """)


def place_workspaces(mode, remembered):
    primary = primary_output(mode)
    side_name, side_output = SECONDARY.get(mode, ("", primary))
    # Give the secondary display its workspace first. Moving its last visible workspace
    # otherwise makes Hyprland create a replacement numbered workspace there.
    evaluate(f"""
        local primary = '{primary}'
        local side = '{side_name}'
        local function move(w, monitor)
            local selector = w.id or ('name:' .. w.name)
            hl.dispatch(hl.dsp.workspace.move({{workspace=selector, monitor=monitor}}))
        end
        if side ~= '' then
            local selector = 'name:' .. side
            local w = hl.get_workspace(selector)
            if w and w.monitor.name ~= '{side_output}' then move(w, '{side_output}') end
            hl.dispatch(hl.dsp.focus({{workspace=selector}}))
        end
        for _, w in ipairs(hl.get_workspaces()) do
            if not w.special and w.name ~= side and w.monitor.name ~= primary then
                move(w, primary)
            end
        end
        hl.dispatch(hl.dsp.focus({{monitor=primary}}))
        hl.dispatch(hl.dsp.focus({{workspace={remembered}}}))
    """)


def split_workspaces_ok(mode, workspaces):
    name, secondary = SECONDARY[mode]
    primary = primary_output(mode)
    normal = [w for w in workspaces if w["type"] == "normal"]
    return (any(w["name"] == name for w in normal)
            and all(w["monitor"] == (secondary if w["name"] == name else primary) for w in normal))


def watch():
    preferred = read_mode(PREFERENCE) or EXTERNAL_ONLY
    applied = None
    remembered = 1
    RUNTIME.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            plugged = connected()
            outputs = monitors()
            actual = topology(outputs)
            if not active(outputs.get(PANEL)) and not active(outputs.get(HDMI)):
                # A failed HDMI mode-set or physical unplug can remove the last output.
                monitor(PANEL)
                wait_for(lambda m: active(m.get(PANEL)))
                outputs = monitors()
                actual = topology(outputs)
            if not unlocked():
                # Unplugging while locked must leave a panel on which to unlock.
                if not plugged and not active(outputs.get(PANEL)):
                    monitor(PANEL)
                time.sleep(1)
                continue
            request = RUNTIME / "processing"
            try:
                (RUNTIME / "request").replace(request)
            except FileNotFoundError:
                pass
            requested = read_mode(request)
            target = (requested or preferred) if plugged else "Laptop"
            target_topology = "Extended" if target in SECONDARY else target
            current = extended_mode() if actual == "Extended" else actual
            if current == applied or applied is None:
                primary = outputs.get(primary_output(current)) or {}
                number = primary.get("activeWorkspace", {}).get("id")
                if isinstance(number, int) and number > 0:
                    remembered = number

            changed = current != target or applied != target
            if actual != target_topology:
                configure_outputs(target_topology, outputs)
                wait_for(lambda m: topology(m) == target_topology)
            repair = False
            if target in SECONDARY:
                _, side_output = SECONDARY[target]
                repair = not split_workspaces_ok(target, query("workspaces"))
                if repair and not changed and outputs[side_output]["focused"]:
                    # A newly created workspace outside the shortcut range
                    # should follow the user's focus back to the main screen.
                    number = outputs[side_output]["activeWorkspace"].get("id")
                    if isinstance(number, int) and number > 0:
                        remembered = number
            if changed or repair:
                if not unlocked() or connected() != plugged:
                    raise RuntimeError("Display state changed during layout switch")
                workspace_rules(target)
                place_workspaces(target, remembered)
                if target in SECONDARY and not split_workspaces_ok(target, query("workspaces")):
                    raise RuntimeError("Workspace placement has not settled")
            if requested and plugged and requested != preferred:
                write_mode(PREFERENCE, requested)
                preferred = requested
            request.unlink(missing_ok=True)
            applied = target
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as err:
            print(f"Display switch: {err}", file=sys.stderr, flush=True)
            # Return to the last successful layout after an unsuccessful choice.
            (RUNTIME / "processing").unlink(missing_ok=True)
            applied = None
            # A compositor watchdog restart may change the instance signature.
            try:
                matches = [i for i in query("instances") if i["wl_socket"] == os.environ["WAYLAND_DISPLAY"]]
                if len(matches) == 1:
                    os.environ["HYPRLAND_INSTANCE_SIGNATURE"] = matches[0]["instance"]
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
        time.sleep(1)


if __name__ == "__main__":
    if sys.argv[1:] in (["status"], ["menu"]):
        picker(sys.argv[1])
    elif len(sys.argv) == 3 and sys.argv[1] == "set":
        request_mode(sys.argv[2])
    elif not sys.argv[1:]:
        watch()
    else:
        sys.exit("Usage: display-mode [status|menu|set LAYOUT]")
