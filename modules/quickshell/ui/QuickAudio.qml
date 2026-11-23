import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic as Controls
import Quickshell.Io
import Quickshell.Services.Pipewire
import "Palette.js" as Ink
import "Config.js" as Config

Rectangle {
    id: audio
    required property var media
    required property bool showing
    signal closeRequested()
    implicitHeight: sections.implicitHeight + 28
    color: Ink.panel; radius: 13; border.color: Qt.alpha(Ink.lavender, 0.48)
    property var rows: []
    property var confirmation: null
    property string error: ""
    onShowingChanged: if (!showing) { confirmation = null; error = ""; scroll.contentY = 0 }
    readonly property var mic: Pipewire.defaultAudioSource
    PwObjectTracker { objects: audio.mic ? [audio.mic] : [] }
    Process {
        id: reader
        command: Config.commands.audio.concat("choices")
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const rows = JSON.parse(text)
                    if (JSON.stringify(rows) !== JSON.stringify(audio.rows)) audio.rows = rows
                } catch (_) { audio.rows = []; audio.error = "Audio devices unavailable" }
            }
        }
    }
    Timer {
        interval: 1500; running: audio.showing; repeat: true; triggeredOnStart: true
        onTriggered: if (!writer.running) reader.running = true
    }
    Process {
        id: writer
        stderr: StdioCollector { onStreamFinished: if (text.trim()) audio.error = text.trim() }
        onExited: reader.running = true
    }
    function apply(target) {
        error = ""
        confirmation = null
        writer.command = Config.commands.audio.concat(["apply-inline", JSON.stringify(target)])
        writer.running = true
    }
    Flickable {
        id: scroll
        anchors.fill: parent; anchors.margins: 14
        contentWidth: width; contentHeight: sections.implicitHeight
        clip: true; boundsBehavior: Flickable.StopAtBounds
        Controls.ScrollBar.vertical: Controls.ScrollBar {}
        Column {
            id: sections
            width: scroll.width; spacing: 6
            RowLayout {
                width: parent.width
                Text {
                    Layout.fillWidth: true; text: "Audio"; color: Ink.text
                    font.family: "Inter"; font.pixelSize: 19; font.weight: Font.DemiBold
                }
                TaskButton { label: "×"; Accessible.name: "Close audio controls"; onTriggered: audio.closeRequested() }
            }
            QuickLevel {
                width: parent.width; label: "Output volume"; icon: audio.media.speakerIcon
                enabled: !!audio.media.output; canMute: true; muted: !!audio.media.output?.muted
                percent: 100 * (audio.media.output?.volume ?? 0)
                maximum: audio.media.boostAllowed ? 200 : 100
                boostRange: audio.media.boostAllowed
                onToggleMute: if (audio.media.output) audio.media.output.muted = !muted
                onAdjusted: percent => audio.media.setOutputVolume(percent / 100)
            }
            PanelSwitch {
                width: parent.width
                text: "Allow volume above 100%"
                checked: audio.media.boostAllowed
                enabled: !boostWriter.running
                onToggled: {
                    boostWriter.command = Config.commands.audio.concat(checked ? "boost-on" : "boost-off")
                    boostWriter.running = true
                }
                Process { id: boostWriter }
            }
            Repeater {
                model: audio.rows
                Loader {
                    id: row
                    required property var modelData
                    width: sections.width
                    sourceComponent: modelData.heading ? heading : choice
                    Component {
                        id: heading
                        Column {
                            Text {
                                text: row.modelData.heading; color: Ink.lavender
                                font.family: "Inter"; font.pixelSize: 12; topPadding: 6; bottomPadding: 2
                            }
                            QuickLevel {
                                width: parent.width; visible: row.modelData.heading === "Microphone" && !!audio.mic?.audio
                                label: "Microphone input"; icon: muted ? "microphone-sensitivity-muted" : "microphone-sensitivity-high"
                                percent: 100 * (audio.mic?.audio?.volume ?? 0); muted: !!audio.mic?.audio?.muted
                                canMute: true
                                onToggleMute: audio.mic.audio.muted = !muted
                                onAdjusted: percent => { if (audio.mic?.audio) audio.mic.audio.volume = percent / 100 }
                            }
                        }
                    }
                    Component {
                        id: choice
                        QuickChoice {
                            text: row.modelData.label
                            current: !!row.modelData.current; trailing: current ? "✓" : ""
                            enabled: !!row.modelData.target && !writer.running
                            onClicked: {
                                if (row.modelData.target.action === "headset") audio.confirmation = row.modelData.target
                                else audio.apply(row.modelData.target)
                            }
                        }
                    }
                }
            }
            Text {
                visible: !!text; width: parent.width; wrapMode: Text.Wrap; color: Ink.muted
                text: audio.confirmation ? "Using the headset microphone switches playback to call quality." : audio.error
            }
            Row {
                visible: !!audio.confirmation; spacing: 6
                TaskButton { label: "Switch profile"; onTriggered: audio.apply(audio.confirmation) }
                TaskButton { label: "Cancel"; onTriggered: audio.confirmation = null }
            }
            MediaCard {
                width: parent.width; visible: !!audio.media.player
                media: audio.media; showing: audio.showing && visible
            }
        }
    }
}
