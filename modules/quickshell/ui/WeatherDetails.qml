import QtQuick
import "Palette.js" as Ink

Column {
    id: card
    required property var clock
    readonly property var weather: clock.weather || ({})
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
    Detail {
        visible: !!card.clock.place
        text: card.weather.icon ? card.weather.icon + "  " + card.weather.temperature + "° · " + card.weather.description
            : card.clock.offline ? "Weather unavailable · retrying" : "Fetching weather…"
        color: Ink.text
    }
    Detail {
        visible: !!card.weather.icon
        text: visible ? "Feels like " + card.weather.feels + "°" : ""
    }
    Detail {
        visible: !!card.weather.icon && card.weather.day === card.clock.date
        text: visible ? "↑ " + card.weather.high + "°   ↓ " + card.weather.low + "°"
            + (card.weather.rain != null ? "   Rain " + card.weather.rain + "%" : "") : ""
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
