import QtQuick
import QtQuick.Controls.Basic as Controls
import "Palette.js" as Ink

Controls.Switch {
    id: control
    property string detail: ""
    padding: 10
    rightPadding: indicator.width + 18
    background: Rectangle {
        radius: 8
        color: control.hovered ? Ink.selection : Ink.field
        border.color: control.visualFocus ? Ink.lavender : "transparent"
    }
    contentItem: Column {
        spacing: 2
        Text { text: control.text; font.family: "Inter"; font.pixelSize: 13; color: Ink.text }
        Text { visible: !!control.detail; text: control.detail; font.pixelSize: 11; color: Ink.muted }
    }
    indicator: Rectangle {
        x: control.width - width - 10; y: (control.height - height) / 2
        implicitWidth: 36; implicitHeight: 20
        radius: height / 2
        color: control.checked ? Ink.lavender : Ink.panel
        border.color: control.checked ? Ink.lavender : Ink.inactive
        Rectangle {
            width: 14; height: width; radius: width / 2
            x: control.checked ? parent.width - width - 3 : 3
            anchors.verticalCenter: parent.verticalCenter
            color: control.checked ? Ink.panel : Ink.muted
            Behavior on x { NumberAnimation { duration: 110 } }
        }
    }
}
