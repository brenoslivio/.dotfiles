import QtQuick
import Quickshell
import Quickshell.Services.Mpris
import "Palette.js" as Ink

BarButton {
    id: media
    // playerctld can retain stale metadata after the last real player exits.
    readonly property var players: Mpris.players.values.filter(p =>
        p.dbusName !== "org.mpris.MediaPlayer2.playerctld" && p.playbackState !== MprisPlaybackState.Stopped)
    readonly property var currentPlayer: players.find(p => p.isPlaying) || players[0] || null
    property MprisPlayer player: null
    onCurrentPlayerChanged: if (currentPlayer) player = currentPlayer
    Timer {
        // Some players briefly report Stopped between tracks. Keep the popup anchored.
        interval: 350
        running: !media.currentPlayer && !!media.player
        onTriggered: media.player = null
    }
    readonly property string title: player?.trackTitle || player?.identity || ""
    readonly property string action: player?.isPlaying ? "Pause" : "Play"
    readonly property alias accent: palette.accent
    CoverAccent { id: palette; artwork: media.player?.trackArtUrl || "" }

    visible: !!player
    width: Math.min(implicitWidth, 230)
    labelFormat: Text.StyledText
    label: "<font color='" + accent + "'>♪</font>&nbsp; " + title.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    labelColor: Ink.text
    buttons: Qt.LeftButton | Qt.MiddleButton | Qt.BackButton | Qt.ForwardButton
    Accessible.role: Accessible.Button
    Accessible.name: action + " " + title
    Accessible.onPressAction: if (player?.canTogglePlaying) player.togglePlaying()
    onTriggered: button => {
        if (button === Qt.LeftButton && player?.canTogglePlaying) player.togglePlaying()
        else if (button === Qt.ForwardButton && player?.canGoNext) player.next()
        else if ((button === Qt.BackButton || button === Qt.MiddleButton) && player?.canGoPrevious) player.previous()
    }
    onVisibleChanged: if (!visible) popup.visible = false

    Timer {
        interval: 300
        running: media.visible && media.hovered && !popup.visible
        onTriggered: popup.visible = true
    }
    Timer {
        interval: 250
        running: popup.visible && !media.hovered && !cardHover.hovered
        onTriggered: popup.visible = false
    }
    PopupWindow {
        id: popup
        anchor.item: media
        anchor.edges: Edges.Bottom
        anchor.gravity: Edges.Bottom
        color: "transparent"
        implicitWidth: 310
        implicitHeight: Math.max(cover.height, details.implicitHeight) + 24

        Rectangle {
            anchors.fill: parent
            radius: 10; color: Ink.panel; border.color: media.accent
            HoverHandler { id: cardHover }
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
                    source: popup.visible ? media.player?.trackArtUrl || "" : ""
                    asynchronous: true; fillMode: Image.PreserveAspectFit
                    sourceSize.width: 144; sourceSize.height: 144
                }
            }
            Column {
                id: details
                anchors { left: cover.right; leftMargin: 10; right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
                spacing: 4
                Text {
                    width: parent.width; text: media.title; textFormat: Text.PlainText
                    wrapMode: Text.Wrap; color: Ink.text
                    font.family: "Inter"; font.pixelSize: 13; font.bold: true
                }
                Text {
                    width: parent.width; visible: !!text
                    text: media.player?.trackArtist || ""; textFormat: Text.PlainText
                    elide: Text.ElideRight; color: Ink.muted; font.family: "Inter"; font.pixelSize: 12
                }
                Row {
                    spacing: 4
                    TransportButton {
                        label: "│◀"; Accessible.name: "Previous"
                        enabled: !!media.player?.canGoPrevious
                        onTriggered: media.player.previous()
                    }
                    TransportButton {
                        label: media.player?.isPlaying ? "⏸" : "▶"; Accessible.name: media.action
                        labelColor: Ink.lavender; enabled: !!media.player?.canTogglePlaying
                        onTriggered: media.player.togglePlaying()
                    }
                    TransportButton {
                        label: "▶│"; Accessible.name: "Next"
                        enabled: !!media.player?.canGoNext
                        onTriggered: media.player.next()
                    }
                }
                Column {
                    id: progress
                    width: parent.width; spacing: 3
                    readonly property real duration: media.player?.lengthSupported ? media.player.length : 0
                    visible: duration > 0 && !!media.player?.positionSupported
                    readonly property real elapsed: Math.max(0, Math.min(duration, media.player?.position || 0))
                    readonly property real shownTime: seekPointer.pressed && seekPointer.sameTrack
                        ? seekPointer.timeAt(seekPointer.mouseX) : elapsed
                    function timestamp(seconds: real): string {
                        const total = Math.floor(seconds)
                        const minutes = Math.floor(total / 60)
                        const mm = minutes >= 60 ? Math.floor(minutes / 60) + ":" + String(minutes % 60).padStart(2, "0") : String(minutes)
                        return mm + ":" + String(total % 60).padStart(2, "0")
                    }
                    Timer {
                        running: popup.visible && progress.visible && !!media.player?.isPlaying
                        interval: 500; repeat: true; triggeredOnStart: true
                        onTriggered: media.player?.positionChanged()
                    }
                    Item {
                        width: parent.width; height: 18
                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width; height: 4; radius: 2; color: Ink.field
                            Rectangle {
                                id: played
                                width: progress.duration > 0 ? parent.width * progress.shownTime / progress.duration : 0
                                height: parent.height; radius: parent.radius; color: media.accent
                            }
                            Rectangle {
                                visible: seekPointer.enabled && (seekPointer.containsMouse || seekPointer.pressed)
                                anchors.verticalCenter: parent.verticalCenter
                                x: Math.max(0, Math.min(parent.width - width, played.width - width / 2))
                                width: 8; height: 8; radius: 4; color: media.accent
                            }
                        }
                        MouseArea {
                            id: seekPointer
                            anchors.fill: parent
                            enabled: progress.visible && !!media.player?.canSeek
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            property MprisPlayer pressedPlayer: null
                            property int pressedTrack: -1
                            readonly property bool sameTrack: !!pressedPlayer && pressedPlayer === media.player
                                && pressedTrack === pressedPlayer.uniqueId
                            function timeAt(x: real): real {
                                return progress.duration * Math.max(0, Math.min(1, x / width))
                            }
                            onPressed: {
                                pressedPlayer = media.player
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
        }
    }
    component TransportButton: BarButton {
        minimumWidth: 34
        opacity: enabled ? 1 : 0.38
        activeFocusOnTab: enabled
        border.color: activeFocus ? Ink.lavender : "transparent"
        Accessible.role: Accessible.Button
        Accessible.onPressAction: if (enabled) triggered(Qt.LeftButton)
        Keys.onSpacePressed: triggered(Qt.LeftButton)
        Keys.onReturnPressed: triggered(Qt.LeftButton)
    }
}
