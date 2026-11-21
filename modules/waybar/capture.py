"""Show active microphone and desktop capture links reported by pw-dump --monitor."""
import json
import sys
from html import escape


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


def capture_status(graph):
    microphones, screens = set(), set()

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
            apps = microphones
        elif source_class == "Video/Source" and stream_class.startswith("Stream/Input/Video"):
            # A webcam produces the same stream class as a shared window. Check the producer.
            producer = props(source.get("client.id")).get("application.process.binary", "")
            if not (producer.startswith("xdg-desktop-portal-")
                    or source.get("node.name", "").startswith("xdph-streaming-")
                    or source.get("media.role") == "Screen"):
                continue
            apps = screens
        else:
            continue
        app = (stream.get("application.name") or props(stream.get("client.id")).get("application.name")
               or stream.get("node.name") or "Unknown application")
        apps.add(escape(" ".join(app.split())[:80]))

    icons, sections = [], []
    for apps, icon, title in ((microphones, "", "Microphone"), (screens, "󰍹", "Screen sharing")):
        if apps:
            icons.append(icon)
            sections.append(f"<b>{title}</b>\n" + "\n".join(sorted(apps, key=str.casefold)))
    return {"text": "  ".join(icons), "tooltip": "\n\n".join(sections)}


def main():
    graph, lines, previous = {}, [], None
    for line in sys.stdin:
        lines.append(line)
        # pw-dump indents nested arrays and ends each update with an unindented bracket.
        if line.rstrip() != "]":
            continue
        update_graph(graph, json.loads("".join(lines)))
        lines.clear()
        status = capture_status(graph)
        if status != previous:
            print(json.dumps(status), flush=True)
            previous = status
    print(json.dumps({"text": ""}), flush=True)


if __name__ == "__main__":
    main()
