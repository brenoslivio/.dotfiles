import QtQuick
import QtQuick.Controls.Basic as Controls
import "Palette.js" as Ink

Column {
    id: week
    required property var forecast
    required property string today
    property var days: []
    readonly property int temperatureWidth: 34
    readonly property int precipitationWidth: 49
    // Preserve the hovered row while the clock updates every second.
    onForecastChanged: if (JSON.stringify(forecast) !== JSON.stringify(days)) days = forecast
    spacing: 1

    component Cell: Text {
        height: parent.height
        verticalAlignment: Text.AlignVCenter; horizontalAlignment: Text.AlignRight
        color: Ink.text; font.family: "Inter"; font.pixelSize: 12
    }
    component Heading: Cell {
        color: Ink.muted; font.pixelSize: 10
    }
    Row {
        anchors.right: parent.right; anchors.rightMargin: 5; height: 16
        Heading { width: week.temperatureWidth; text: "High" }
        Heading { width: week.temperatureWidth; text: "Low" }
        Heading { width: week.precipitationWidth; text: "Precip." }
    }
    Repeater {
        model: week.days
        Rectangle {
            id: row
            required property var modelData
            readonly property bool current: modelData.date === week.today
            readonly property date localDate: new Date(modelData.date + "T12:00:00")
            width: week.width; height: 22; radius: 5
            color: current ? Qt.alpha(Ink.lavender, 0.12) : "transparent"
            Row {
                anchors.fill: parent; anchors.rightMargin: 5
                Cell {
                    width: parent.width - icon.width - 2 * week.temperatureWidth - week.precipitationWidth; leftPadding: 5
                    horizontalAlignment: Text.AlignLeft
                    text: row.current ? "Today " + row.localDate.getDate() : Qt.formatDate(row.localDate, "ddd d")
                    color: row.current ? Ink.lavender : Ink.text
                }
                Cell {
                    id: icon
                    width: 24; horizontalAlignment: Text.AlignHCenter
                    text: row.modelData.icon; font.family: "FiraCode Nerd Font Mono"; font.pixelSize: 16
                    Accessible.name: row.modelData.description
                    HoverHandler { id: hover }
                    Controls.ToolTip {
                        visible: hover.hovered && week.visible
                        delay: 300; padding: 6
                        text: row.modelData.description
                        contentItem: Text { text: row.modelData.description; color: Ink.text; font.family: "Inter"; font.pixelSize: 12 }
                        background: Rectangle { color: Ink.field; border.color: Ink.inactive; radius: 5 }
                    }
                }
                Cell { width: week.temperatureWidth; text: row.modelData.high != null ? row.modelData.high + "°" : "—" }
                Cell { width: week.temperatureWidth; text: row.modelData.low != null ? row.modelData.low + "°" : "—"; color: Ink.muted }
                Cell { width: week.precipitationWidth; text: row.modelData.rain != null ? row.modelData.rain + "%" : "—"; color: Ink.muted }
            }
        }
    }
}
