import QtQuick
import QtQuick.Controls.Basic as Controls
import "Palette.js" as Ink

Controls.TextField {
    color: Ink.text; placeholderTextColor: Ink.muted
    font.family: "Inter"; font.pixelSize: 13; selectByMouse: true
    leftPadding: 8; rightPadding: 8
    background: Rectangle {
        implicitHeight: 32; color: Ink.field; radius: 5
        border.color: parent.activeFocus ? Ink.lavender : Ink.inactive
    }
}
