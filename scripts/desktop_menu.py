"""Small Rofi dialogs for the Waybar controls."""
import html
import subprocess


def dialog(prompt, rows=None, *, message="", initial="", selected=0, markup=False):
    args = ["rofi", "-dmenu", "-i", "-p", prompt, "-theme-str",
            "inputbar { children: [prompt, entry]; } element { children: [element-text]; }"]
    if message:
        args += ["-mesg", html.escape(message)]
    if markup:
        args.append("-markup-rows")
    if rows is None:
        args += ["-filter", initial, "-theme-str", "mainbox { children: [inputbar, message]; }"]
    else:
        args += ["-no-custom", "-format", "i", "-selected-row", str(selected),
                 "-me-select-entry", "", "-me-accept-entry", "MousePrimary"]
    result = subprocess.run(args, input="\n".join(rows or []), text=True, stdout=subprocess.PIPE)
    if result.returncode == 1:  # Escape or focus loss
        return None
    result.check_returncode()
    answer = result.stdout.rstrip("\n")
    return int(answer) if rows is not None else answer


def notify(title, detail=""):
    subprocess.run(["notify-send", "--app-name=Waybar", "--", title, html.escape(detail)], check=True)
