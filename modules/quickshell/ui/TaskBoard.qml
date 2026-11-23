import QtQuick
import QtQuick.Controls.Basic as Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import Quickshell.Wayland
import "Config.js" as Config
import "Palette.js" as Ink

PanelWindow {
    id: board
    required property var panelState
    readonly property var tracking: panelState.tracking
    readonly property var items: tracking.items || []
    readonly property var active: tracking.active
    readonly property string zone: panelState.clock.zone || ""
    readonly property string today: panelState.clock.date || Qt.formatDate(new Date(), "yyyy-MM-dd")
    property string selected: ""
    readonly property var current: items.find(n => n.key === selected)
    property var collapsed: ({})
    property bool showDone: false
    property bool historyOpen: false
    readonly property var projects: items.filter(n => !n.depth)
    property var dragSource: null
    property var dragOrder: []
    property var dropProject: null
    property bool dropAfter: false
    property real dropLine: 0
    property real dragY: 0
    property string form: ""
    property var target: null
    property string input: ""
    property bool formFromPlan: false
    property string operation: ""
    property string problem: ""
    property var dueBefore: null
    property var destinationItem: null
    property var request: null
    property var anchorButton
    readonly property bool busy: !!request
    readonly property bool editingTitle: ["project","add","rename"].includes(form)
    readonly property bool orphan: !!target && !items.some(n => n.key === target.key)
    readonly property var destinations: items.filter(n => !n.depth && n.key !== target?.project)
    readonly property int completed: items.filter(n => n.done).length
    visible: false
    anchors { top: true; left: true }
    implicitWidth: Math.min(534, (screen?.width || 550) - 16)
    implicitHeight: Math.min((screen?.height || 680) - margins.top - 12, form === "deadline" ? 680 : 530)
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "dotfiles-task-board"
    WlrLayershell.keyboardFocus: focusPulse.running ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.OnDemand
    color: "transparent"
    HyprlandFocusGrab {
        windows: [board]
        active: board.visible
        onCleared: board.visible = false
    }
    Timer { id: focusPulse; interval: 150 }
    TaskNotepad { id: recovery }

    function reveal(key) {
        const item = items.find(n => n.key === key)
        if (!item) return
        selected = key
        collapsed = Object.assign({}, collapsed, {[item.project]: false})
        if (item.done) showDone = true
        Qt.callLater(scrollTo, key)
    }
    function scrollTo(key) {
        for (let i = 0; i < rows.count; ++i) {
            const row = rows.itemAt(i)
            if (!row || row.modelData.key !== key) continue
            if (row.y < list.contentY) list.contentY = row.y
            else if (row.y + row.height > list.contentY + list.height)
                list.contentY = Math.min(Math.max(0, list.contentHeight - list.height), row.y + row.height - list.height)
            return
        }
    }
    function openAt(button, key) {
        anchorButton = button
        const bar = button.QsWindow.window
        screen = bar.screen
        const center = bar.margins.left + button.mapToItem(null, button.width / 2, 0).x
        margins.left = Math.max(8, Math.min(screen.width - implicitWidth - 8, center - implicitWidth / 2))
        margins.top = bar.margins.top + bar.height + 4
        visible = true
        historyOpen = false
        focusPulse.restart()
        if (!busy) {
            reset()
            planner.open()
            if (key) reveal(key)
            else list.contentY = 0
        }
    }
    function reset() { formFromPlan = false; form = ""; target = null; input = ""; problem = "" }
    function begin(action, item, fromPlan = false) {
        if (busy) return
        reset()
        formFromPlan = fromPlan
        if (!fromPlan) planner.picking = false
        target = item || null
        if (action === "move" || action === "transfer")
            destinationItem = items.find(n => !n.depth && n.key !== item.project) || null
        if (action === "project" || action === "add")
            operation = Date.now().toString(36) + "-" + Math.random().toString(36).slice(2)
        if (item) selected = item.key
        input = action === "rename" ? item.title : action === "extend" ? "5m" : ""
        dueBefore = item ? tracking.deadlines?.[item.key] || null : null
        form = action
        if (action === "project") list.contentY = 0
        if (item && action === "add") reveal(item.key)
        if (item && !fromPlan) Qt.callLater(scrollTo, action === "add" && !item.depth ? "add/" + item.key : item.key)
    }
    function send(action, extra) {
        if (busy) return
        problem = ""
        request = Object.assign({action: action, board: true, zone: zone, target: target, operation: operation,
            session: active?.id || "", fromPlan: formFromPlan}, extra || {})
        worker.running = true
    }
    function complete(reply) {
        const action = request.action, old = target, fromPlan = request.fromPlan
        request = null
        if (reply.view) panelState.tracking = Object.assign({}, tracking, reply.view)
        if (reply.error) {
            if (reply.key && items.some(n => n.key === reply.key)) {
                target = items.find(n => n.key === reply.key)
                if (!fromPlan) reveal(reply.key)
            }
            problem = reply.error
            return
        }
        if (action === "planOrder" && form === "todayMenu") return
        reset()
        if (fromPlan) {
            if (reply.key) selected = reply.key
            return
        }
        if (action === "add") {
            const parent = items.find(n => n.key === reply.parent)
            if (parent) begin("add", parent)
        } else if (reply.key && items.some(n => n.key === reply.key && (!n.done || showDone))) reveal(reply.key)
        else if (reply.parent) reveal(reply.parent)
        else if (!current && old) selected = old.project
    }
    function dateLabel(due) {
        if (!due) return ""
        const date = new Date(due.date + "T12:00:00")
        const next = new Date(today + "T12:00:00"); next.setDate(next.getDate() + 1)
        const day = due.date === today ? "Today" : due.date === Qt.formatDate(next, "yyyy-MM-dd") ? "Tomorrow"
            : Qt.formatDate(date, due.date.slice(0, 4) === today.slice(0, 4) ? "MMM d" : "MMM d, yyyy")
        return (due.date < today ? "Overdue · " : "") + day + (due.time ? " " + due.time : "")
    }
    function elapsed(seconds) {
        const h = Math.floor(seconds / 3600), m = Math.floor(seconds / 60) % 60
        return h ? h + "h " + m + "m" : m ? m + "m" : Math.floor(seconds) + "s"
    }
    function selectRow(item) { if (!busy) { reset(); selected = item.key } }
    function moveProject(source, destination, after, order) {
        if (!source || !destination || busy) return
        const next = order.filter(key => key !== source.key)
        next.splice(next.indexOf(destination.key) + (after ? 1 : 0), 0, source.key)
        if (next.every((key, i) => key === order[i])) return
        send("reorder", {target: source, destination: destination, after: after, order: order})
    }
    function nudge(step) {
        const index = projects.findIndex(p => p.key === current?.key)
        moveProject(current, projects[index + step], step > 0, projects.map(p => p.key))
    }
    function findDrop(y) {
        dragY = y
        const at = y + list.contentY
        if (at < projectsHeading.y) { dropProject = null; return }
        let last = null
        for (let i = 0; i < rows.count; ++i) {
            const row = rows.itemAt(i)
            if (!row?.project || row.n.key === dragSource?.key) continue
            if (at < row.y + row.height / 2) {
                dropProject = row.n; dropAfter = false; dropLine = row.y
                return
            }
            last = row.n
        }
        dropProject = last; dropAfter = true; dropLine = content.height - 2
    }
    function endDrag() { dragSource = null; dropProject = null }
    Timer {
        interval: 35; repeat: true
        running: !!board.dragSource && (board.dragY < 32 || board.dragY > list.height - 32)
        onTriggered: {
            list.contentY = Math.max(0, Math.min(Math.max(0, list.contentHeight - list.height),
                list.contentY + (board.dragY < 32 ? -12 : 12)))
            board.findDrop(board.dragY)
        }
    }
    onVisibleChanged: if (!visible) endDrag()
    onItemsChanged: if (dragSource) endDrag()
    readonly property var listModel: {
        const model = []
        let project = null
        for (const n of items) {
            if (!n.depth) {
                if (project && !collapsed[project.key]) model.push({add: true, key: "add/" + project.key, parentItem: project})
                project = n
            }
            if (!n.depth || (!collapsed[n.project] && (showDone || !n.done))) model.push(n)
        }
        if (project && !collapsed[project.key]) model.push({add: true, key: "add/" + project.key, parentItem: project})
        return model
    }
    onZoneChanged: if (form === "deadline") reset()
    Process {
        id: worker; command: Config.commands.focus.concat("apply"); stdinEnabled: true
        onStarted: write(JSON.stringify(board.request) + "\n")
        stdout: StdioCollector { onStreamFinished: {
            try { board.complete(JSON.parse(text)) }
            catch (e) { board.request = null; board.problem = "Could not read the task helper response." }
        } }
    }
    Shortcut { sequence: "Escape"; enabled: board.visible && !board.busy; onActivated: { if (board.dragSource) board.endDrag(); else if (board.historyOpen) board.historyOpen = false; else if (board.form) board.reset(); else if (planner.picking) planner.picking = false; else board.visible = false } }
    component Caption: Text {
        color: Ink.muted; font.family: "Inter"; font.pixelSize: 12
        textFormat: Text.PlainText; elide: Text.ElideRight
    }
    Component {
        id: titleEditor
        RowLayout {
            PlaceField {
                id: name; Layout.fillWidth: true
                placeholderText: board.form === "project" ? "Project name" : board.form === "add" ? "New task" : "Name"
                text: board.input; onTextEdited: board.input = text
                Component.onCompleted: { forceActiveFocus(); if (board.form === "rename") selectAll() }
                onAccepted: if (saveName.enabled) saveName.triggered(Qt.LeftButton)
            }
            TaskButton { id: saveName; label: board.form === "rename" ? "Save" : "Add"; labelColor: Ink.lavender
                enabled: !!board.input.trim() && !board.busy && !board.orphan
                onTriggered: board.send(board.form, {title: board.input}) }
            TaskButton { label: "Cancel"; onTriggered: board.reset() }
        }
    }
    Rectangle {
        anchors.fill: parent; color: Ink.panel; radius: 12; border.color: Ink.inactive
        FocusHistory {
            anchors.fill: parent; anchors.margins: 14; visible: board.historyOpen
            panelState: board.panelState; formatDuration: board.elapsed
            onBack: board.historyOpen = false
            onCloseWindow: board.visible = false
        }
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 14; spacing: 6
            visible: !board.historyOpen
            RowLayout {
                Layout.fillWidth: true
                Caption { text: "Projects & tasks"; color: Ink.text; font.pixelSize: 19; font.bold: true; Layout.fillWidth: true }
                TaskButton { label: "Recover draft…"; visible: !!board.tracking.draft || !!board.tracking.legacy
                    onTriggered: { board.visible = false; recovery.openAt(board.anchorButton) } }
                TaskButton { label: "+ Project"; labelColor: Ink.lavender; enabled: !board.busy && !board.tracking.boardError; onTriggered: board.begin("project") }
                TaskButton { label: "×"; Accessible.name: "Close tasks"; enabled: !board.busy; onTriggered: board.visible = false }
            }
            TaskFocus {
                Layout.fillWidth: true; visible: !!board.active
                session: board.active; now: board.panelState.focusNow; busy: board.busy
                onReveal: if (board.active.sameNote) board.reveal(board.active.task)
                onControl: action => { if (action === "extend") board.begin(action); else board.send(action) }
            }
            Loader { Layout.fillWidth: true; visible: active; active: board.form === "project" || (board.editingTitle && board.orphan); sourceComponent: titleEditor }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Ink.inactive; opacity: 0.55 }
            Flickable {
                id: list; Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 42
                clip: true; contentWidth: width; contentHeight: content.implicitHeight
                boundsBehavior: Flickable.StopAtBounds
                Controls.ScrollBar.vertical: Controls.ScrollBar {}
                Column {
                    id: content; width: list.width - 8; spacing: 2
                    TodayPlan { id: planner; width: parent.width; boardWindow: board; viewport: list }
                    Caption { id: projectsHeading; text: "Projects"; font.bold: true; topPadding: 8; bottomPadding: 4 }
                    Caption {
                        visible: !board.items.length; width: parent.width; wrapMode: Text.Wrap
                        text: board.tracking.boardError || board.tracking.error || (board.tracking.items ? "Add a project to start your list." : "Loading tasks…")
                    }
                    Repeater {
                        id: rows; model: board.listModel
                        Column {
                            id: entry
                            required property var modelData
                            readonly property var n: modelData
                            readonly property bool project: !n.add && n.depth === 0
                            readonly property var due: board.tracking.deadlines?.[n.key]
                            width: content.width; spacing: 2
                            Rectangle {
                                width: parent.width; height: entry.n.add ? 27 : entry.project ? 39 : 33
                                radius: 6; color: board.selected === entry.n.key ? Ink.selection : entry.project ? Ink.field : "transparent"
                                border.color: board.dragSource?.key === entry.n.key ? Ink.lavender : "transparent"
                                RowLayout {
                                    anchors.fill: parent; anchors.leftMargin: entry.n.add ? 28 : entry.project ? 4 : Math.min(80, 16 * entry.n.depth)
                                    anchors.rightMargin: 4; spacing: 2
                                    Item {
                                        visible: entry.project; Layout.preferredWidth: 18; Layout.fillHeight: true
                                        Accessible.name: "Reorder " + (entry.n.title || "")
                                        Text { anchors.centerIn: parent; text: "⠿"; font.pixelSize: 17; color: grip.containsMouse ? Ink.lavender : Ink.muted }
                                        MouseArea {
                                            id: grip; anchors.fill: parent; hoverEnabled: true; preventStealing: true
                                            enabled: !board.busy && board.projects.length > 1
                                            cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                                            property real originY
                                            onPressed: mouse => { originY = mapToItem(list, mouse.x, mouse.y).y }
                                            onPositionChanged: mouse => {
                                                if (!pressed) return
                                                const y = mapToItem(list, mouse.x, mouse.y).y
                                                if (!board.dragSource && Math.abs(y - originY) < 5) return
                                                if (!board.dragSource) {
                                                    board.dragOrder = board.projects.map(p => p.key)
                                                    board.dragSource = entry.n
                                                }
                                                board.findDrop(y)
                                            }
                                            onReleased: mouse => {
                                                const pt = mapToItem(list, mouse.x, mouse.y)
                                                if (board.dragSource && pt.x >= 0 && pt.x < list.width && pt.y >= 0 && pt.y < list.height)
                                                    board.moveProject(board.dragSource, board.dropProject, board.dropAfter, board.dragOrder)
                                                board.endDrag()
                                            }
                                            onCanceled: board.endDrag()
                                        }
                                    }
                                    TaskButton {
                                        visible: !entry.n.add
                                        label: entry.project ? (board.collapsed[entry.n.key] ? "▸" : "▾") : entry.n.done ? "☑" : "☐"
                                        Accessible.name: entry.project ? "Expand or collapse " + entry.n.title : "Toggle completion of " + entry.n.title
                                        enabled: !board.busy
                                        onTriggered: {
                                            if (entry.project) board.collapsed = Object.assign({}, board.collapsed, {[entry.n.key]: !board.collapsed[entry.n.key]})
                                            else { board.selectRow(entry.n); board.send("toggle", {target: entry.n}) }
                                        }
                                    }
                                    Controls.AbstractButton {
                                        id: title; Layout.fillWidth: true; Layout.fillHeight: true
                                        text: entry.n.add ? "+ Add task" : entry.n.title
                                        Accessible.name: text; activeFocusOnTab: true; enabled: !board.busy
                                        contentItem: Text { text: title.text; textFormat: Text.PlainText; font.family: "Inter"
                                            font.pixelSize: entry.n.add ? 12 : 14; font.bold: entry.project
                                            font.strikeout: !!entry.n.done; color: entry.n.add ? Ink.lavender : entry.n.done ? Ink.muted : Ink.text
                                            verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
                                        background: Rectangle {
                                            color: "transparent"; radius: 3
                                            border.color: title.visualFocus ? Ink.lavender : "transparent"
                                        }
                                        onClicked: {
                                            if (entry.n.add) board.begin("add", entry.n.parentItem)
                                            else board.selectRow(entry.n)
                                        }
                                    }
                                    Caption { visible: entry.project; text: entry.project ? String(board.items.filter(n => n.depth && n.project === entry.n.key && !n.done).length) + " open" : ""; font.pixelSize: 11 }
                                    TaskButton { visible: !entry.n.add && (!!entry.due || board.selected === entry.n.key)
                                        label: entry.due ? board.dateLabel(entry.due) : "Due…"; labelColor: entry.due ? Ink.lavender : Ink.muted
                                        Accessible.name: "Deadline for " + (entry.n.title || "")
                                        enabled: !board.busy && !entry.n.done; onTriggered: board.begin("deadline", entry.n) }
                                    TaskButton { visible: !entry.n.add; label: "⋯"; Accessible.name: "Actions for " + (entry.n.title || "")
                                        enabled: !board.busy; onTriggered: board.begin("menu", entry.n) }
                                }
                            }
                            Loader {
                                width: parent.width; visible: active
                                active: (board.form === "rename" && board.target?.key === entry.n.key)
                                    || (board.form === "add" && (board.target?.depth ? board.target.key === entry.n.key : entry.n.add && entry.n.parentItem.key === board.target?.key))
                                sourceComponent: titleEditor
                            }
                        }
                    }
                }
                Rectangle {
                    y: board.dropLine; width: content.width; height: 2; radius: 1; z: 2
                    color: Ink.lavender; visible: !!board.dragSource && !!board.dropProject
                }
            }
            TaskButton { visible: board.completed > 0; label: board.showDone ? "Hide completed" : "Show completed (" + board.completed + ")"
                onTriggered: board.showDone = !board.showDone }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Ink.inactive; opacity: 0.55; visible: !!board.current || !!board.form }
            RowLayout {
                visible: !!board.current && board.form !== "deadline"
                Layout.fillWidth: true
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 2
                    Caption { Layout.fillWidth: true; text: board.current?.title || ""; color: Ink.text; font.bold: true }
                    Caption {
                        visible: !!board.current?.depth; Layout.fillWidth: true
                        text: {
                            const key = board.selected, a = board.active, t = board.tracking
                            const start = a?.sameNote && a.task === key ? a.running_since : null
                            const end = Math.min(board.panelState.focusNow, a?.cutoff ?? board.panelState.focusNow)
                            const live = start == null ? 0 : Math.max(0, end - start)
                            const today = (t.today?.[key] || 0) + (start == null ? 0 : Math.max(0, end - Math.max(t.midnight, start)))
                            return "Today " + board.elapsed(today) + " · Total " + board.elapsed((t.totals?.[key] || 0) + live)
                        }
                    }
                }
                TaskButton { visible: !!board.current?.depth && !board.current?.done; label: "Focus…"; enabled: !board.busy; onTriggered: board.begin("start", board.current) }
                TaskButton { label: "Deadline…"; enabled: !board.busy && !board.current?.done; onTriggered: board.begin("deadline", board.current) }
            }
            RowLayout {
                visible: board.form === "todayMenu" && planner.pending.includes(board.selected)
                enabled: !board.busy
                TaskButton { label: "Move up"; enabled: planner.pending.indexOf(board.selected) > 0
                    onTriggered: planner.reorder(planner.pending, board.selected, planner.pending.indexOf(board.selected) - 1) }
                TaskButton { label: "Move down"; enabled: planner.pending.indexOf(board.selected) < planner.pending.length - 1
                    onTriggered: planner.reorder(planner.pending, board.selected, planner.pending.indexOf(board.selected) + 1) }
                TaskButton { label: "Remove from Today"; onTriggered: planner.change("planRemove", {key: board.selected}) }
            }
            RowLayout {
                visible: board.form === "menu"; enabled: !board.busy
                TaskButton { label: "Rename"; onTriggered: board.begin("rename", board.current) }
                TaskButton { label: board.current?.depth ? "Add subtask" : "Add task"; onTriggered: board.begin("add", board.current) }
                TaskButton { label: "Move up"; visible: board.current?.depth === 0; enabled: board.current?.key !== board.projects[0]?.key; onTriggered: board.nudge(-1) }
                TaskButton { label: "Move down"; visible: board.current?.depth === 0; enabled: board.current?.key !== board.projects[board.projects.length-1]?.key; onTriggered: board.nudge(1) }
                TaskButton { label: "Move…"; visible: !!board.current?.depth; onTriggered: board.begin("move", board.current) }
                TaskButton { label: planner.planned.includes(board.selected) ? "Remove from Today" : "Do today"
                    visible: !!board.current?.depth && !board.current?.done; enabled: planner.available
                    onTriggered: planner.change(planner.planned.includes(board.selected) ? "planRemove" : "planAdd", {target: board.current, key: board.selected}) }
                TaskButton { label: "Delete…"; onTriggered: board.begin("delete", board.current) }
            }
            ColumnLayout {
                Layout.fillWidth: true; visible: ["delete","transfer","move"].includes(board.form)
                Caption { Layout.fillWidth: true; wrapMode: Text.Wrap
                    text: board.form === "delete" ? "Delete “" + (board.target?.title || "") + "”" + (board.descendants ? " and its " + board.descendants + " nested items?" : "?")
                        : board.form === "transfer" ? "Move the tasks to this project, then delete the original project." : "Move this task and its subtasks to a project." }
                RowLayout {
                    Controls.ComboBox {
                        id: destination; visible: board.form !== "delete"; Layout.fillWidth: true
                        model: board.destinations.concat([{title: "New project…"}]); textRole: "title"
                        currentIndex: board.destinationItem ? board.destinations.findIndex(n => n.key === board.destinationItem.key) : board.destinations.length
                        onActivated: index => board.destinationItem = board.destinations[index] || null
                    }
                    TaskButton { visible: board.form === "delete" && board.target?.depth === 0 && board.descendants > 0
                        label: "Move tasks first…"; onTriggered: board.begin("transfer", board.target) }
                    TaskButton { label: "Cancel"; onTriggered: board.reset() }
                    TaskButton { label: board.form === "delete" ? "Delete" : board.form === "transfer" ? "Move & delete" : "Move"
                        enabled: !board.busy && !board.orphan && (board.form === "delete" || (destination.currentIndex >= 0 && (!!board.destinationItem || !!board.input.trim())))
                        onTriggered: board.send(board.form, board.destinationItem ? {destination: board.destinationItem} : {newProject: board.input}) }
                }
                PlaceField { visible: board.form !== "delete" && destination.currentIndex === board.destinations.length
                    Layout.fillWidth: true; placeholderText: "New project name"; text: board.input; onTextEdited: board.input = text }
            }
            Loader {
                Layout.fillWidth: true; active: board.form === "deadline"; visible: active
                sourceComponent: TaskDatePicker {
                    today: board.today; due: board.dueBefore; busy: board.busy || board.orphan || board.zone !== board.tracking.zone
                    onSave: day => board.send("deadline", {date: day, expectedDue: board.dueBefore})
                    onRemove: board.send("clearDeadline", {expectedDue: board.dueBefore}); onCancel: board.reset()
                }
            }
            RowLayout {
                visible: board.form === "start" || board.form === "extend"; Layout.fillWidth: true
                PlaceField { id: duration; Layout.fillWidth: true; placeholderText: "37m, 1h 15m, or 14:40"; text: board.input
                    onTextEdited: board.input = text; onVisibleChanged: if (visible) forceActiveFocus()
                    onAccepted: if (go.enabled) go.triggered(Qt.LeftButton) }
                TaskButton { id: go; label: board.form === "extend" ? "Extend" : board.input.trim() ? "Start" : "Start untimed"
                    enabled: !board.busy && (board.form !== "extend" || !!board.input.trim())
                    onTriggered: board.send(board.form, {duration: board.input}) }
                TaskButton { label: "Cancel"; onTriggered: board.reset() }
            }
            Caption { Layout.fillWidth: true; visible: !!board.problem || board.orphan; wrapMode: Text.Wrap
                text: board.problem || "This item changed in the note. Your input is kept here."; color: Ink.lavender }
            RowLayout {
                visible: board.orphan && board.editingTitle
                Controls.ComboBox { id: replacement; Layout.fillWidth: true; model: board.items; textRole: "title" }
                TaskButton { label: "Use selected row"; enabled: replacement.currentIndex >= 0
                    onTriggered: {
                        const n = board.items[replacement.currentIndex]
                        board.target = n; board.reveal(n.key); board.problem = ""
                    } }
            }
            TaskButton { visible: !!board.problem && !!board.current && board.target?.key === board.current?.key
                    && (board.target?.rev !== board.current?.rev || board.target?.tree_rev !== board.current?.tree_rev)
                label: "Use current version"; onTriggered: { board.target = board.current; board.problem = "" } }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Ink.inactive; opacity: 0.55 }
            TaskButton {
                label: board.panelState.focusTodayLabel + "  ·  Focus history ›"; labelColor: Ink.lavender
                enabled: !board.busy; onTriggered: board.historyOpen = true
            }
        }
    }
    readonly property int descendants: {
        if (!target) return 0
        const start = items.findIndex(n => n.key === target.key)
        if (start < 0) return 0
        let i = start + 1
        while (i < items.length && items[i].depth > target.depth) ++i
        return i - start - 1
    }
}
