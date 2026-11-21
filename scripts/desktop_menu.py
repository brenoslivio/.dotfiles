"""Short GTK dialogs and desktop notifications."""
import html
import subprocess


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
    subprocess.run(["notify-send", "--app-name=Desktop panel", "--", title, html.escape(detail)], check=True)
