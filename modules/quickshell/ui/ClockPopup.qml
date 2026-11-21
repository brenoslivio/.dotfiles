import QtQuick
import Quickshell
import "Palette.js" as Ink
import "Config.js" as Config

PopupWindow {
    id: popup
    required property var clock
    property bool showCities: false
    readonly property date today: new Date((clock.date || "2000-01-01") + "T12:00:00")
    readonly property int year: today.getFullYear()
    readonly property int month: today.getMonth()
    readonly property int offset: (new Date(year, month, 1).getDay() + 6) % 7
    readonly property int days: new Date(year, month + 1, 0).getDate()

    anchor.edges: Edges.Bottom
    anchor.gravity: Edges.Bottom
    grabFocus: true
    color: "transparent"
    implicitWidth: showCities ? 185 : 228
    implicitHeight: showCities ? cities.implicitHeight + 16 : calendar.implicitHeight + 16

    Rectangle {
        anchors.fill: parent
        color: Ink.panel; radius: 10; border.color: Ink.inactive
        focus: true
        Keys.onEscapePressed: popup.visible = false
        Column {
            id: cities
            anchors.centerIn: parent
            visible: popup.showCities
            Repeater {
                model: popup.clock.cities || []
                BarButton {
                    required property var modelData
                    width: popup.width - 16
                    label: (modelData.id === popup.clock.zone ? "✓  " : "") + modelData.name + "   " + modelData.time
                    onTriggered: {
                        Quickshell.execDetached(Config.commands.selectZone.concat(JSON.stringify(modelData.id)))
                        popup.visible = false
                    }
                }
            }
        }
        Column {
            id: calendar
            anchors.centerIn: parent
            visible: !popup.showCities
            spacing: 4
            Text {
                width: calendar.width
                horizontalAlignment: Text.AlignHCenter
                text: Qt.formatDate(popup.today, "MMMM yyyy")
                color: Ink.text; font.bold: true; font.family: "Inter"; font.pixelSize: 14
            }
            Row {
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
        }
    }
}
