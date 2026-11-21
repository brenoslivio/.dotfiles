import QtQuick
import Quickshell
import "Palette.js" as Ink

Rectangle {
    id: button
    property string label
    property alias labelFormat: caption.textFormat
    property string subtitle
    property string hint
    property bool richHint: false
    property string iconSource
    property int iconSize: 18
    property bool selected: false
    property bool marked: false
    property bool alert: false
    property bool slashed: false
    property bool spinning: false
    property bool glyph: false
    property string glyphFamily: "FiraCode Nerd Font Mono"
    property bool italic: false
    property bool highlight: true
    property int padding: 6
    property int minimumWidth: 26
    property color labelColor: Ink.muted
    property int buttons: Qt.LeftButton
    signal triggered(int button)
    signal scrolled(int delta)
    implicitWidth: Math.max(minimumWidth, caption.implicitWidth + (iconSource ? iconSize + (label ? 3 : 0) : 0) + 2 * padding)
    width: implicitWidth
    height: 29
    radius: 7
    color: selected || (highlight && pointer.containsMouse) ? Ink.selection : "transparent"

    Row {
        anchors.centerIn: parent
        anchors.verticalCenterOffset: button.subtitle ? -6 : 0
        spacing: iconSource && label ? 3 : 0
        Image {
            id: icon
            anchors.verticalCenter: parent.verticalCenter
            width: button.iconSize; height: width
            sourceSize.width: width; sourceSize.height: height
            source: button.iconSource; visible: !!source.toString()
            RotationAnimation on rotation {
                from: 0; to: 360; duration: 1000; loops: Animation.Infinite
                running: button.spinning
                onRunningChanged: if (!running) icon.rotation = 0
            }
        }
        Text {
            id: caption
            anchors.verticalCenter: parent.verticalCenter
            visible: !!button.label
            text: button.label; textFormat: Text.PlainText
            width: Math.max(0, Math.min(implicitWidth, button.width - 2 * button.padding - (icon.visible ? icon.width + 3 : 0)))
            elide: Text.ElideRight
            color: button.selected || (button.highlight && pointer.containsMouse) ? Ink.text : button.labelColor
            font.family: button.glyph ? button.glyphFamily : "Inter"
            font.pixelSize: button.glyph ? 19 : 13
            font.italic: button.italic
        }
    }
    Text {
        visible: !!button.subtitle
        anchors { bottom: parent.bottom; horizontalCenter: parent.horizontalCenter }
        width: Math.max(0, button.width - 2 * button.padding)
        text: button.subtitle; textFormat: Text.PlainText
        horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
        color: Ink.lavender; font.family: "Inter"; font.pixelSize: 11
    }
    Rectangle {
        anchors.centerIn: parent
        width: button.iconSize; height: 1.5
        rotation: -45; color: Ink.lavender; visible: button.slashed
    }
    Rectangle {
        anchors { right: parent.right; top: parent.top; rightMargin: 2; topMargin: 2 }
        width: button.alert ? 6 : 4; height: width; radius: width / 2
        color: button.alert ? "#ff6675" : Ink.lavender
        visible: button.marked || button.alert
    }
    Rectangle {
        anchors { bottom: parent.bottom; horizontalCenter: parent.horizontalCenter }
        width: 16; height: 2; radius: 1; color: Ink.magenta; visible: button.selected
    }
    MouseArea {
        id: pointer
        anchors.fill: parent; hoverEnabled: true; acceptedButtons: button.buttons
        cursorShape: button.buttons ? Qt.PointingHandCursor : Qt.ArrowCursor
        onExited: tip.visible = false
        onPressed: tip.visible = false
        onClicked: mouse => button.triggered(mouse.button)
        onWheel: event => { if (event.angleDelta.y) button.scrolled(event.angleDelta.y) }
    }
    Timer {
        interval: 650
        running: pointer.containsMouse && !pointer.pressed && button.hint !== ""
        onTriggered: tip.visible = true
    }
    PopupWindow {
        id: tip
        anchor.item: button; anchor.edges: Edges.Bottom; anchor.gravity: Edges.Bottom
        implicitWidth: Math.min(530, tipText.implicitWidth + 22)
        implicitHeight: Math.min(540, tipText.contentHeight + 16)
        color: "transparent"
        Rectangle {
            anchors.fill: parent; radius: 7; color: Ink.panel; border.color: Ink.inactive
            clip: true
            Text {
                id: tipText
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 9 }
                text: button.richHint ? button.hint.replace(/\n/g, "<br>") : button.hint
                textFormat: button.richHint ? Text.StyledText : Text.PlainText
                wrapMode: Text.Wrap; font.family: "Inter"; font.pixelSize: 12; color: Ink.text
            }
        }
    }
}
