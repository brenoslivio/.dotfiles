import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic as Controls
import QtQuick.Controls.impl as Style
import "Palette.js" as Ink

Rectangle {
    id: card
    required property var entry
    required property bool banner
    readonly property bool compact: banner && entry.isTransient
        && ["volume_notif", "mic-mute"].includes(entry.notice?.hints["x-canonical-private-synchronous"])
    readonly property color accent: entry.criticalBattery ? "#ff8290" : Ink.lavender
    readonly property int inset: compact ? 10 : 12
    readonly property var secondary: entry.actions.filter(a => a !== entry.openAction)
    implicitHeight: row.implicitHeight + 2 * inset
    radius: banner ? 12 : 9
    color: entry.canOpen && hover.hovered ? Ink.selection : banner ? Ink.panel : Ink.field
    border.color: activeFocus ? accent : banner ? Qt.alpha(accent, hover.hovered ? 0.62 : 0.30) : "transparent"
    activeFocusOnTab: entry.canOpen
    Accessible.role: entry.canOpen ? Accessible.Button : Accessible.Grouping
    Accessible.name: entry.title
    Accessible.description: entry.openAction ? "Open notification" : entry.desktopApp ? "Open " + entry.app : ""
    Accessible.onPressAction: entry.open()
    Keys.onReturnPressed: entry.open()
    Keys.onSpacePressed: entry.open()
    transform: Translate { id: offset }
    Component.onCompleted: if (banner) appear.start()
    ParallelAnimation {
        id: appear
        NumberAnimation { target: card; property: "opacity"; from: 0; to: 1; duration: 130 }
        NumberAnimation { target: offset; property: "x"; from: 7; to: 0; duration: 130; easing.type: Easing.OutCubic }
    }

    HoverHandler { id: hover }
    MouseArea {
        anchors.fill: parent
        enabled: card.entry.canOpen; hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: card.entry.open()
    }
    Rectangle {
        visible: card.entry.criticalBattery
        anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: 12; bottomMargin: 12 }
        width: 3; radius: 2; color: card.accent
    }

    component SenderIcon: Rectangle {
        required property int size
        implicitWidth: size; implicitHeight: size
        radius: Math.round(size / 3)
        color: Qt.alpha(card.accent, 0.12)
        Style.IconImage {
            id: image
            anchors.centerIn: parent
            width: Math.round(parent.size * 0.72); height: width
            source: card.entry.icon
            color: card.entry.icon.endsWith("-symbolic.svg") ? card.accent : "transparent"
            sourceSize.width: width; sourceSize.height: height
            fillMode: Image.PreserveAspectFit
        }
        Text {
            anchors.centerIn: parent
            visible: image.status !== Image.Ready
            text: card.entry.app.charAt(0).toUpperCase()
            color: card.accent; font.family: "Inter"; font.weight: Font.DemiBold
            font.pixelSize: Math.round(parent.size * 0.5)
        }
    }

    RowLayout {
        id: row
        anchors { top: parent.top; left: parent.left; right: parent.right; margins: card.inset }
        spacing: 10
        SenderIcon {
            size: 34
            visible: card.banner && !card.compact
            Layout.alignment: Qt.AlignTop
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: card.compact ? 0 : 4
            RowLayout {
                Layout.fillWidth: true
                spacing: 7
                SenderIcon { size: 22; visible: !card.banner }
                Text {
                    Layout.fillWidth: true
                    text: card.compact ? card.entry.title : card.entry.app + (card.entry.website ? " · " + card.entry.website : "")
                    textFormat: Text.PlainText; elide: Text.ElideRight
                    color: card.compact ? Ink.text : card.accent
                    font.family: "Inter"; font.pixelSize: card.compact ? 13 : 12; font.weight: Font.Medium
                }
                Item {
                    Layout.preferredWidth: Math.max(time.implicitWidth, dismiss.width)
                    Layout.preferredHeight: card.compact ? 20 : 24
                    Text {
                        id: time
                        anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                        visible: !card.compact && dismiss.opacity === 0
                        text: Qt.formatTime(card.entry.received, "HH:mm")
                        color: Ink.inactive; font.family: "Inter"; font.pixelSize: 11
                    }
                    TaskButton {
                        id: dismiss
                        anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                        height: 24; width: 24
                        label: "×"; Accessible.name: "Dismiss notification"
                        opacity: hover.hovered || card.activeFocus || activeFocus || hovered ? 1 : 0
                        onTriggered: card.entry.dismiss()
                    }
                }
            }
            Text {
                Layout.fillWidth: true; visible: !!text && !card.compact
                text: card.entry.title; textFormat: Text.PlainText
                wrapMode: Text.Wrap; elide: Text.ElideRight
                maximumLineCount: card.banner ? 2 : 2147483647
                color: Ink.text; font.family: "Inter"; font.weight: Font.DemiBold; font.pixelSize: card.banner ? 16 : 14
            }
            Text {
                Layout.fillWidth: true; visible: !!text && !card.compact
                text: card.entry.body; textFormat: Text.PlainText
                wrapMode: Text.Wrap; elide: Text.ElideRight
                maximumLineCount: card.banner ? 2 : 2147483647
                color: Ink.muted; font.family: "Inter"; font.pixelSize: 13
            }
            Flow {
                id: buttons
                Layout.fillWidth: true; Layout.topMargin: 4; spacing: 6
                visible: card.secondary.length > 0
                Repeater {
                    model: card.secondary
                    Controls.Button {
                        id: action
                        required property var modelData
                        readonly property bool primary: card.entry.app === "Desktop panel" && modelData.identifier === "extend"
                        text: modelData.text || modelData.identifier
                        width: Math.min(implicitWidth, buttons.width)
                        horizontalPadding: 11; verticalPadding: 5
                        onClicked: modelData.invoke()
                        background: Rectangle {
                            radius: 6
                            color: action.primary ? Ink.lavender : action.hovered || action.visualFocus ? Ink.selection : Qt.alpha(Ink.lavender, 0.10)
                            border.color: action.visualFocus ? Ink.text : "transparent"
                        }
                        contentItem: Text {
                            text: action.text; textFormat: Text.PlainText; elide: Text.ElideRight
                            horizontalAlignment: Text.AlignHCenter
                            font.family: "Inter"; font.pixelSize: 12; font.weight: Font.Medium
                            color: action.primary ? Ink.panel : Ink.text
                        }
                    }
                }
            }
        }
    }
}
