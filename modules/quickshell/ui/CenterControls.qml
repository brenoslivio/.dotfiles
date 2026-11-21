import QtQuick
import Quickshell
import Quickshell.Services.Mpris
import "Config.js" as Config
import "Palette.js" as Ink

Rectangle {
    id: center
    required property var state
    // playerctld stays on the bus after the last player exits and can leave stale metadata.
    readonly property var players: Mpris.players.values.filter(p => p.dbusName !== "org.mpris.MediaPlayer2.playerctld"
        && !p.dbusName.toLowerCase().includes("brave")
        && p.playbackState !== MprisPlaybackState.Stopped)
    readonly property var player: players.find(p => p.isPlaying) || players[0] || null
    readonly property string trackTitle: player?.trackTitle || player?.identity || ""
    color: Ink.field; radius: 8; height: 30; width: controls.implicitWidth + 10
    Row {
        id: controls
        anchors.centerIn: parent
        spacing: 2
        BarButton {
            iconSource: Config.commands.bellIcon
            readonly property string mode: center.state.notifications.alt || ""
            alert: mode.includes("notification")
            slashed: mode.includes("dnd")
            hint: (center.state.notifications.tooltip || "Notifications") + "\nLeft-click to open · Right-click for Do Not Disturb"
            buttons: Qt.LeftButton | Qt.RightButton
            onTriggered: button => Quickshell.execDetached(Config.commands.notifications.concat([button === Qt.RightButton ? "-d" : "-t", "-sw"]))
        }
        BarButton {
            id: updates
            readonly property var flags: center.state.updates["class"] || []
            property bool animateAutomatic: false
            Timer {
                interval: 500
                running: updates.flags.includes("checking")
                onTriggered: updates.animateAutomatic = true
            }
            onFlagsChanged: if (!flags.includes("checking")) animateAutomatic = false
            iconSource: Config.commands.updateIcon
            alert: flags.includes("attention")
            spinning: flags.includes("manual") || animateAutomatic
            hint: menu.visible ? "" : center.state.updates.tooltip || "Check for updates"
            buttons: Qt.LeftButton | Qt.RightButton
            onTriggered: button => {
                if (button === Qt.RightButton) menu.toggle()
                else Quickshell.execDetached(Config.commands.updates.concat("manual"))
            }
            ActionMenu { id: menu; anchor.item: updates; command: Config.commands.updates }
        }
        BarButton {
            id: clockButton
            readonly property var weather: center.state.clock.weather
            label: (center.state.clock.label || "…") + (weather?.icon ? "   " + weather.icon + "  " + weather.temperature + "°" : "")
            subtitle: center.player ? (center.player.isPlaying ? "♪  " : "⏸  ") + center.trackTitle : ""
            buttons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton | Qt.BackButton | Qt.ForwardButton
            hint: calendar.visible ? "" : [center.state.clock.place?.name, center.state.clock.zone, center.trackTitle, center.player?.trackArtist].filter(Boolean).join("\n")
            onTriggered: button => {
                if (button === Qt.MiddleButton || button === Qt.BackButton) {
                    if (center.player?.canGoPrevious) center.player.previous()
                    return
                }
                if (button === Qt.ForwardButton) {
                    if (center.player?.canGoNext) center.player.next()
                    return
                }
                const places = button === Qt.RightButton
                const close = calendar.visible && calendar.showPlaces === places
                calendar.showPlaces = places
                calendar.visible = !close
            }
            ClockPopup {
                id: calendar
                anchor.item: clockButton
                clock: center.state.clock
                player: center.player
                trackTitle: center.trackTitle
            }
        }
        BarButton {
            id: tasks
            iconSource: Config.commands.taskIcon; labelColor: Ink.lavender
            label: center.state.tasks.text || "0"
            hint: taskMenu.visible ? "" : center.state.tasks.tooltip || ""
            richHint: true
            buttons: Qt.LeftButton | Qt.RightButton
            onTriggered: button => {
                if (button === Qt.RightButton) taskMenu.toggle()
                else Quickshell.execDetached(Config.commands.obsidian)
            }
            ActionMenu { id: taskMenu; anchor.item: tasks; command: Config.commands.tasks }
        }
    }
}
