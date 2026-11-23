import QtQuick
import QtQuick.Controls.Basic as Controls
import QtQuick.Layouts
import "Palette.js" as Ink

Column {
    id: plan
    required property var boardWindow
    required property Flickable viewport
    readonly property var state: boardWindow.tracking.plan || ({})
    readonly property string day: boardWindow.tracking.localDay || ""
    readonly property bool available: !!day && !state.error && !boardWindow.tracking.boardError
    readonly property var planned: state.tasks || []
    readonly property var carry: state.carry || []
    readonly property var byKey: {
        const lookup = Object.create(null)
        for (const n of boardWindow.items) lookup[n.key] = n
        return lookup
    }
    readonly property var pending: planned.filter(k => byKey[k] && !byKey[k].done)
    readonly property var done: planned.filter(k => byKey[k]?.done)
    readonly property var candidates: {
        const query = search.text.trim().toLowerCase()
        return boardWindow.items.filter(n => n.depth && !n.done && !planned.includes(n.key)
            && (n.title.toLowerCase().includes(query) || projectName(n).toLowerCase().includes(query)))
    }
    property bool expanded: true
    property bool picking: false
    property bool showCarry: false
    property bool showDone: false
    property string dragging: ""
    property var beforeDrag: []
    property real pointerY: 0
    property int insertion: -1
    spacing: 3

    function open() {
        expanded = true
        picking = false
        showCarry = false
        showDone = false
        stopDrag()
    }
    function change(action, extra) {
        boardWindow.send(action, Object.assign({day: day, fromPlan: true}, extra))
    }
    function projectName(item) { return byKey[item?.project]?.title || "" }
    function reorder(before, key, to) {
        const after = before.filter(k => k !== key)
        after.splice(to, 0, key)
        if (after.some((k, i) => before[i] !== k))
            change("planOrder", {before: before, order: after})
    }
    function stopDrag() { dragging = ""; insertion = -1 }
    function updateDrop() {
        const y = viewport.mapToItem(openRows, 0, pointerY).y
        insertion = Math.max(0, Math.min(pending.length, Math.floor(y / 46 + 0.5)))
    }
    onDayChanged: open()
    onPendingChanged: if (dragging && JSON.stringify(beforeDrag) !== JSON.stringify(pending)) stopDrag()
    onPickingChanged: {
        search.text = ""
        if (picking) Qt.callLater(() => search.forceActiveFocus())
    }
    Timer {
        interval: 40; repeat: true
        running: !!plan.dragging && (plan.pointerY < 24 || plan.pointerY > plan.viewport.height - 24)
        onTriggered: {
            const view = plan.viewport
            view.contentY = Math.max(0, Math.min(view.contentHeight - view.height,
                view.contentY + (plan.pointerY < 24 ? -10 : 10)))
            plan.updateDrop()
        }
    }
    component Label: Text {
        textFormat: Text.PlainText; elide: Text.ElideRight
        font.family: "Inter"; font.pixelSize: 12; color: Ink.muted
    }
    component TaskTitle: Controls.AbstractButton {
        id: title
        required property var task
        property string detail: ""
        Layout.fillWidth: true; Layout.fillHeight: true
        activeFocusOnTab: true; Accessible.name: (task?.title || "") + " · " + detail
        background: Rectangle { color: "transparent"; radius: 4; border.color: title.visualFocus ? Ink.lavender : "transparent" }
        contentItem: Column {
            spacing: 1
            topPadding: Math.max(0, (height - primary.implicitHeight - subtitle.implicitHeight - spacing) / 2)
            Label { id: primary; width: parent.width; text: title.task?.title || ""; color: Ink.text
                font.pixelSize: 14; font.strikeout: !!title.task?.done }
            Label { id: subtitle; width: parent.width; text: title.detail; font.pixelSize: 11 }
        }
    }
    RowLayout {
        width: parent.width
        TaskButton { label: (plan.planned.length || plan.carry.length ? (plan.expanded ? "▾  " : "▸  ") : "") + "Today"
            labelColor: Ink.text; onTriggered: { plan.expanded = !plan.expanded; plan.picking = false } }
        Label { Layout.fillWidth: true; text: plan.planned.length ? plan.done.length + " / " + plan.planned.length + " done" : "" }
        TaskButton { label: plan.picking ? "Done" : "+ Plan task"; labelColor: Ink.lavender
            enabled: plan.available && !boardWindow.busy
            onTriggered: { plan.expanded = true; plan.picking = !plan.picking; boardWindow.reset() } }
    }
    Label { visible: !!plan.state.error; width: parent.width; wrapMode: Text.Wrap; text: plan.state.error || "" }
    Column {
        width: parent.width; visible: plan.picking; spacing: 3
        PlaceField { id: search; width: parent.width; placeholderText: "Search tasks or projects"
            onAccepted: if (plan.candidates.length && !boardWindow.busy) plan.change("planAdd", {target: plan.candidates[0]}) }
        ListView {
            id: matches; width: parent.width; height: Math.min(contentHeight, 132)
            clip: true; model: plan.candidates; boundsBehavior: Flickable.StopAtBounds
            Controls.ScrollBar.vertical: Controls.ScrollBar {}
            delegate: RowLayout {
                required property var modelData
                width: matches.width - 8; height: 42
                TaskTitle { task: modelData; detail: plan.projectName(modelData)
                    enabled: !boardWindow.busy; onClicked: plan.change("planAdd", {target: modelData}) }
                TaskButton { label: "+ Add"; Accessible.name: "Plan " + modelData.title
                    enabled: !boardWindow.busy; onTriggered: plan.change("planAdd", {target: modelData}) }
            }
        }
        Label { visible: !plan.candidates.length
            text: search.text.trim() ? "No matching open tasks." : "No more open tasks to plan." }
    }
    Column {
        width: parent.width; visible: plan.expanded && !plan.picking; spacing: 2
        Item {
            id: openRows; width: parent.width; height: plan.pending.length * 46
            Column {
                width: parent.width
                Repeater {
                    model: plan.pending
                    Rectangle {
                        id: row
                        required property string modelData
                        required property int index
                        readonly property var task: plan.byKey[modelData]
                        readonly property var due: boardWindow.tracking.deadlines?.[modelData]
                        width: openRows.width; height: 46; radius: 6
                        color: boardWindow.selected === modelData ? Ink.selection : index === 0 ? Ink.field : "transparent"
                        RowLayout {
                            anchors.fill: parent; anchors.margins: 3; spacing: 3
                            Item {
                                Layout.preferredWidth: 18; Layout.fillHeight: true
                                Label { anchors.centerIn: parent; text: "⠿"; font.pixelSize: 16; color: handle.containsMouse ? Ink.lavender : Ink.muted }
                                MouseArea {
                                    id: handle; anchors.fill: parent; hoverEnabled: true; preventStealing: true
                                    enabled: !boardWindow.busy && plan.pending.length > 1
                                    cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                                    property real origin
                                    onPressed: mouse => { origin = mapToItem(plan.viewport, mouse.x, mouse.y).y }
                                    onPositionChanged: mouse => {
                                        if (!pressed) return
                                        const y = mapToItem(plan.viewport, mouse.x, mouse.y).y
                                        if (!plan.dragging && Math.abs(y - origin) < 5) return
                                        if (!plan.dragging) { plan.beforeDrag = plan.pending.slice(); plan.dragging = row.modelData }
                                        plan.pointerY = y
                                        plan.updateDrop()
                                    }
                                    onReleased: mouse => {
                                        const pt = mapToItem(plan.viewport, mouse.x, mouse.y)
                                        if (plan.dragging && pt.x >= 0 && pt.x < plan.viewport.width && pt.y >= 0 && pt.y < plan.viewport.height)
                                            plan.reorder(plan.beforeDrag, row.modelData, plan.insertion - (plan.insertion > row.index ? 1 : 0))
                                        plan.stopDrag()
                                    }
                                    onCanceled: plan.stopDrag()
                                }
                            }
                            TaskButton { label: "☐"; Accessible.name: "Complete " + (row.task?.title || "")
                                enabled: !boardWindow.busy; onTriggered: boardWindow.send("toggle", {target: row.task, fromPlan: true}) }
                            TaskTitle { task: row.task
                                detail: (row.index === 0 ? "Up next  ·  " : "") + plan.projectName(row.task)
                                    + (row.due ? "  ·  " + boardWindow.dateLabel(row.due) : "")
                                enabled: !boardWindow.busy
                                onClicked: boardWindow.selectRow(row.task) }
                            TaskButton { visible: row.index === 0
                                readonly property bool focusing: boardWindow.active?.sameNote === true && boardWindow.active.task === row.modelData
                                label: !focusing ? "Focus…" : boardWindow.active.status === "paused" ? "Paused"
                                    : boardWindow.active.status === "expired" ? "Time’s up" : "Focusing…"
                                labelColor: Ink.lavender; enabled: !boardWindow.busy && !focusing
                                onTriggered: boardWindow.begin("start", row.task, true) }
                            TaskButton { label: "⋯"; Accessible.name: "Today actions for " + (row.task?.title || "")
                                enabled: !boardWindow.busy; onTriggered: boardWindow.begin("todayMenu", row.task, true) }
                        }
                    }
                }
            }
            Rectangle { visible: !!plan.dragging; width: parent.width; height: 2; y: plan.insertion * 46 - 1; color: Ink.lavender }
        }
        Label { visible: plan.planned.length > 0 && !plan.pending.length; text: "All planned tasks done"; color: Ink.lavender }
        TaskButton { visible: !!plan.done.length; label: (plan.showDone ? "▾ " : "▸ ") + "Completed (" + plan.done.length + ")"
            onTriggered: plan.showDone = !plan.showDone }
        Repeater {
            model: plan.showDone ? plan.done : []
            RowLayout {
                required property string modelData
                readonly property var task: plan.byKey[modelData]
                width: plan.width; height: 40
                TaskButton { label: "☑"; Accessible.name: "Reopen " + (task?.title || "")
                    enabled: !boardWindow.busy; onTriggered: boardWindow.send("toggle", {target: task, fromPlan: true}) }
                TaskTitle { task: parent.task; detail: plan.projectName(parent.task); onClicked: boardWindow.selectRow(parent.task) }
                TaskButton { label: "Remove"; Accessible.name: "Remove from Today"; enabled: !boardWindow.busy
                    onTriggered: plan.change("planRemove", {key: modelData}) }
            }
        }
        RowLayout {
            visible: !!plan.carry.length; width: parent.width
            TaskButton { label: (plan.showCarry ? "▾ " : "▸ ") + "Carry over (" + plan.carry.length + ")"
                onTriggered: plan.showCarry = !plan.showCarry }
            Item { Layout.fillWidth: true }
            TaskButton { label: "Add all to today"; labelColor: Ink.lavender; enabled: !boardWindow.busy
                onTriggered: plan.change("planCarry", {keys: plan.carry}) }
        }
        Repeater {
            model: plan.showCarry ? plan.carry : []
            RowLayout {
                required property string modelData
                width: plan.width; height: 40
                TaskTitle { task: plan.byKey[modelData]; detail: plan.projectName(task); onClicked: boardWindow.selectRow(task) }
                TaskButton { label: "+ Add"; enabled: !boardWindow.busy; onTriggered: plan.change("planCarry", {keys: [modelData]}) }
                TaskButton { label: "Dismiss"; enabled: !boardWindow.busy; onTriggered: plan.change("planDismiss", {keys: [modelData]}) }
            }
        }
    }
}
