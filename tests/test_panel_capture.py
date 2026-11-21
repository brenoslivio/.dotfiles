from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modules/quickshell"))
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
            "indicators": [{"icon": "󱡶", "hint": "Screen sharing\nBrave"},
                           {"icon": "󰖠", "hint": "Camera\nBrave"}],
            "details": "Brave · Screen sharing and camera",
        })
        graph[4][1]["state"] = "paused"
        self.assertEqual(capture_status(graph, ())["indicators"], [])
        graph[4][1]["state"] = "active"
        portal["application.process.binary"] = wrapper
        del source["media.name"]
        source["media.role"] = "Camera"
        self.assertEqual(capture_status(graph, ())["details"], "Brave · Camera")

    def test_concurrent_captures_list_each_app_under_its_resource(self):
        graph = {
            1: ("Node", {"props": {"media.class": "Audio/Source"}}),
            2: ("Node", {"props": {"media.class": "Stream/Input/Audio", "application.name": "Recorder"}}),
            3: ("Link", {"output-node-id": 1, "input-node-id": 2, "state": "active"}),
            4: ("Node", {"props": {"media.class": "Stream/Input/Audio", "application.process.binary": "brave"}}),
            5: ("Link", {"output-node-id": 1, "input-node-id": 4, "state": "active"}),
            6: ("Node", {"props": {"media.class": "Video/Source", "media.role": "Screen"}}),
            7: ("Node", {"props": {"media.class": "Stream/Input/Video", "application.process.binary": "brave"}}),
            8: ("Link", {"output-node-id": 6, "input-node-id": 7, "state": "active"}),
        }
        self.assertEqual(capture_status(graph, {"brave"})["indicators"], [
            {"icon": "󱡶", "hint": "Screen sharing\nBrave"},
            {"icon": "󰍬", "hint": "Microphone\nBrave\nRecorder"},
            {"icon": "󰖠", "hint": "Camera\nBrave"},
        ])
