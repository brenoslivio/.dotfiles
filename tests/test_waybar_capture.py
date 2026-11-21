from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modules/waybar"))
from capture import capture_status


class ScreenShareTests(unittest.TestCase):
    def test_hyprland_stream_and_camera_are_distinguished_on_nixos(self):
        wrapper = ".xdg-desktop-portal-hyprland-wrapped"
        source = {"media.class": "Video/Source", "node.name": wrapper, "client.id": 1}
        portal = {"application.process.binary": wrapper}
        graph = {
            1: ("Client", {"props": portal}),
            2: ("Node", {"props": source}),
            3: ("Node", {"props": {"media.class": "Stream/Input/Video", "application.process.binary": "brave"}}),
            4: ("Link", {"output-node-id": 2, "input-node-id": 3, "state": "active"}),
        }
        # Match the wrapped producer even before the stream name is available.
        self.assertEqual(capture_status(graph, ())["details"], "Brave · Screen sharing")
        portal.clear()
        source["media.name"] = "xdph-streaming-123"
        self.assertEqual(capture_status(graph, {"brave"}), {
            "icon": "󱡶", "multiple": True, "details": "Brave · Screen sharing and camera",
        })
        graph[4][1]["state"] = "paused"
        self.assertEqual(capture_status(graph, ())["icon"], "")
        graph[4][1]["state"] = "active"
        portal["application.process.binary"] = wrapper
        del source["media.name"]
        source["media.role"] = "Camera"
        self.assertEqual(capture_status(graph, ())["details"], "Brave · Camera")
