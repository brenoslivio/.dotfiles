import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import "Config.js" as Config
import "Palette.js" as Ink

ColumnLayout {
    id: page
    required property var display
    property string pending: ""
    property string error: ""
    spacing: 6
    onDisplayChanged: {
        if (!display.connected || display.current === pending) pending = ""
        if (!display.connected) error = ""
    }
    Timer {
        interval: 10000; running: !!page.pending
        onTriggered: {
            page.error = "The layout change wasn’t confirmed. Check the display and try again."
            page.pending = ""
        }
    }
    Process {
        id: writer
        stderr: StdioCollector {
            onStreamFinished: if (text.trim()) { page.error = text.trim(); page.pending = "" }
        }
    }
    Text {
        Layout.fillWidth: true; visible: !!text; color: Ink.muted
        wrapMode: Text.Wrap; textFormat: Text.PlainText
        text: page.display.connected === undefined ? "Display status unavailable."
            : !page.display.connected ? "Laptop display · Connect an HDMI display to choose a layout."
            : page.error
    }
    Repeater {
        model: ScriptModel { values: page.display.modes ?? [] }
        QuickChoice {
            required property string modelData
            Layout.fillWidth: true
            text: modelData
            current: page.display.current === modelData
            detail: modelData === "Mirror" ? "Show the same desktop on both screens"
                : modelData === "Docked" ? "Use the external display only"
                : modelData === "Extend · Laptop main" ? "Numbered workspaces on the laptop"
                : "Numbered workspaces on the external display"
            trailing: current ? "✓" : page.pending === modelData ? "Applying…" : ""
            enabled: !!page.display.connected && !page.pending && !writer.running
            onClicked: {
                if (current) return
                page.error = ""
                page.pending = modelData
                writer.command = Config.commands.displays.concat(["set", modelData])
                writer.running = true
            }
        }
    }
}
