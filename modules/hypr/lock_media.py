"""Print Hyprlock's media label and publish a small cover for its image widget."""

import base64
import fcntl
import hashlib
import html
import io
import os
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.parse import unquote, unquote_to_bytes, urlsplit

import dbus
from PIL import Image, ImageOps, PngImagePlugin


PREFIX = "org.mpris.MediaPlayer2."
MAX_BYTES = 12 * 1024 * 1024


def current_track():
    bus = dbus.SessionBus()
    paused = None
    for name in sorted(bus.list_names()):
        if not name.startswith(PREFIX) or name == PREFIX + "playerctld":
            continue
        props = dbus.Interface(bus.get_object(name, "/org/mpris/MediaPlayer2", introspect=False),
                               "org.freedesktop.DBus.Properties")
        try:
            status = props.Get(PREFIX + "Player", "PlaybackStatus", timeout=0.5)
            if status == "Playing":
                return status, props.Get(PREFIX + "Player", "Metadata", timeout=0.5)
            if status == "Paused" and paused is None:
                paused = props
        except dbus.DBusException:
            continue  # A player can close between listing and reading it.
    return ("Paused", paused.Get(PREFIX + "Player", "Metadata", timeout=0.5)) if paused else ("", {})


def label(status, metadata):
    if not status:
        return ""
    title = " ".join(metadata.get("xesam:title", "").split())
    artist = " ".join(", ".join(metadata.get("xesam:artist", [])).split())
    def shorten(text, limit):
        return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"
    if title and artist:
        artist = shorten(artist, max(18, 51 - len(title)))
        title = shorten(title, 51 - len(artist))
    track = shorten(" — ".join(filter(None, (title, artist))), 54)
    if status == "Paused":
        return "Paused · " + html.escape(track) if track else "Paused"
    return "♪ " + html.escape(track) if track else ""


def read_art(url, local):
    if local:
        with local.open("rb") as source:
            return source.read(MAX_BYTES + 1)
    if url.startswith("data:image/"):
        header, payload = url.split(",", 1)
        if len(payload) > MAX_BYTES * 3:
            raise ValueError("Oversized cover")
        data = unquote_to_bytes(payload)
        return base64.b64decode(data, validate=True) if header.endswith(";base64") else data
    if urlsplit(url).scheme in ("http", "https"):
        return subprocess.check_output(
            ["curl", "-q", "--proto", "=http,https", "--proto-redir", "=http,https",
             "--fail", "--silent", "--location", "--max-time", "2", "--max-filesize", str(MAX_BYTES), "--", url],
            stderr=subprocess.DEVNULL)
    raise ValueError("Unsupported cover URL")


def publish_cover(path, url):
    if not url:
        path.unlink(missing_ok=True)
        return
    parsed = urlsplit(url) if url.startswith("file:") else None
    local = Path(unquote(parsed.path)) if parsed and parsed.netloc in ("", "localhost") else None
    key = hashlib.sha256(url.encode()).hexdigest()
    if local:
        try:
            key += str(local.stat().st_mtime_ns)
        except OSError:
            path.unlink(missing_ok=True)
            return
    if path.exists():
        with Image.open(path) as cached:
            if cached.info.get("source") == key and (
                    "unavailable" not in cached.info or time.time() - path.stat().st_mtime < 60):
                return
    info = PngImagePlugin.PngInfo()
    info.add_text("source", key)
    try:
        data = read_art(url, local)
        if len(data) > MAX_BYTES:
            raise ValueError("Oversized cover")
        with Image.open(io.BytesIO(data)) as art:
            if art.width * art.height > 24_000_000:
                raise ValueError("Oversized cover")
            art.thumbnail((384, 384))
            cover = ImageOps.fit(ImageOps.exif_transpose(art).convert("RGBA"), (144, 144))
    except (OSError, ValueError, subprocess.SubprocessError, Image.DecompressionBombError):
        cover = Image.new("RGBA", (1, 1))
        info.add_text("unavailable", "1")
    with tempfile.TemporaryDirectory(dir=path.parent) as temp:
        new_cover = Path(temp) / "cover.png"
        cover.save(new_cover, "PNG", pnginfo=info)
        new_cover.replace(path)


def main():
    directory = Path(os.environ["XDG_RUNTIME_DIR"]) / "hyprlock-media"
    directory.mkdir(mode=0o700, exist_ok=True)
    with (directory / "update.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            status, metadata = current_track()
        except dbus.DBusException:
            status, metadata = "", {}
        cover = directory / "cover.png"
        try:
            publish_cover(cover, metadata.get("mpris:artUrl", ""))
        except (OSError, ValueError):
            cover.unlink(missing_ok=True)
        print(label(status, metadata))


if __name__ == "__main__":
    main()
