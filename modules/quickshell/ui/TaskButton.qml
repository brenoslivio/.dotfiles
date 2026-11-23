import QtQuick
import "Palette.js" as Ink

BarButton {
    activeFocusOnTab: enabled && visible
    opacity: enabled ? 1 : 0.5
    border.color: activeFocus ? Ink.lavender : "transparent"
    Accessible.role: Accessible.Button; Accessible.name: label
    Accessible.onPressAction: triggered(Qt.LeftButton)
    Keys.onReturnPressed: triggered(Qt.LeftButton)
    Keys.onSpacePressed: triggered(Qt.LeftButton)
}
