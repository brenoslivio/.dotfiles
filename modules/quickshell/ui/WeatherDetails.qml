import QtQuick
import "Palette.js" as Ink

Column {
    id: card
    required property var clock
    readonly property var weather: clock.weather || ({})
    property bool weekly: false
    signal addPlace()
    spacing: 4
    Rectangle { width: parent.width; height: 1; color: Qt.alpha(Ink.lavender, 0.28) }
    Text {
        width: parent.width; topPadding: 4
        visible: !!card.clock.place
        text: card.clock.place?.name || ""; textFormat: Text.PlainText
        horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
        color: Ink.lavender; font.family: "Inter"; font.pixelSize: 13; font.bold: true
    }
    component Detail: Text {
        width: card.width; textFormat: Text.PlainText; wrapMode: Text.Wrap
        horizontalAlignment: Text.AlignHCenter
        color: Ink.muted; font.family: "Inter"; font.pixelSize: 12
    }
    Row {
        visible: !!card.clock.place
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 3
        Repeater {
            model: ["Today", "7 days"]
            BarButton {
                required property string modelData
                required property int index
                label: modelData; selected: card.weekly === (index === 1)
                height: 24; minimumWidth: 52
                activeFocusOnTab: true
                border.color: activeFocus ? Ink.lavender : "transparent"
                Accessible.role: Accessible.RadioButton
                Accessible.name: label; Accessible.checked: selected
                Accessible.onPressAction: triggered(Qt.LeftButton)
                Keys.onSpacePressed: triggered(Qt.LeftButton)
                Keys.onReturnPressed: triggered(Qt.LeftButton)
                onTriggered: card.weekly = index === 1
            }
        }
    }
    Detail {
        visible: !!card.clock.place && !card.weekly
        text: card.weather.icon ? card.weather.icon + "  " + card.weather.temperature + "° · " + card.weather.description
            : card.clock.offline ? "Weather unavailable · retrying" : "Fetching weather…"
        color: Ink.text
    }
    Detail {
        visible: !!card.weather.icon && !card.weekly
        text: visible ? "Feels like " + card.weather.feels + "°" : ""
    }
    Detail {
        visible: !!text && !card.weekly && card.weather.day === card.clock.date
        text: [card.weather.high != null ? "↑ " + card.weather.high + "°" : "",
               card.weather.low != null ? "↓ " + card.weather.low + "°" : "",
               card.weather.rain != null ? "Rain " + card.weather.rain + "%" : ""].filter(Boolean).join("   ")
    }
    WeeklyForecast {
        width: card.width
        visible: card.weekly && days.length > 0
        forecast: card.clock.week || []
        today: card.clock.date || ""
    }
    Detail {
        visible: card.weekly && !card.clock.week?.length
        text: card.clock.offline ? "Weekly forecast unavailable · retrying" : "Fetching weekly forecast…"
    }
    Detail {
        visible: !!card.weather.icon
        font.pixelSize: 10
        text: (card.clock.offline ? "Offline · " : "") + (card.clock.updated || "") + " · Open-Meteo"
        TapHandler { onTapped: Qt.openUrlExternally("https://open-meteo.com/") }
        HoverHandler { cursorShape: Qt.PointingHandCursor }
    }
    BarButton {
        visible: !card.clock.place
        anchors.horizontalCenter: parent.horizontalCenter
        label: "Add weather location…"
        onTriggered: card.addPlace()
    }
}
