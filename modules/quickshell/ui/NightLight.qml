import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic as Controls
import Quickshell.Io
import "Palette.js" as Ink
import "Config.js" as Config

ColumnLayout {
    id: night
    required property bool showing
    required property string city
    property var state: ({})
    readonly property bool powered: !!state.available && !!state.powered
    readonly property string detail: !state.available ? "Unavailable" : state.manual
        ? (powered ? "On until " : "Paused until ") + state.until
        : (powered ? "On" : "Off") + " · Scheduled"
    property string pending: ""
    property string error: ""
    function request(action) {
        pending = String(action)
        if (!writer.running) flush()
    }
    function flush() {
        if (!pending || writer.running) return
        writer.command = Config.commands.nightLight.concat(pending)
        pending = ""
        writer.running = true
    }
    Process {
        id: writer
        stdout: StdioCollector {
            onStreamFinished: if (text.trim()) {
                const next = JSON.parse(text)
                const saved = writer.command[writer.command.length - 1]
                const reload = saved.startsWith("schedule ") || saved === "defaults"
                if (next.start && (next.start !== night.state.start || reload))
                    startField.text = next.start
                if (next.end && (next.end !== night.state.end || reload))
                    endField.text = next.end
                if (next.daytime && (next.daytime !== night.state.daytime || reload))
                    dayField.text = String(next.daytime)
                if (next.nighttime && (next.nighttime !== night.state.nighttime || reload))
                    nightField.text = String(next.nighttime)
                night.state = next
                night.error = ""
            }
        }
        stderr: StdioCollector { onStreamFinished: if (text.trim()) night.error = text.trim() }
        onExited: Qt.callLater(night.flush)
    }
    Timer {
        interval: 2500; running: night.showing; triggeredOnStart: true; repeat: true
        onTriggered: if (!writer.running && !night.pending) night.request("status")
    }
    spacing: 8
    QuickChoice {
        Layout.fillWidth: true
        text: "Night Light"; detail: night.detail; symbol: "weather-clear-night"
        current: night.powered; trailing: night.powered ? "On" : "Off"; enabled: !!night.state.available
        onClicked: night.request("toggle")
    }
    RowLayout {
        Layout.fillWidth: true; Layout.topMargin: 4
        Text { Layout.fillWidth: true; text: "Warmth"; color: Ink.text; font.family: "Inter"; font.pixelSize: 14 }
        Text {
            text: night.state.available ? Math.round(6500 - warmth.value) + " K" : "–"
            color: Ink.lavender; font.family: "Inter"; font.pixelSize: 13
        }
    }
    Controls.Slider {
        id: warmth
        Layout.fillWidth: true; Accessible.name: "Night Light warmth"
        enabled: !!night.state.available; from: 0; to: 4000; stepSize: 25; live: true
        Binding on value {
            when: !warmth.pressed && !writer.running && !night.pending
            value: 6500 - (night.state.kelvin ?? 6500)
            restoreMode: Binding.RestoreNone
        }
        onMoved: night.request(6500 - Math.round(value))
        background: Rectangle {
            x: warmth.leftPadding; y: (warmth.height - height) / 2
            width: warmth.availableWidth; height: 8; radius: 4
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Ink.lavender }
                GradientStop { position: 1; color: "#eaa66c" }
            }
        }
        handle: Rectangle {
            x: warmth.leftPadding + warmth.visualPosition * (warmth.availableWidth - width)
            y: (warmth.height - height) / 2
            width: 16; height: 16; radius: 8; color: Ink.text
            border.color: warmth.visualFocus ? Ink.magenta : Ink.panel
        }
    }
    RowLayout {
        Layout.fillWidth: true
        Text { Layout.fillWidth: true; text: "Cooler"; color: Ink.muted; font.pixelSize: 11 }
        Text { text: "Warmer"; color: Ink.muted; font.pixelSize: 11 }
    }
    QuickChoice {
        Layout.fillWidth: true
        text: night.state.manual ? "Resume schedule" : "Following schedule"
        enabled: !!night.state.manual && !!night.state.available
        onClicked: night.request("resume")
    }
    Text {
        Layout.fillWidth: true; wrapMode: Text.Wrap; textFormat: Text.PlainText
        text: [night.city, night.state.zone].filter(Boolean).join(" · ")
        color: Ink.lavender; font.family: "Inter"; font.pixelSize: 13
    }
    component TimeField: PlaceField {
        Layout.fillWidth: true; placeholderText: "HH:MM"; maximumLength: 5
        validator: RegularExpressionValidator { regularExpression: /([01][0-9]|2[0-3]):[0-5][0-9]/ }
    }
    component KelvinField: PlaceField {
        Layout.fillWidth: true; maximumLength: 4; inputMethodHints: Qt.ImhDigitsOnly
        validator: IntValidator { bottom: 2500; top: 6500; locale: "C" }
    }
    GridLayout {
        columns: 2; Layout.fillWidth: true
        Text { text: "Starts at"; color: Ink.muted }
        Text { text: "Ends at"; color: Ink.muted }
        TimeField { id: startField; Accessible.name: "Night Light starts at" }
        TimeField { id: endField; Accessible.name: "Night Light ends at" }
        Text { text: "Daytime (K)"; color: Ink.muted }
        Text { text: "Nighttime (K)"; color: Ink.muted }
        KelvinField { id: dayField; Accessible.name: "Daytime temperature in kelvin" }
        KelvinField { id: nightField; Accessible.name: "Nighttime temperature in kelvin" }
    }
    readonly property bool validRange: dayField.acceptableInput && nightField.acceptableInput
        && Number(dayField.text) > Number(nightField.text)
    Text {
        Layout.fillWidth: true; wrapMode: Text.Wrap
        visible: !!night.state.available && !night.validRange
        text: "Use 2500–6500 K. Choose a lower temperature for nighttime."
        color: Ink.muted; font.pixelSize: 12
    }
    RowLayout {
        TaskButton {
            label: "Save schedule"
            enabled: !!night.state.available && startField.acceptableInput && endField.acceptableInput
                && startField.text !== endField.text && night.validRange
            onTriggered: night.request(["schedule", startField.text, endField.text, dayField.text, nightField.text].join(" "))
        }
        TaskButton { label: "Restore defaults"; enabled: !!night.state.available; onTriggered: night.request("defaults") }
    }
    Text {
        visible: !!night.state.next; color: Ink.muted
        text: "Next change at " + (night.state.manual ? night.state.until : night.state.next)
    }
    Text { visible: !!text; text: night.error; color: Ink.text; font.pixelSize: 12 }
}
