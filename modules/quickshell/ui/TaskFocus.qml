import QtQuick
import QtQuick.Layouts
import "Palette.js" as Ink

RowLayout {
    id: strip
    required property var session
    required property double now
    required property bool busy
    signal control(string action)
    signal reveal()
    spacing: 4
    TaskButton {
        label: {
            if (!strip.session) return ""
            const state = strip.session.status
            let prefix = state === "expired" ? "Time’s up" : state === "paused" ? "Paused" : "Focusing"
            if (state === "running" && strip.session.cutoff != null) {
                const s = Math.max(0, Math.ceil(strip.session.cutoff - strip.now))
                prefix = Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0")
            }
            return prefix + " · " + strip.session.title
        }
        Layout.maximumWidth: Math.max(80, strip.width - 140)
        labelColor: Ink.lavender; hint: strip.session?.title || ""; onTriggered: strip.reveal()
    }
    Item { Layout.fillWidth: true }
    TaskButton {
        enabled: !strip.busy
        label: strip.session?.status === "expired" ? "Extend…" : strip.session?.status === "paused" ? "Resume" : "Pause"
        onTriggered: strip.control(strip.session.status === "expired" ? "extend" : strip.session.status === "paused" ? "resume" : "pause")
    }
    TaskButton { label: "Finish"; enabled: !strip.busy; onTriggered: strip.control("finish") }
}
