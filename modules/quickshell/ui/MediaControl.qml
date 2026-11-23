import QtQuick
import Quickshell
import Quickshell.Services.Mpris
import Quickshell.Io
import "Config.js" as Config
import "Palette.js" as Ink

TaskButton {
    id: mediaButton
    required property var output
    required property bool boostAllowed
    readonly property string speakerIcon: output && !output.muted ? "audio-volume-high" : "audio-volume-muted"
    signal openRequested()
    function setOutputVolume(value) {
        if (!output) return
        const next = Math.max(0, Math.min(boostAllowed ? 2 : 1, value))
        if (Math.abs(output.volume - next) < 0.0001) return
        output.volume = next
        previewDelay.restart()
    }
    Timer {
        id: previewDelay
        interval: 100
        onTriggered: if (mediaButton.output && !mediaButton.output.muted && mediaButton.output.volume > 0)
            preview.running = true
    }
    Process { id: preview; command: Config.commands.volumeFeedback }
    // playerctld can retain stale metadata after the last real player exits.
    readonly property var players: Mpris.players.values.filter(p =>
        p.dbusName !== "org.mpris.MediaPlayer2.playerctld" && p.playbackState !== MprisPlaybackState.Stopped)
    readonly property var currentPlayer: players.find(p => p.isPlaying) || players[0] || null
    property MprisPlayer player: null
    onCurrentPlayerChanged: if (currentPlayer) player = currentPlayer
    Timer {
        // Some players briefly report Stopped between tracks. Keep the popup anchored.
        interval: 350
        running: !mediaButton.currentPlayer && !!mediaButton.player
        onTriggered: mediaButton.player = null
    }
    readonly property string title: player?.trackTitle || player?.identity || ""
    readonly property string action: player?.isPlaying ? "Pause" : "Play"
    readonly property alias accent: palette.accent
    CoverAccent { id: palette; artwork: mediaButton.player?.trackArtUrl || "" }

    minimumWidth: contents.implicitWidth + 2 * padding
    underlineWidth: width - 2 * padding
    Row {
        id: contents
        anchors.centerIn: parent; spacing: 5
        Text {
            anchors.verticalCenter: parent.verticalCenter; visible: !!mediaButton.title
            text: "♪"; color: mediaButton.accent; font.pixelSize: 14
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter; visible: !!text
            width: Math.min(implicitWidth, 185)
            text: mediaButton.title; textFormat: Text.PlainText; elide: Text.ElideRight
            font.family: "Inter"; font.pixelSize: 13; color: Ink.text
        }
        SettingsIcon { anchors.verticalCenter: parent.verticalCenter; width: 22; symbol: mediaButton.speakerIcon }
    }
    Accessible.name: title ? "Audio · " + title : "Audio"
    hint: selected ? "" : [(output ? (output.muted ? "Muted" : "Volume · " + Math.round(output.volume * 100) + "%") : "No audio output"),
        title, title ? "Middle-click to " + action.toLowerCase() : ""].filter(Boolean).join("\n")
    onScrolled: delta => { if (output) setOutputVolume(output.volume + Math.sign(delta) * 0.05) }
    buttons: Qt.LeftButton | Qt.MiddleButton | Qt.BackButton | Qt.ForwardButton
    onTriggered: button => {
        if (button === Qt.LeftButton) openRequested()
        else if (button === Qt.MiddleButton && player?.canTogglePlaying) player.togglePlaying()
        else if (button === Qt.BackButton && player?.canGoPrevious) player.previous()
        else if (button === Qt.ForwardButton && player?.canGoNext) player.next()
    }
}
