import QtQuick
import Quickshell
import Quickshell.Services.Mpris
import "Palette.js" as Ink
import "Config.js" as Config

Row {
    id: controls
    required property var state
    required property int availableWidth
    readonly property var players: Mpris.players.values.filter(p => !p.dbusName.toLowerCase().includes("brave")
        && p.playbackState !== MprisPlaybackState.Stopped)
    readonly property var player: players.find(p => p.isPlaying) || players[0]
    spacing: 2
    BarButton {
        readonly property int room: controls.availableWidth - fixed.implicitWidth - 6
        visible: !!controls.player && room >= 45
        width: Math.min(implicitWidth, 355, Math.max(0, room))
        label: (controls.player?.isPlaying ? "▶   " : "⏸   ") + (controls.player?.trackTitle || controls.player?.identity || "")
        italic: !!controls.player && !controls.player.isPlaying
        hint: [controls.player?.trackTitle, controls.player?.trackArtist].filter(Boolean).join("\n")
        buttons: Qt.LeftButton | Qt.MiddleButton | Qt.RightButton | Qt.BackButton | Qt.ForwardButton
        onTriggered: button => {
            if (button === Qt.LeftButton) controls.player.togglePlaying()
            else if (button === Qt.MiddleButton || button === Qt.BackButton) controls.player.previous()
            else controls.player.next()
        }
    }
    Row {
        id: fixed
        spacing: 2
        BarButton {
            id: volume
            readonly property var audio: controls.state.sink?.audio
            label: (controls.state.capture.icon || (audio?.muted ? "󰝟" : "󰕾")) + "  "
                + (audio ? Math.round(audio.volume * 100) + "%" : "—")
            marked: controls.state.capture.multiple === true
            hint: audioMenu.visible ? "" : [controls.state.sink?.description || "Audio output", controls.state.capture.details,
                "Right-click to choose output or microphone"].filter(Boolean).join("\n")
            buttons: Qt.LeftButton | Qt.RightButton
            onTriggered: button => {
                if (button === Qt.RightButton) audioMenu.toggle()
                else Quickshell.execDetached(Config.commands.mixer)
            }
            onScrolled: delta => { if (audio) audio.volume = Math.max(0, Math.min(1, audio.volume + Math.sign(delta) * 0.05)) }
            ActionMenu { id: audioMenu; anchor.item: volume; command: Config.commands.audio }
        }
        Divider {}
        BarButton {
            label: "  " + (controls.state.memory.text || "0") + "%"
            minimumWidth: 56; buttons: Qt.NoButton; richHint: true; highlight: false
            hint: controls.state.memory.tooltip || ""
        }
        BarButton {
            label: "  " + (controls.state.cpu.text || "0") + "%"
            minimumWidth: 56; buttons: Qt.NoButton; richHint: true; highlight: false
            hint: controls.state.cpu.tooltip || ""
        }
        Divider {}
        Tray { id: tray; anchors.verticalCenter: parent.verticalCenter }
        Divider { visible: tray.implicitWidth > 0 }
        BarButton {
            readonly property var level: controls.state.hardware.brightness
            visible: level != null
            label: level < 34 ? "󰃞" : level < 67 ? "󰃟" : "󰃠"
            glyph: true; glyphFamily: "FiraCode Nerd Font Propo"; buttons: Qt.NoButton; highlight: false
            hint: "Brightness · " + level + "%"
            onScrolled: delta => Quickshell.execDetached(Config.commands.brightness.concat(delta > 0 ? "+5%" : "5%-"))
        }
        BarButton {
            readonly property var battery: controls.state.hardware.battery
            visible: !!battery
            readonly property bool discharging: battery?.status === "Discharging"
            readonly property var icons: ["", "", "", "", ""]
            label: (battery?.status === "Charging" ? "󰂄" : icons[Math.round((battery?.level || 0) / 25)])
                + (discharging ? " " + battery.level + "%" : "")
            buttons: Qt.NoButton; glyph: !discharging; glyphFamily: "FiraCode Nerd Font Propo"; highlight: false
            hint: battery?.tooltip || ""
        }
        Divider {}
        BarButton {
            visible: !!controls.state.display.text
            label: controls.state.display.text || ""; glyph: true; labelColor: Ink.lavender
            hint: controls.state.display.tooltip || ""
            onTriggered: Quickshell.execDetached(controls.state.displayCommand.concat("menu"))
        }
        BarButton {
            label: "⏻"; glyph: true; labelColor: Ink.lavender
            hint: "Power menu"
            onTriggered: Quickshell.execDetached(Config.commands.power)
        }
    }
}
