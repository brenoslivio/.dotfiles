import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Wayland
import "Palette.js" as Ink
import "PowerActions.js" as Power

PanelWindow {
    id: popup
    required property PanelWindow bar
    property int currentIndex: -1
    visible: false
    screen: bar.screen
    anchors { top: true; right: true }
    margins { top: bar.margins.top + bar.height + 4; right: bar.margins.right }
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    WlrLayershell.namespace: "dotfiles-power-menu"
    implicitWidth: strip.implicitWidth + 12
    implicitHeight: strip.implicitHeight + 12
    color: "transparent"
    onVisibleChanged: if (visible) currentIndex = -1
    HyprlandFocusGrab {
        windows: [popup, bar]
        active: popup.visible
        onCleared: popup.visible = false
    }

    function activate(index: int) {
        if (!visible || index < 0) return
        visible = false
        Quickshell.execDetached(Power.actions[index].command)
    }

    Rectangle {
        anchors.fill: parent
        color: Ink.panel; radius: 10; border.color: Qt.alpha(Ink.lavender, 0.6)
        focus: true
        Keys.onPressed: event => {
            const count = Power.actions.length
            if (event.key === Qt.Key_Escape) popup.visible = false
            else if (event.key === Qt.Key_Right) popup.currentIndex = (popup.currentIndex + 1) % count
            else if (event.key === Qt.Key_Left) popup.currentIndex = (popup.currentIndex < 0 ? count - 1 : (popup.currentIndex + count - 1) % count)
            else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) popup.activate(popup.currentIndex)
            else {
                const index = Power.actions.findIndex(action => action.key === event.text.toLowerCase())
                if (index < 0 || event.modifiers !== Qt.NoModifier) return
                popup.activate(index)
            }
            event.accepted = true
        }

        Row {
            id: strip
            anchors.centerIn: parent
            spacing: 2
            Repeater {
                model: Power.actions
                Row {
                    id: tile
                    required property int index
                    required property var modelData
                    spacing: 4
                    Rectangle {
                        visible: tile.index === 3
                        anchors.verticalCenter: parent.verticalCenter
                        width: 1; height: 32; color: Qt.alpha(Ink.lavender, 0.22)
                    }
                    Rectangle {
                        width: 70; height: 53; radius: 6
                        color: mouse.containsMouse || popup.currentIndex === tile.index ? Ink.selection : "transparent"
                        Accessible.role: Accessible.Button
                        Accessible.name: tile.modelData.label
                        Accessible.onPressAction: popup.activate(tile.index)
                        Column {
                            anchors.centerIn: parent
                            spacing: 3
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: tile.modelData.glyph; color: Ink.text
                                font.family: "FiraCode Nerd Font Mono"; font.pixelSize: 21
                            }
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: tile.modelData.label; color: Ink.text
                                font.family: "Inter"; font.pixelSize: 12
                            }
                        }
                        MouseArea {
                            id: mouse
                            anchors.fill: parent; hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: popup.activate(tile.index)
                        }
                    }
                }
            }
        }
    }
}
