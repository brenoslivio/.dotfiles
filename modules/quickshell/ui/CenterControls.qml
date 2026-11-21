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
            slashed: mode.includes("dnd")
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
            label: center.state.clock.label || "…"
            buttons: Qt.LeftButton | Qt.RightButton
            hint: calendar.visible ? "" : center.state.clock.zone || ""
            onTriggered: button => {
                const cities = button === Qt.RightButton
                const close = calendar.visible && calendar.showCities === cities
                calendar.showCities = cities
                calendar.visible = !close
            }
            ClockPopup { id: calendar; anchor.item: clockButton; clock: center.state.clock }
        }
        BarButton {
            id: tasks
            iconSource: Config.commands.taskIcon; labelColor: Ink.lavender
            label: center.state.tasks.text || "0"
            hint: taskMenu.visible ? "" : center.state.tasks.tooltip || ""
            richHint: true
            buttons: Qt.LeftButton | Qt.RightButton
            onTriggered: button => {
                if (button === Qt.RightButton) taskMenu.toggle()
                else Quickshell.execDetached(Config.commands.obsidian)
            }
            ActionMenu { id: taskMenu; anchor.item: tasks; command: Config.commands.tasks }
        }
    }
}
