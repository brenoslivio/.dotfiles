//@ pragma UseQApplication
//@ pragma RespectSystemStyle
//@ pragma ShellId dotfiles-panel
import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Services.Pipewire
import Quickshell.Io
import Quickshell.Wayland
import "Config.js" as Config
import "Palette.js" as Ink

ShellRoot {
    id: root
    property var clock: ({})
    property var capture: ({})
    property var levels: []
    readonly property var sink: Pipewire.defaultAudioSink
    readonly property var workspaceIcons: ["󰖟", "󰏫", "", "", "", ""]

    Component.onCompleted: Hyprland.refreshToplevels()
    PwObjectTracker { objects: root.sink ? [root.sink] : [] }
    property var boostAllowed: null
    function enforceVolumeLimit() {
        const output = sink?.audio
        if (boostAllowed !== null && output && output.volume > (boostAllowed ? 2 : 1))
            output.volume = boostAllowed ? 2 : 1
    }
    Connections {
        target: root.sink?.audio ?? null
        function onVolumeChanged() { root.enforceVolumeLimit() }
    }
    onSinkChanged: Qt.callLater(enforceVolumeLimit)
    onBoostAllowedChanged: enforceVolumeLimit()
    Feed { command: Config.commands.audio.concat("boost-watch"); onLine: data => root.boostAllowed = JSON.parse(data) }
    readonly property alias notifications: notices
    property PanelWindow controlPopup: null
    onBarVisibleChanged: if (!barVisible) controlPopup = null
    property bool barVisible: true
    NotificationHub {
        id: notices
        focusSession: root.tracking.active ?? null
        now: root.focusNow
        barVisible: root.barVisible
    }
    IpcHandler {
        target: "bar"
        function toggle(): bool {
            root.barVisible = !root.barVisible
            if (!root.barVisible) board.visible = false
            return root.barVisible
        }
    }
    property var updates: ({})
    property var tasks: ({})
    readonly property alias taskBoard: board
    property var tracking: ({})
    readonly property string focusTodayLabel: {
        const a = tracking.active
        const end = Math.min(focusNow, a?.cutoff ?? focusNow)
        const live = a?.running_since == null ? 0 : Math.max(0, end - Math.max(tracking.midnight, a.running_since))
        return "Today " + board.elapsed((tracking.todaySeconds || 0) + live)
    }
    property double focusNow: Date.now() / 1000
    Timer {
        interval: 1000; repeat: true; triggeredOnStart: true
        running: root.tracking.active?.status === "running"
        onTriggered: root.focusNow = Math.floor(Date.now() / 1000)
    }
    Feed {
        property string zone: root.clock.zone || ""
        command: Config.commands.focus.concat(["watch", zone])
        onZoneChanged: if (running) running = false
        onLine: data => root.tracking = JSON.parse(data)
    }
    TaskBoard { id: board; panelState: root }
    property var memory: ({})
    property var cpu: ({})
    property var hardware: ({})
    readonly property alias brightnessControl: brightnessWriter
    BrightnessControl { id: brightnessWriter }
    property var display: ({})
    readonly property var displayCommand: Config.commands.displays
    IpcHandler {
        target: "powerMenu"
        function toggle(): bool {
            const panel = panels.instances.find(p => p.monitor && p.monitor === Hyprland.focusedMonitor)
            if (!panel) return false
            panel.togglePowerMenu()
            return true
        }
    }

    Feed { command: Config.commands.tasks.concat("watch"); onLine: data => root.tasks = JSON.parse(data) }
    Feed { command: Config.commands.updates.concat("watch"); onLine: data => root.updates = JSON.parse(data) }
    Feed { command: Config.commands.resources.concat("memory"); onLine: data => root.memory = JSON.parse(data) }
    Feed { command: Config.commands.resources.concat("cpu"); onLine: data => root.cpu = JSON.parse(data) }
    Feed { command: Config.commands.hardware; onLine: data => root.hardware = JSON.parse(data) }
    Process {
        id: displays
        command: root.displayCommand.concat("status")
        stdout: StdioCollector { onStreamFinished: root.display = text.trim() ? JSON.parse(text) : ({}) }
    }
    Timer { interval: 2000; running: true; repeat: true; triggeredOnStart: true; onTriggered: displays.running = true }
    Feed { command: Config.commands.clock; onLine: data => root.clock = JSON.parse(data) }
    Feed {
        command: Config.commands.capture
        onLine: data => root.capture = JSON.parse(data)
        onExited: root.capture = ({})
    }
    Feed {
        command: Config.commands.spectrum
        onLine: data => {
            const bands = data.trim().split(";")
            if (bands[bands.length - 1] === "") bands.pop()
            if (bands.length !== 64) return
            const levels = bands.map(Number)
            if (!levels.some(level => level > 2)) return
            root.levels = levels
            silence.restart()
        }
    }
    Timer {
        id: silence
        interval: 220
        onTriggered: root.levels = []
    }

    Variants {
        id: panels
        model: Quickshell.screens
        PanelWindow {
            id: panel
            required property var modelData
            screen: modelData
            visible: root.barVisible
            readonly property var monitor: Hyprland.monitorFor(screen)
            readonly property var workspace: monitor?.activeWorkspace
            readonly property var focusedWindow: Hyprland.activeToplevel
            function togglePowerMenu() { systemControls.togglePowerMenu() }
            anchors { left: true; right: true; top: true }
            margins { left: 14; right: 14; top: 10 }
            implicitHeight: 38
            color: "transparent"
            WlrLayershell.layer: WlrLayer.Bottom
            WlrLayershell.namespace: "dotfiles-panel"

            Rectangle {
                id: background
                anchors.fill: parent
                radius: 12; color: Qt.alpha(Ink.panel, 0.96)
                border.color: Qt.alpha(Ink.lavender, 0.65)
                Item {
                    id: spectrum
                    anchors.fill: parent
                    anchors.margins: background.border.width
                    readonly property real corner: background.radius - background.border.width
                    readonly property real baselineInset: 5 - background.border.width
                    readonly property color bandColor: Qt.alpha(systemControls.mediaAccent, 0.22)
                    Repeater {
                        id: bands
                        model: 64
                        Item {
                            id: band
                            required property int index
                            readonly property bool first: index === 0
                            readonly property bool last: index === bands.model - 1
                            readonly property real step: spectrum.width / bands.model
                            x: Math.round(index * step)
                            width: Math.round((index + 1) * step) - x - (last ? 0 : 2)
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: spectrum.baselineInset
                            height: Math.min(1, (root.levels[index] || 0) / 255) * (background.height - 8)
                            clip: first || last
                            Behavior on height { NumberAnimation { duration: 85 } }
                            // Reveal the panel's fixed corner curve up to this band's current level.
                            Rectangle {
                                x: band.last ? band.width - width : 0
                                width: band.clip ? Math.max(band.width, 2 * spectrum.corner) : band.width
                                height: band.clip ? spectrum.height : band.height
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: band.clip ? -spectrum.baselineInset : 0
                                topLeftRadius: band.first ? spectrum.corner : 0
                                bottomLeftRadius: topLeftRadius
                                topRightRadius: band.last ? spectrum.corner : 0
                                bottomRightRadius: topRightRadius
                                color: spectrum.bandColor
                            }
                        }
                    }
                }

                Row {
                    id: left
                    anchors { left: parent.left; leftMargin: 7; verticalCenter: parent.verticalCenter }
                    spacing: 2
                    BarButton {
                        iconSource: Config.commands.logo; iconSize: 24
                        hint: "Open application launcher"
                        onTriggered: Quickshell.execDetached([Quickshell.env("HOME") + "/.config/rofi/launch.sh"])
                    }
                    Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 1; height: 21; color: Qt.alpha(Ink.lavender, 0.3) }
                    Repeater {
                        model: Hyprland.workspaces.values.slice().sort((a, b) => a.id - b.id)
                        BarButton {
                            required property var modelData
                            visible: modelData.monitor === panel.monitor && !modelData.name.startsWith("special:")
                            glyph: true; minimumWidth: 32
                            selected: modelData.active
                            marked: modelData.toplevels.values.length > 0
                            label: root.workspaceIcons[modelData.id - 1] || "󰍺"
                            labelColor: marked ? Ink.lavender : Ink.inactive
                            hint: "Workspace " + modelData.name
                            onTriggered: modelData.activate()
                        }
                    }
                }
                Item {
                    id: windowInfo
                    anchors { left: left.right; leftMargin: 7; right: center.left; rightMargin: 7; verticalCenter: parent.verticalCenter }
                    height: 26
                    readonly property var current: panel.focusedWindow && panel.focusedWindow.workspace === panel.workspace
                        ? panel.focusedWindow : panel.workspace?.toplevels.values.find(w => w.lastIpcObject.address === panel.workspace.lastIpcObject.lastwindow)
                    readonly property string title: current?.title || panel.workspace?.lastIpcObject.lastwindowtitle || ""
                    readonly property string appId: current?.wayland?.appId || current?.lastIpcObject.class || ""
                    readonly property var entry: {
                        if (!appId || !DesktopEntries.applications.values.length) return null
                        const id = appId.toLowerCase().includes("brave") ? "com.brave.Browser" : appId
                        return DesktopEntries.byId(id) || DesktopEntries.heuristicLookup(appId)
                    }
                    visible: width > 45 && !!title
                    Divider {}
                    Image {
                        id: appIcon
                        anchors { left: parent.left; leftMargin: 9; verticalCenter: parent.verticalCenter }
                        width: 16; height: width
                        source: windowInfo.entry?.icon ? Quickshell.iconPath(windowInfo.entry.icon) : ""
                        visible: !!source.toString()
                    }
                    Text {
                        anchors { left: appIcon.visible ? appIcon.right : parent.left; leftMargin: 6; right: parent.right; verticalCenter: parent.verticalCenter }
                        text: {
                            const characters = Array.from(windowInfo.title)
                            return characters.length > 70 ? characters.slice(0, 69).join("") + "…" : windowInfo.title
                        }
                        elide: Text.ElideRight; textFormat: Text.PlainText
                        color: Ink.muted; font.family: "Inter"; font.pixelSize: 13
                    }
                }
                CenterControls {
                    id: center
                    state: root
                    anchors.verticalCenter: parent.verticalCenter
                    x: Math.max(left.x + left.implicitWidth + 3, Math.min((parent.width - width) / 2, systemControls.x - width - 5))
                }
                SystemControls {
                    id: systemControls
                    bar: panel
                    state: root
                    anchors { right: parent.right; rightMargin: 7; verticalCenter: parent.verticalCenter }
                }
            }
        }
    }
}
