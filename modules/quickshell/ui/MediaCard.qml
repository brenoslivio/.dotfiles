import QtQuick
import Quickshell.Services.Mpris
import "Palette.js" as Ink

Rectangle {
    id: card
    required property var media
    required property bool showing
    implicitHeight: Math.max(cover.height, details.implicitHeight) + 24
    radius: 10; color: Ink.panel; border.color: card.media.accent
    Rectangle {
        id: cover
        anchors { left: parent.left; leftMargin: 12; verticalCenter: parent.verticalCenter }
        width: 72; height: 72; radius: 6; color: Ink.field
        Text {
            anchors.centerIn: parent
            visible: art.status !== Image.Ready
            text: "♪"; font.pixelSize: 28; color: Ink.lavender
        }
        Image {
            id: art
            anchors.fill: parent
            source: card.showing ? card.media.player?.trackArtUrl || "" : ""
            asynchronous: true; fillMode: Image.PreserveAspectFit
            sourceSize.width: 144; sourceSize.height: 144
        }
    }
    Column {
        id: details
        anchors { left: cover.right; leftMargin: 10; right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
        spacing: 4
        Text {
            width: parent.width; text: card.media.title; textFormat: Text.PlainText
            wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; color: Ink.text
            font.family: "Inter"; font.pixelSize: 13; font.bold: true
        }
        Text {
            width: parent.width; visible: !!text
            text: card.media.player?.trackArtist || ""; textFormat: Text.PlainText
            elide: Text.ElideRight; color: Ink.muted; font.family: "Inter"; font.pixelSize: 12
        }
        Row {
            spacing: 4
            TransportButton {
                symbol: "media-skip-backward"; Accessible.name: "Previous"
                enabled: !!card.media.player?.canGoPrevious
                onTriggered: card.media.player.previous()
            }
            TransportButton {
                symbol: card.media.player?.isPlaying ? "media-playback-pause" : "media-playback-start"; Accessible.name: card.media.action
                labelColor: Ink.lavender; enabled: !!card.media.player?.canTogglePlaying
                onTriggered: card.media.player.togglePlaying()
            }
            TransportButton {
                symbol: "media-skip-forward"; Accessible.name: "Next"
                enabled: !!card.media.player?.canGoNext
                onTriggered: card.media.player.next()
            }
        }
        Column {
            id: progress
            width: parent.width; spacing: 3
            readonly property real duration: card.media.player?.lengthSupported ? card.media.player.length : 0
            visible: duration > 0 && !!card.media.player?.positionSupported
            readonly property real elapsed: Math.max(0, Math.min(duration, card.media.player?.position || 0))
            readonly property real shownTime: seekPointer.pressed && seekPointer.sameTrack
                ? seekPointer.timeAt(seekPointer.mouseX) : elapsed
            function timestamp(seconds: real): string {
                const total = Math.floor(seconds)
                const minutes = Math.floor(total / 60)
                const mm = minutes >= 60 ? Math.floor(minutes / 60) + ":" + String(minutes % 60).padStart(2, "0") : String(minutes)
                return mm + ":" + String(total % 60).padStart(2, "0")
            }
            Timer {
                running: card.showing && progress.visible && !!card.media.player?.isPlaying
                interval: 500; repeat: true; triggeredOnStart: true
                onTriggered: card.media.player?.positionChanged()
            }
            Item {
                width: parent.width; height: 18
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width; height: 4; radius: 2; color: Ink.field
                    Rectangle {
                        id: played
                        width: progress.duration > 0 ? parent.width * progress.shownTime / progress.duration : 0
                        height: parent.height; radius: parent.radius; color: card.media.accent
                    }
                    Rectangle {
                        visible: seekPointer.enabled && (seekPointer.containsMouse || seekPointer.pressed)
                        anchors.verticalCenter: parent.verticalCenter
                        x: Math.max(0, Math.min(parent.width - width, played.width - width / 2))
                        width: 8; height: 8; radius: 4; color: card.media.accent
                    }
                }
                MouseArea {
                    id: seekPointer
                    anchors.fill: parent
                    enabled: progress.visible && !!card.media.player?.canSeek
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    property MprisPlayer pressedPlayer: null
                    property int pressedTrack: -1
                    readonly property bool sameTrack: !!pressedPlayer && pressedPlayer === card.media.player
                        && pressedTrack === pressedPlayer.uniqueId
                    function timeAt(x: real): real {
                        return progress.duration * Math.max(0, Math.min(1, x / width))
                    }
                    onPressed: {
                        pressedPlayer = card.media.player
                        pressedTrack = pressedPlayer.uniqueId
                    }
                    onReleased: mouse => {
                        if (sameTrack && enabled) pressedPlayer.position = timeAt(mouse.x)
                        pressedPlayer = null
                    }
                    onCanceled: pressedPlayer = null
                }
            }
            Item {
                width: parent.width; implicitHeight: elapsedLabel.implicitHeight
                Text {
                    id: elapsedLabel
                    text: progress.timestamp(progress.shownTime)
                    color: Ink.muted; font.family: "Inter"; font.pixelSize: 11
                }
                Text {
                    anchors.right: parent.right
                    text: progress.timestamp(progress.duration)
                    color: Ink.muted; font.family: "Inter"; font.pixelSize: 11
                }
            }
        }
    }
    component TransportButton: TaskButton {
        id: transport
        required property string symbol
        minimumWidth: 36; height: 32
        SettingsIcon {
            anchors.centerIn: parent; symbol: transport.symbol
            color: transport.hovered || transport.activeFocus ? Ink.text : transport.labelColor
        }
    }
}
