import QtQuick
import QtQuick.Controls.Basic as Controls
import Quickshell
import "Palette.js" as Ink

PopupWindow {
    id: popup
    required property var clock
    required property var deadlines
    signal openTask(string block)
    property bool showPlaces: false
    property int monthOffset: 0
    property string selectedDay: ""
    readonly property date today: clock.date ? new Date(clock.date + "T12:00:00") : new Date()
    readonly property date displayed: new Date(today.getFullYear(), today.getMonth() + monthOffset, 1, 12)
    readonly property int year: displayed.getFullYear()
    readonly property int month: displayed.getMonth()
    readonly property int offset: (new Date(year, month, 1).getDay() + 6) % 7
    readonly property int days: new Date(year, month + 1, 0).getDate()
    readonly property var byDay: {
        const groups = {}
        for (const [block, due] of Object.entries(deadlines)) {
            if (!groups[due.date]) groups[due.date] = []
            groups[due.date].push({block: block, time: due.time, title: due.title})
        }
        for (const group of Object.values(groups))
            group.sort((a, b) => a.time.localeCompare(b.time) || a.title.localeCompare(b.title))
        return groups
    }
    readonly property int agendaRows: Object.values(byDay).reduce((rows, group) => Math.max(rows, Math.min(4, group.length)), 0)
    readonly property string agendaDay: {
        if (selectedDay) return selectedDay
        const prefix = Qt.formatDate(displayed, "yyyy-MM-")
        const first = monthOffset === 0 ? Qt.formatDate(today, "yyyy-MM-dd") : prefix + "01"
        const dates = Object.keys(byDay).filter(day => day.startsWith(prefix)).sort()
        return dates.find(day => day >= first) || dates[0] || first
    }
    function moveMonth(step) {
        selectedDay = ""
        monthOffset += step
    }

    onVisibleChanged: if (!visible) {
        picker.reset()
        weatherDetails.weekly = false
        selectedDay = ""
        monthOffset = 0
    }
    onShowPlacesChanged: if (showPlaces) weatherDetails.weekly = false

    anchor.edges: Edges.Bottom
    anchor.gravity: Edges.Bottom
    grabFocus: true
    color: "transparent"
    implicitWidth: showPlaces ? Math.min(560, (screen?.width || 576) - 16) : 228
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
            Row {
                TaskButton { label: "‹"; Accessible.name: "Previous month"; onTriggered: popup.moveMonth(-1) }
                Text {
                    width: calendar.width - 52; height: 29
                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                    text: Qt.formatDate(popup.displayed, "MMMM yyyy")
                    color: Ink.text; font.bold: true; font.family: "Inter"; font.pixelSize: 14
                }
                TaskButton { label: "›"; Accessible.name: "Next month"; onTriggered: popup.moveMonth(1) }
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
                    model: 42
                    Controls.AbstractButton {
                        id: cell
                        required property int index
                        readonly property int day: index - popup.offset + 1
                        readonly property string iso: enabled ? Qt.formatDate(new Date(popup.year, popup.month, day, 12), "yyyy-MM-dd") : ""
                        readonly property bool current: popup.monthOffset === 0 && day === popup.today.getDate()
                        readonly property int count: popup.byDay[iso]?.length || 0
                        enabled: day > 0 && day <= popup.days
                        width: 30; height: 25
                        Accessible.name: iso + (count ? ", " + count + " deadlines" : "")
                        onClicked: popup.selectedDay = iso
                        background: Rectangle {
                            radius: 6; color: cell.current ? Ink.lavender : "transparent"
                            border.color: cell.enabled && (cell.activeFocus || (popup.agendaRows && popup.agendaDay === cell.iso)) ? Ink.lavender : "transparent"
                        }
                        contentItem: Text {
                            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                            text: cell.enabled ? cell.day : ""
                            color: cell.current ? Ink.panel : Ink.text
                            font.family: "Inter"; font.pixelSize: 12; font.bold: cell.current
                        }
                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom
                            anchors.bottomMargin: 2; width: 5; height: 3; radius: 1.5
                            color: cell.current ? Ink.panel : Ink.lavender; visible: cell.count > 0
                        }
                    }
                }
            }
            Text {
                visible: popup.agendaRows > 0
                text: (popup.byDay[popup.agendaDay]?.length ? "Deadlines" : "No deadlines") + " · " + popup.agendaDay
                color: Ink.muted; font.family: "Inter"; font.pixelSize: 12
            }
            ListView {
                width: calendar.width; height: popup.agendaRows * 29
                visible: height > 0; clip: true
                model: popup.byDay[popup.agendaDay] || []
                Controls.ScrollBar.vertical: Controls.ScrollBar {}
                delegate: TaskButton {
                    required property var modelData
                    width: ListView.view.width
                    label: [modelData.time, modelData.title].filter(Boolean).join(" · ")
                    hint: label
                    onTriggered: popup.openTask(modelData.block)
                }
            }
            WeatherDetails {
                id: weatherDetails
                width: calendar.width
                clock: popup.clock
                onAddPlace: {
                    popup.showPlaces = true
                    picker.edit(null)
                }
            }
        }
    }
}
