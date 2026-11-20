"""Native GTK menu descriptions for Waybar and short desktop dialogs."""
import html
import json
import subprocess
import xml.etree.ElementTree as ET


def menu():
    root = ET.Element("interface")
    return root, ET.SubElement(root, "menu", id="choices")


def group(parent, label, tag="submenu"):
    node = ET.SubElement(parent, tag)
    ET.SubElement(node, "attribute", name="label").text = label.replace("_", "__")
    return node


def item(parent, label, action=None):
    node = group(parent, label, "item")
    ET.SubElement(node, "attribute", name="action").text = "picker.choose" if action else "picker.disabled"
    if action:
        ET.SubElement(node, "attribute", name="target").text = json.dumps(action)
    return node


def show_menu(root):
    print(ET.tostring(root, encoding="unicode"))


def dialog(title, choices=None, *, message="", initial=""):
    args = ["zenity", "--title", title, "--text", message, "--width", "380"]
    if choices is None:
        args += ["--entry", "--entry-text", initial, "--ok-label", "Save"]
    else:
        args += ["--list", "--column", "ID", "--column", "Task", "--hide-column", "1", "--print-column", "1"]
        for i, choice in enumerate(choices):
            args.extend([str(i), choice])
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE)
    if result.returncode == 1:
        return None
    result.check_returncode()
    value = result.stdout.rstrip("\n")
    return value if choices is None else int(value)


def notify(title, detail=""):
    subprocess.run(["notify-send", "--app-name=Waybar", "--", title, html.escape(detail)], check=True)
