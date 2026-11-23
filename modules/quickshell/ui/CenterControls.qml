import QtQuick
import Quickshell
import "Config.js" as Config
import "Palette.js" as Ink

Rectangle {
    id: center
    required property var state
    color: Ink.field; radius: 8; height: 30; width: controls.implicitWidth + 10
    Row {
        id: controls
        anchors.centerIn: parent
        spacing: 2
        BarButton {
            iconSource: Config.commands.bellIcon
            readonly property string mode: center.state.notifications.alt || ""
            alert: mode.includes("notification")
            slashed: mode.includes("dnd") || mode.includes("inhibited")
            hint: (center.state.notifications.tooltip || "Notifications") + "\nLeft-click to open · Right-click for Do Not Disturb"
            buttons: Qt.LeftButton | Qt.RightButton
            onTriggered: button => Quickshell.execDetached(Config.commands.notifications.concat([button === Qt.RightButton ? "-d" : "-t", "-sw"]))
        }
        BarButton {
            id: updates
            readonly property var flags: center.state.updates["class"] || []
            property bool animateAutomatic: false
            Timer {
                interval: 500
                running: updates.flags.includes("checking")
                onTriggered: updates.animateAutomatic = true
            }
            onFlagsChanged: if (!flags.includes("checking")) animateAutomatic = false
            iconSource: Config.commands.updateIcon
            alert: flags.includes("attention")
            marked: flags.includes("pending")
            spinning: flags.includes("manual") || animateAutomatic
            hint: menu.visible ? "" : center.state.updates.tooltip || "Check for updates"
            buttons: Qt.LeftButton | Qt.RightButton
            onTriggered: button => {
                if (button === Qt.RightButton) menu.toggle()
                else Quickshell.execDetached(Config.commands.updates.concat("manual"))
            }
            ActionMenu { id: menu; anchor.item: updates; command: Config.commands.updates }
        }
        BarButton {
            id: clockButton
            readonly property var weather: center.state.clock.weather
            readonly property string utcOffset: center.state.clock.utcOffset || ""
            labelFormat: Text.StyledText
            label: (center.state.clock.label || "…").replace(/ /g, "&nbsp;")
                + (utcOffset ? " <font size='-1' color='" + Ink.inactive + "'>(" + utcOffset + ")</font>" : "")
                + (weather?.icon ? "&nbsp;&nbsp;&nbsp;" + weather.icon + "&nbsp;&nbsp;" + weather.temperature + "°" : "")
            buttons: Qt.LeftButton | Qt.RightButton
            hint: calendar.visible ? "" : [center.state.clock.place?.name, center.state.clock.zone].filter(Boolean).join("\n")
            onTriggered: button => {
                const places = button === Qt.RightButton
                const close = calendar.visible && calendar.showPlaces === places
                calendar.showPlaces = places
                calendar.visible = !close
            }
            ClockPopup {
                id: calendar
                anchor.item: clockButton
                clock: center.state.clock
                deadlines: center.state.tracking.deadlines || ({})
                onOpenTask: block => {
                    calendar.visible = false
                    center.state.taskBoard.openAt(tasks, block)
                }
            }
        }
        BarButton {
            id: tasks
            iconSource: Config.commands.taskIcon; labelColor: Ink.lavender
            readonly property var session: center.state.tracking.active
            readonly property var urgency: center.state.tracking.urgency
            label: !session ? center.state.tasks.text || "0" : session.status === "paused" ? "Paused"
                : session.status === "expired" ? "Time’s up" : "Focusing..."
            alert: urgency?.level === "urgent"
            marked: urgency?.level === "soon"
            markColor: "#efb65c"
            hint: center.state.taskBoard.visible ? "" : urgency?.text || center.state.tasks.tooltip || ""
            richHint: !urgency?.text
            buttons: Qt.LeftButton | Qt.RightButton
            onTriggered: button => {
                if (button === Qt.LeftButton) center.state.taskBoard.openAt(tasks, "")
                else Quickshell.execDetached(Config.commands.obsidian)
            }
        }
    }
}
