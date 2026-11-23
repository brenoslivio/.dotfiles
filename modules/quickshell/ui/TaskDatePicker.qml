import QtQuick
import QtQuick.Layouts
import "Palette.js" as Ink

ColumnLayout {
    id: picker
    required property string today
    required property var due
    required property bool busy
    signal save(string day)
    signal remove()
    signal cancel()
    property date month: new Date()
    property string selected: ""
    readonly property date baseDate: today ? new Date(today + "T12:00:00") : new Date()
    enabled: !busy
    function choose(day) {
        save(Qt.formatDate(day, "yyyy-MM-dd"))
    }
    function display(day) {
        selected = Qt.formatDate(day, "yyyy-MM-dd")
        month = new Date(day.getFullYear(), day.getMonth(), 1, 12)
    }
    Component.onCompleted: {
        display(due?.date ? new Date(due.date + "T12:00:00") : baseDate)
    }
    spacing: 3
    RowLayout {
        Layout.fillWidth: true
        TaskButton { label: "‹"; Accessible.name: "Previous month"; onTriggered: picker.month = new Date(picker.month.getFullYear(), picker.month.getMonth()-1, 1, 12) }
        Text { text: Qt.formatDate(picker.month, "MMMM yyyy"); color: Ink.text; font.bold: true; Layout.fillWidth: true }
        TaskButton { label: "›"; Accessible.name: "Next month"; onTriggered: picker.month = new Date(picker.month.getFullYear(), picker.month.getMonth()+1, 1, 12) }
        TaskButton { label: "Today"; onTriggered: picker.choose(picker.baseDate) }
        TaskButton { label: "Tomorrow"; onTriggered: {
            const d = new Date(picker.baseDate); d.setDate(d.getDate()+1); picker.choose(d)
        } }
    }
    GridLayout {
        columns: 7; columnSpacing: 2; rowSpacing: 0
        Layout.alignment: Qt.AlignHCenter
        Repeater {
            model: ["Mo","Tu","We","Th","Fr","Sa","Su"]
            Text { required property string modelData; Layout.preferredWidth: 34; text: modelData; horizontalAlignment: Text.AlignHCenter; color: Ink.muted; font.pixelSize: 11 }
        }
        Repeater {
            model: 42
            TaskButton {
                required property int index
                readonly property int day: index + 1 - (picker.month.getDay() + 6) % 7
                readonly property date value: new Date(picker.month.getFullYear(), picker.month.getMonth(), day, 12)
                enabled: value.getMonth() === picker.month.getMonth()
                label: enabled ? String(day) : ""; Accessible.name: Qt.formatDate(value, "yyyy-MM-dd")
                Layout.preferredWidth: 34; Layout.preferredHeight: 23
                selected: enabled && picker.selected === Qt.formatDate(value, "yyyy-MM-dd")
                onTriggered: picker.choose(value)
            }
        }
    }
    RowLayout {
        Item { Layout.fillWidth: true }
        TaskButton { label: "Clear"; visible: !!picker.due; enabled: !picker.busy; onTriggered: picker.remove() }
        TaskButton { label: "Cancel"; onTriggered: picker.cancel() }
    }
}
