import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic as Controls
import Quickshell
import Quickshell.Hyprland
import Quickshell.Wayland
import "Palette.js" as Ink

PanelWindow {
    id: popup
    required property var hub
    required property bool centerMode
    readonly property var output: centerMode ? hub.centerScreen : hub.activeScreen
    SystemClock { id: clock; enabled: popup.centerMode && popup.visible; precision: SystemClock.Hours }
    function dayLabel(date) {
        const today = clock.date
        if (today.toDateString() === date.toDateString()) return "Today"
        const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1)
        if (yesterday.toDateString() === date.toDateString()) return "Yesterday"
        return Qt.formatDate(date, today.getFullYear() === date.getFullYear() ? "ddd, MMM d" : "MMM d, yyyy")
    }
    screen: output || hub.activeScreen
    visible: !!output && (centerMode || (!hub.centerScreen && hub.banners.length > 0))
    anchors { top: true; right: true }
    margins { top: hub.barVisible ? 56 : 10; right: 14 }
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: centerMode ? "dotfiles-notification-center" : "dotfiles-notification-banner"
    WlrLayershell.keyboardFocus: centerMode ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
    implicitWidth: Math.max(1, Math.min(416, (screen?.width || 450) - 28))
    implicitHeight: Math.max(1, Math.min((screen?.height || 500) - margins.top - 14,
        centerMode ? 510 : list.contentHeight + 2))
    color: "transparent"

    HyprlandFocusGrab {
        windows: [popup]
        active: popup.centerMode && popup.visible
        onCleared: if (popup.centerMode) popup.hub.centerScreen = null
    }
    Rectangle {
        anchors.fill: parent
        color: popup.centerMode ? Ink.panel : "transparent"
        radius: 13
        border.color: popup.centerMode ? Qt.alpha(Ink.lavender, 0.32) : "transparent"
        focus: popup.centerMode
        Keys.onEscapePressed: popup.hub.centerScreen = null
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: popup.centerMode ? 15 : 1
            spacing: popup.centerMode ? 10 : 0
            RowLayout {
                visible: popup.centerMode
                Layout.fillWidth: true
                Text { text: "Notifications"; color: Ink.text; font.family: "Inter"; font.pixelSize: 19; font.weight: Font.DemiBold; Layout.fillWidth: true }
                TaskButton { label: "Clear all"; enabled: popup.hub.history.length > 0; onTriggered: popup.hub.clearHistory() }
            }
            PanelSwitch {
                visible: popup.centerMode; Layout.fillWidth: true
                text: "Do Not Disturb"
                detail: popup.hub.focusing ? "Silenced during focus" : ""
                Accessible.description: popup.hub.focusing ? "Notifications are also silenced by focus" : ""
                checked: popup.hub.manual
                onToggled: if (checked !== popup.hub.manual) popup.hub.toggleManual()
            }
            ListView {
                id: list
                Layout.fillWidth: true; Layout.fillHeight: true
                clip: true; spacing: 7
                model: ScriptModel { values: popup.centerMode ? popup.hub.history : popup.hub.banners }
                delegate: Column {
                    required property var modelData
                    required property int index
                    width: list.width; spacing: 6
                    Text {
                        visible: popup.centerMode && !!modelData?.received && index >= 0 && (index === 0 ||
                            modelData.received.toDateString() !== popup.hub.history[index - 1]?.received.toDateString())
                        text: visible && modelData?.received ? popup.dayLabel(modelData.received) : ""
                        topPadding: index > 0 ? 5 : 0; leftPadding: 2
                        font.family: "Inter"; font.pixelSize: 12; font.weight: Font.DemiBold; color: Ink.muted
                    }
                    NotificationCard { width: list.width; entry: modelData; banner: !popup.centerMode }
                }
                Text {
                    anchors.centerIn: parent; visible: popup.centerMode && list.count === 0
                    text: "No notifications"; color: Ink.muted; font.family: "Inter"
                }
            }
        }
    }
}
