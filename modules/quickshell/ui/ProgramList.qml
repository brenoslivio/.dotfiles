import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic as Controls
import Quickshell.Io
import "Config.js" as Config
import "Palette.js" as Ink

ColumnLayout {
    id: table
    required property var state
    required property string ranking
    required property bool showing
    signal sortBy(string metric)
    spacing: 5
    readonly property int memoryWidth: 104
    readonly property int cpuWidth: 68
    readonly property int scrollGutter: 8
    property var selection: null
    property var confirmation: null
    property string result: ""
    function reset() {
        selection = null
        confirmation = null
        result = ""
        search.clear()
        list.positionViewAtBeginning()
    }
    readonly property var rows: {
        if (!showing) return []
        const groups = new Map()
        const estimates = state.memory.estimates ?? {}
        const query = search.text.trim().toLowerCase()
        for (const proc of state.cpu.members ?? []) {
            if (query && !proc.name.toLowerCase().includes(query)) continue
            let group = groups.get(proc.name)
            if (!group) {
                group = {name: proc.name, members: [], memory: 0, cpu: 0}
                groups.set(proc.name, group)
            }
            const memory = estimates[proc.pid + "/" + proc.start] ?? proc.rss
            group.members.push([proc.pid, proc.start])
            group.memory += memory
            group.cpu += proc.cpu
        }
        const metric = ranking === "CPU" ? "cpu" : "memory"
        return Array.from(groups.values()).sort((a, b) => b[metric] - a[metric] || a.name.localeCompare(b.name))
    }
    function choose(target) {
        if (!target || confirmation || killer.running) return
        selection = {name: target.name, members: target.members}
        result = ""
    }
    function size(kib) {
        return kib >= 1048576 ? (kib / 1048576).toFixed(1) + " GiB" : Math.round(kib / 1024) + " MiB"
    }
    Process {
        id: killer
        command: Config.commands.resources.concat("force-quit")
        property var target
        onStarted: write(JSON.stringify(target) + "\n")
        stdout: StdioCollector {
            onStreamFinished: {
                if (!text.trim()) return
                const r = JSON.parse(text)
                table.result = killer.target.name + " · " + [
                    r.signalled && r.signalled + " sent SIGKILL", r.gone && r.gone + " already exited or changed",
                    r.denied && r.denied + " permission denied", r.failed && r.failed + " failed"
                ].filter(Boolean).join(", ")
            }
        }
        onExited: code => { if (code) table.result = "Force quit failed. Refresh the selection and try again." }
    }
    PlaceField {
        id: search
        Layout.fillWidth: true; placeholderText: "Search programs"; Accessible.name: placeholderText
        onTextEdited: list.positionViewAtBeginning()
    }
    RowLayout {
        Layout.fillWidth: true; Layout.rightMargin: table.scrollGutter; spacing: 2
        Text { Layout.fillWidth: true; text: "Program"; color: Ink.text; font.family: "Inter"; font.pixelSize: 13 }
        Repeater {
            model: ["Memory", "CPU"]
            TaskButton {
                required property string modelData
                Layout.minimumWidth: modelData === "Memory" ? table.memoryWidth : table.cpuWidth
                Layout.preferredWidth: Layout.minimumWidth
                label: modelData + (table.ranking === modelData ? " ↓" : "")
                selected: table.ranking === modelData; Accessible.name: "Sort by " + modelData
                onTriggered: { table.sortBy(modelData); list.positionViewAtBeginning() }
            }
        }
    }
    ListView {
        id: list
        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
        model: table.rows.length; boundsBehavior: Flickable.StopAtBounds
        Controls.ScrollBar.vertical: Controls.ScrollBar {}
        delegate: Controls.AbstractButton {
            id: entry
            required property int index
            readonly property var row: table.rows[index]
            property var pressedTarget
            width: ListView.view.width - table.scrollGutter; height: 29
            padding: 0; hoverEnabled: true
            Accessible.name: row?.name ?? ""
            onPressed: pressedTarget = row
            onClicked: { table.choose(pressedTarget ?? row); pressedTarget = null }
            background: Rectangle {
                radius: 5
                color: table.selection && table.selection.name === entry.row?.name ? Ink.selection
                    : entry.hovered ? Ink.field : "transparent"
                border.color: entry.visualFocus ? Ink.lavender : "transparent"
            }
            contentItem: RowLayout {
                spacing: 2
                Text {
                    Layout.fillWidth: true; leftPadding: 4; elide: Text.ElideRight
                    text: entry.row?.name ?? ""; textFormat: Text.PlainText
                    color: Ink.text; font.family: "Inter"; font.pixelSize: 12
                }
                Text {
                    Layout.preferredWidth: table.memoryWidth; horizontalAlignment: Text.AlignHCenter
                    text: table.size(entry.row?.memory ?? 0); color: Ink.muted; font.pixelSize: 12
                }
                Text {
                    Layout.preferredWidth: table.cpuWidth; horizontalAlignment: Text.AlignHCenter
                    text: (entry.row?.cpu ?? 0).toFixed(1) + "%"; color: Ink.muted; font.pixelSize: 12
                }
            }
        }
        Text { anchors.centerIn: parent; visible: list.count === 0; text: "No matching programs"; color: Ink.muted }
    }
    Text {
        Layout.fillWidth: true; visible: !!text; wrapMode: Text.Wrap; textFormat: Text.PlainText
        color: Ink.text; font.family: "Inter"; font.pixelSize: 12
        text: table.confirmation ? "Force quit " + table.confirmation.name + "? Unsaved work may be lost." : table.result
    }
    RowLayout {
        Layout.fillWidth: true; visible: !!table.selection || !!table.confirmation
        Text { Layout.fillWidth: true; elide: Text.ElideRight; color: Ink.muted; textFormat: Text.PlainText; text: table.selection ? table.selection.name : "" }
        TaskButton { visible: !!table.confirmation; label: "Cancel"; onTriggered: table.confirmation = null }
        TaskButton {
            label: table.confirmation ? "Force quit now" : "Force quit…"; enabled: !killer.running
            onTriggered: {
                if (!table.confirmation) { table.confirmation = table.selection; return }
                killer.target = table.confirmation
                killer.stdinEnabled = true
                killer.running = true
                table.confirmation = null
                table.selection = null
            }
        }
    }
}
