import QtQuick
import Quickshell
import "Palette.js" as Ink

PopupWindow {
    id: popup
    required property var clock
    required property var player
    required property string trackTitle
    property bool showPlaces: false
    readonly property date today: new Date((clock.date || "2000-01-01") + "T12:00:00")
    readonly property int year: today.getFullYear()
    readonly property int month: today.getMonth()
    readonly property int offset: (new Date(year, month, 1).getDay() + 6) % 7
    readonly property int days: new Date(year, month + 1, 0).getDate()

    onVisibleChanged: if (!visible) picker.reset()

    anchor.edges: Edges.Bottom
    anchor.gravity: Edges.Bottom
    grabFocus: true
    color: "transparent"
    implicitWidth: showPlaces ? (picker.page === "search" ? 340 : 270) : 228
    implicitHeight: showPlaces ? picker.implicitHeight + 16 : calendar.implicitHeight + 16

    Rectangle {
        anchors.fill: parent
        color: Ink.panel; radius: 10; border.color: Ink.inactive
        focus: true
        Keys.onEscapePressed: popup.visible = false
        PlacePicker {
            id: picker
            anchors.centerIn: parent
            width: popup.width - 16
            visible: popup.showPlaces
            clock: popup.clock
            onChosen: popup.visible = false
        }
        Column {
            id: calendar
            anchors.centerIn: parent
            width: 210
            visible: !popup.showPlaces
            spacing: 4
            Text {
                width: calendar.width
                horizontalAlignment: Text.AlignHCenter
                visible: !!popup.clock.date
                text: Qt.formatDate(popup.today, "MMMM yyyy")
                color: Ink.text; font.bold: true; font.family: "Inter"; font.pixelSize: 14
            }
            Row {
                visible: !!popup.clock.date
                Repeater {
                    model: ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
                    Text {
                        required property string modelData
                        width: 30; height: 20
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        text: modelData; color: Ink.muted; font.pixelSize: 11
                    }
                }
            }
            Grid {
                visible: !!popup.clock.date
                columns: 7
                Repeater {
                    model: popup.offset + popup.days
                    Rectangle {
                        required property int index
                        readonly property int day: index - popup.offset + 1
                        readonly property bool current: day === popup.today.getDate()
                        width: 30; height: 23; radius: 6
                        color: current ? Ink.lavender : "transparent"
                        Text {
                            anchors.centerIn: parent
                            text: parent.day > 0 ? parent.day : ""
                            color: parent.current ? Ink.panel : Ink.text
                            font.family: "Inter"; font.pixelSize: 12; font.bold: parent.current
                        }
                    }
                }
            }
            WeatherDetails {
                width: calendar.width
                clock: popup.clock
                onAddPlace: {
                    popup.showPlaces = true
                    picker.edit(null)
                }
            }
            Column {
                visible: !!popup.player
                width: calendar.width
                spacing: 4
                Rectangle { width: parent.width; height: 1; color: Qt.alpha(Ink.lavender, 0.28) }
                Text {
                    width: parent.width; topPadding: 4
                    text: popup.trackTitle; textFormat: Text.PlainText
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight
                    color: Ink.text; font.family: "Inter"; font.pixelSize: 13; font.bold: true
                }
                Text {
                    width: parent.width; visible: !!text
                    text: popup.player?.trackArtist || ""; textFormat: Text.PlainText
                    horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                    color: Ink.muted; font.family: "Inter"; font.pixelSize: 12
                }
                Row {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 5
                    TransportButton {
                        label: "󰒮"; hint: "Previous"
                        enabled: !!popup.player?.canGoPrevious
                        onTriggered: popup.player.previous()
                    }
                    TransportButton {
                        label: popup.player?.isPlaying ? "󰏤" : "󰐊"
                        hint: popup.player?.isPlaying ? "Pause" : "Play"
                        labelColor: Ink.lavender
                        enabled: !!popup.player?.canTogglePlaying
                        onTriggered: popup.player.togglePlaying()
                    }
                    TransportButton {
                        label: "󰒭"; hint: "Next"
                        enabled: !!popup.player?.canGoNext
                        onTriggered: popup.player.next()
                    }
                }
            }
        }
    }

    component TransportButton: BarButton {
        minimumWidth: 34; glyph: true
        opacity: enabled ? 1 : 0.38
        activeFocusOnTab: enabled
        highlight: true
        border.color: activeFocus ? Ink.lavender : "transparent"
        Accessible.role: Accessible.Button
        Accessible.name: hint
        Accessible.onPressAction: if (enabled) triggered(Qt.LeftButton)
        Keys.onSpacePressed: triggered(Qt.LeftButton)
        Keys.onReturnPressed: triggered(Qt.LeftButton)
    }
}
