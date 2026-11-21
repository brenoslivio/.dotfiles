import QtQuick
import QtQuick.Controls.Basic as Controls
import Quickshell.Io
import "Palette.js" as Ink
import "Config.js" as Config

Column {
    id: search
    signal back()
    signal picked(var match)
    property var results: []
    property string message: ""
    spacing: 4

    function submit() {
        const text = query.text.trim()
        if (!text || lookup.running) return
        results = []
        message = ""
        lookup.command = Config.commands.streetSearch.concat([text])
        lookup.running = true
    }

    Component.onCompleted: query.forceActiveFocus()
    Keys.onEscapePressed: search.back()
    Process {
        id: lookup
        stdout: StdioCollector {
            onStreamFinished: {
                if (query.text.trim() !== lookup.command[lookup.command.length - 1]) return
                try {
                    const response = JSON.parse(text)
                    search.results = response.results || []
                    search.message = response.error || (search.results.length ? "" : "No matches. Try adding a city or house number.")
                } catch (e) {
                    search.message = "Couldn’t read search results. Try again."
                }
            }
        }
    }
    PlaceField {
        id: query
        width: parent.width
        placeholderText: "Street and city"; Accessible.name: placeholderText
        onAccepted: search.submit()
        onTextEdited: { search.results = []; search.message = "" }
    }
    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        BarButton {
            label: lookup.running ? "Searching…" : "Search"
            enabled: !!query.text.trim() && !lookup.running
            opacity: enabled ? 1 : 0.6
            onTriggered: search.submit()
        }
        BarButton { label: "Back"; onTriggered: search.back() }
    }
    Text {
        visible: !!text; width: parent.width
        text: search.message; textFormat: Text.PlainText; wrapMode: Text.Wrap
        color: Ink.muted; font.family: "Inter"; font.pixelSize: 12
    }
    Repeater {
        model: search.results
        delegate: Controls.ItemDelegate {
            id: row
            required property var modelData
            width: search.width
            padding: 6; hoverEnabled: true
            Accessible.name: [modelData.title, modelData.area, modelData.approximate ? "Approximate" : ""].filter(Boolean).join(", ")
            background: Rectangle {
                radius: 6; color: row.hovered || row.visualFocus ? Ink.selection : "transparent"
            }
            contentItem: Column {
                spacing: 2
                Text {
                    width: parent.width
                    text: row.modelData.title + (row.modelData.approximate ? "  ·  approximate" : "")
                    color: Ink.text; font.family: "Inter"; font.pixelSize: 13
                    textFormat: Text.PlainText; wrapMode: Text.Wrap
                }
                Text {
                    width: parent.width; visible: !!text
                    text: row.modelData.area; textFormat: Text.PlainText; wrapMode: Text.Wrap
                    color: Ink.muted; font.family: "Inter"; font.pixelSize: 11
                }
            }
            HoverHandler { cursorShape: Qt.PointingHandCursor }
            onClicked: search.picked(modelData)
        }
    }
    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        text: "Photon · © OpenStreetMap contributors"; color: Ink.muted
        font.family: "Inter"; font.pixelSize: 10
        TapHandler { onTapped: Qt.openUrlExternally("https://www.openstreetmap.org/copyright") }
        HoverHandler { cursorShape: Qt.PointingHandCursor }
    }
}
