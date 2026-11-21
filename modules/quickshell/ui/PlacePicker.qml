import QtQuick
import QtQuick.Controls.Basic as Controls
import Quickshell.Io
import "Palette.js" as Ink
import "Config.js" as Config

Column {
    id: picker
    required property var clock
    signal chosen()
    property string page: "list"
    property var original: null
    property string error: ""
    property var places: []
    // Keep delegates and scroll position stable between clock ticks.
    onClockChanged: {
        const rows = clock.places || []
        if (JSON.stringify(places) !== JSON.stringify(rows)) places = rows
    }
    spacing: 4

    function reset() {
        page = "list"
        error = ""
        original = null
    }
    function edit(place) {
        original = place ? {id: place.id, name: place.name, latitude: place.latitude, longitude: place.longitude} : null
        nameField.text = place?.name || ""
        coordinateField.text = place ? place.latitude + ", " + place.longitude : ""
        error = ""
        page = "edit"
        nameField.forceActiveFocus()
    }
    function submit(action, payload) {
        if (writer.running) return
        error = ""
        writer.command = Config.commands.clock.concat([action, JSON.stringify(payload)])
        writer.running = true
    }
    function save() {
        submit(original ? "edit" : "add", {id: original?.id, original: original,
               name: nameField.text, coordinates: coordinateField.text})
    }

    Process {
        id: writer
        stdout: StdioCollector {
            onStreamFinished: {
                if (text.trim()) picker.error = text.trim()
                else if (writer.command[writer.command.length - 2] === "select") picker.chosen()
                else picker.reset()
            }
        }
    }
    Text {
        width: parent.width; horizontalAlignment: Text.AlignHCenter
        text: picker.page === "edit" ? (picker.original ? "Edit place" : "Add place")
            : picker.page === "remove" ? "Remove place?" : "Saved places"
        color: Ink.lavender; font.family: "Inter"; font.pixelSize: 13; font.bold: true
    }
    ListView {
        id: list
        visible: picker.page === "list" || picker.page === "manage"
        width: parent.width; height: Math.min(picker.places.length * 30, 210)
        clip: true; model: picker.places; boundsBehavior: Flickable.StopAtBounds
        Controls.ScrollBar.vertical: Controls.ScrollBar {}
        delegate: BarButton {
            required property var modelData
            width: list.width
            label: picker.page === "manage" ? "✎  " + modelData.name
                : (picker.clock.place?.id === modelData.id ? "✓  " : "") + modelData.name + "   " + modelData.time
            onTriggered: {
                if (picker.page === "manage") picker.edit(modelData)
                else picker.submit("select", {id: modelData.id})
            }
        }
    }
    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        visible: list.visible
        BarButton { label: "Add place…"; onTriggered: picker.edit(null) }
        BarButton {
            visible: picker.places.length > 0
            label: picker.page === "manage" ? "Done" : "Manage places…"
            onTriggered: picker.page = picker.page === "manage" ? "list" : "manage"
        }
    }
    component Field: Controls.TextField {
        width: picker.width; color: Ink.text; placeholderTextColor: Ink.muted
        font.family: "Inter"; font.pixelSize: 13; selectByMouse: true
        leftPadding: 8; rightPadding: 8
        background: Rectangle {
            implicitHeight: 32; color: Ink.field; radius: 5
            border.color: parent.activeFocus ? Ink.lavender : Ink.inactive
        }
    }
    Field {
        id: nameField
        visible: picker.page === "edit"; placeholderText: "Place name"; Accessible.name: placeholderText
        onAccepted: coordinateField.forceActiveFocus()
    }
    Field {
        id: coordinateField
        visible: picker.page === "edit"; placeholderText: "Latitude, longitude"; Accessible.name: placeholderText
        onAccepted: picker.save()
    }
    Text {
        visible: picker.page === "remove"; width: parent.width
        text: picker.original?.name || ""; textFormat: Text.PlainText; wrapMode: Text.Wrap
        horizontalAlignment: Text.AlignHCenter; color: Ink.text; font.family: "Inter"
    }
    Text {
        width: parent.width; visible: !!text
        text: picker.error || picker.clock.error || ""; textFormat: Text.PlainText
        wrapMode: Text.WrapAnywhere; color: Ink.lavender; font.family: "Inter"; font.pixelSize: 12
    }
    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        visible: picker.page === "edit" || picker.page === "remove"
        enabled: !writer.running
        BarButton {
            label: picker.page === "remove" ? "Remove" : "Save"; labelColor: Ink.lavender
            onTriggered: {
                if (picker.page === "remove") picker.submit("remove", {id: picker.original.id, original: picker.original})
                else picker.save()
            }
        }
        BarButton {
            visible: picker.page === "edit" && !!picker.original; label: "Remove…"
            onTriggered: picker.page = "remove"
        }
        BarButton { label: "Cancel"; onTriggered: picker.reset() }
    }
}
