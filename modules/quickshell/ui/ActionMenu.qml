import QtQuick
import Quickshell
import Quickshell.Io
import "Palette.js" as Ink

PopupWindow {
    id: popup
    required property var command
    property string choicesArgument: "choices"
    property var entries: []
    property var parents: []
    property bool requested: false
    anchor.edges: Edges.Bottom; anchor.gravity: Edges.Bottom
    color: "transparent"; grabFocus: true
    implicitWidth: 285
    implicitHeight: Math.min(385, entries.reduce((h, row) => h + (row.heading ? 24 : 30), 16))

    function toggle() {
        if (visible) visible = false
        else {
            requested = !requested
            if (requested) reader.running = true
        }
    }
    function enter(row) {
        if (row.back) {
            entries = parents[parents.length - 1]
            parents = parents.slice(0, -1)
        } else if (row.children) {
            parents = parents.concat([entries])
            entries = [{label: "‹  " + row.label, back: true}].concat(row.children)
        } else if (row.target !== undefined) {
            Quickshell.execDetached(command.concat(["apply", JSON.stringify(row.target)]))
            visible = false
        }
        list.currentIndex = -1
        list.positionViewAtBeginning()
    }
    Process {
        id: reader
        command: popup.command.concat(popup.choicesArgument)
        stdout: StdioCollector {
            onStreamFinished: {
                if (!popup.requested) return
                popup.requested = false
                popup.parents = []
                popup.entries = text.trim() ? JSON.parse(text) : [{label: "Choices unavailable"}]
                list.currentIndex = -1
                popup.visible = true
            }
        }
    }
    Rectangle {
        anchors.fill: parent; radius: 9; color: Ink.panel; border.color: Ink.inactive
        ListView {
            id: list
            anchors { fill: parent; margins: 8 }
            clip: true; focus: true; model: popup.entries
            Keys.onEscapePressed: popup.visible = false
            Keys.onReturnPressed: if (currentIndex >= 0) popup.enter(popup.entries[currentIndex])
            Keys.onLeftPressed: if (popup.parents.length) popup.enter({back: true})
            delegate: Rectangle {
                id: row
                required property var modelData
                width: ListView.view.width; height: modelData.heading ? 24 : 30; radius: 6
                color: mouse.containsMouse || ListView.isCurrentItem ? Ink.selection : "transparent"
                Text {
                    anchors { left: parent.left; right: parent.right; margins: 9; verticalCenter: parent.verticalCenter }
                    text: row.modelData.heading || ((row.modelData.current ? "✓   " : "") + row.modelData.label + (row.modelData.children ? "   ›" : ""))
                    textFormat: Text.PlainText; elide: Text.ElideRight
                    font.family: "Inter"; font.pixelSize: row.modelData.heading ? 11 : 13; font.bold: !!row.modelData.heading
                    color: row.modelData.heading ? Ink.lavender : mouse.enabled ? Ink.text : Ink.inactive
                }
                MouseArea {
                    id: mouse
                    anchors.fill: parent; hoverEnabled: true
                    enabled: !!(row.modelData.children || row.modelData.back || row.modelData.target !== undefined)
                    cursorShape: Qt.PointingHandCursor
                    onClicked: popup.enter(row.modelData)
                }
            }
        }
    }
}
