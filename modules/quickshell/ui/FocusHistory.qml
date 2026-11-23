import QtQuick
import QtQuick.Controls.Basic as Controls
import QtQuick.Layouts
import Quickshell.Io
import "Config.js" as Config
import "Palette.js" as Ink

ColumnLayout {
    id: history
    required property var panelState
    required property var formatDuration
    signal back()
    signal closeWindow()
    property string filterDay: ""
    readonly property string day: filterDay || panelState.tracking.localDay || Qt.formatDate(new Date(), "yyyy-MM-dd")
    property var page: ({})
    property var undoStack: []
    property var request: null
    property string error: ""
    property bool refreshPending: false
    spacing: 8

    function refresh() {
        refreshPending = true
        if (visible && !request) reload.restart()
    }
    function run(action, fields) {
        if (request) return
        error = ""
        request = Object.assign({action: action, day: day, zone: panelState.clock.zone || "", board: action !== "historyDay"}, fields || {})
        worker.running = true
    }
    function complete(reply) {
        const action = request.action
        request = null
        if (reply.error) error = reply.error
        else if (action === "historyDay") page = reply
        else {
            if (reply.undo) undoStack = undoStack.concat([reply.undo])
            if (action === "undoDelete") undoStack = undoStack.slice(0, -1)
            if (reply.view) panelState.tracking = Object.assign({}, panelState.tracking, reply.view)
            refreshPending = true
        }
        if (refreshPending && visible) reload.restart()
    }
    onVisibleChanged: if (visible) { filterDay = ""; refresh() }
    onDayChanged: refresh()
    Connections {
        target: history.panelState
        function onTrackingChanged() { if (history.visible) history.refresh() }
    }
    Timer {
        id: reload; interval: 0
        onTriggered: if (history.visible && !history.request) {
            history.refreshPending = false
            history.run("historyDay")
        }
    }
    Process {
        id: worker; command: Config.commands.focus.concat("apply"); stdinEnabled: true
        onStarted: write(JSON.stringify(history.request) + "\n")
        stdout: StdioCollector { onStreamFinished: {
            try { history.complete(JSON.parse(text)) }
            catch (e) { history.request = null; history.error = "Could not read focus history." }
        } }
    }
    component Caption: Text {
        color: Ink.muted; font.family: "Inter"; font.pixelSize: 12; textFormat: Text.PlainText; elide: Text.ElideRight
    }
    RowLayout {
        Layout.fillWidth: true
        TaskButton { label: "‹ Tasks"; onTriggered: history.back() }
        Caption { Layout.fillWidth: true; text: "Focus history"; color: Ink.text; font.bold: true; font.pixelSize: 18 }
        TaskButton { label: "×"; Accessible.name: "Close focus history"; onTriggered: history.closeWindow() }
    }
    RowLayout {
        Layout.fillWidth: true
        TaskButton { label: "‹"; Accessible.name: "Previous day with records"; enabled: !!history.page.earlier; onTriggered: history.filterDay = history.page.earlier }
        Caption { Layout.fillWidth: true; text: Qt.formatDate(new Date(history.day + "T12:00:00"), "dddd, MMM d, yyyy"); color: Ink.text; horizontalAlignment: Text.AlignHCenter }
        TaskButton { label: "›"; Accessible.name: "Next day with records"; enabled: !!history.page.later; onTriggered: history.filterDay = history.page.later }
        TaskButton { label: "Today"; enabled: !!history.filterDay; onTriggered: history.filterDay = "" }
    }
    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Ink.inactive }
    Caption {
        visible: history.page.day === history.day && !history.page.records?.length
        text: "No focus sessions for this day."
    }
    ListView {
        Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 4
        model: history.page.day === history.day ? history.page.records || [] : []
        Controls.ScrollBar.vertical: Controls.ScrollBar {}
        delegate: Rectangle {
            id: row
            required property var modelData
            width: ListView.view.width - 8; height: 48; radius: 6; color: Ink.field
            readonly property var record: modelData
            readonly property bool finished: record.status === "finished"
            readonly property date started: new Date(record.started * 1000)
            readonly property int seconds: {
                if (record.running == null) return record.seconds
                const end = Math.min(history.page.stop, record.cutoff ?? Infinity)
                const from = Math.max(history.page.start, record.running, history.page.asOf)
                return record.seconds + Math.max(0, Math.min(end, history.panelState.focusNow) - from)
            }
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 5
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 1
                    Caption { Layout.fillWidth: true; text: row.record.title; color: Ink.text; font.pixelSize: 14 }
                    Caption { Layout.fillWidth: true; text: "Started " + Qt.formatDateTime(row.started,
                        Qt.formatDate(row.started, "yyyy-MM-dd") === history.day ? "HH:mm" : "MMM d, HH:mm")
                        + (row.finished ? "" : " · " + row.record.status) }
                }
                ColumnLayout {
                    spacing: 1
                    Caption { text: history.formatDuration(row.seconds) + (row.record.total > row.record.seconds ? " this day" : ""); color: Ink.lavender }
                    Caption {
                        visible: row.record.total > row.record.seconds
                        text: history.formatDuration(row.record.total + (row.record.running == null ? 0 :
                            Math.max(0, Math.min(history.panelState.focusNow, row.record.cutoff ?? Infinity) - history.page.asOf))) + " session"
                    }
                }
                TaskButton {
                    label: row.finished ? "Delete" : "Finish"
                    enabled: !history.request
                    onTriggered: row.finished ? history.run("deleteRecord", {recordId: row.record.id})
                                              : history.run("finish", {session: row.record.id})
                }
            }
        }
    }
    Caption { Layout.fillWidth: true; visible: !!history.error; text: history.error; wrapMode: Text.Wrap }
    RowLayout {
        Layout.fillWidth: true
        Caption { Layout.fillWidth: true; text: history.undoStack.length ? "Deleted · " + history.undoStack[history.undoStack.length - 1].record.title : history.panelState.focusTodayLabel }
        TaskButton { visible: history.undoStack.length > 0; label: "Undo"; enabled: !history.request
            onTriggered: history.run("undoDelete", {undo: history.undoStack[history.undoStack.length-1]}) }
    }
}
