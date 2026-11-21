import QtQuick
import Quickshell
import "Palette.js" as Ink
import "Config.js" as Config

Row {
    id: controls
    required property PanelWindow bar
    required property var state
    function togglePowerMenu() { powerMenu.visible = !powerMenu.visible }
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
        minimumWidth: 48; padding: 3; buttons: Qt.NoButton; richHint: true; highlight: false
        hint: controls.state.memory.tooltip || ""
    }
    BarButton {
        label: "  " + (controls.state.cpu.text || "0") + "%"
        minimumWidth: 48; padding: 3; buttons: Qt.NoButton; richHint: true; highlight: false
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
        id: power
        label: "⏻"; glyph: true; labelColor: Ink.lavender
        hint: powerMenu.visible ? "" : "Power menu"
        selected: powerMenu.visible
        onTriggered: controls.togglePowerMenu()
        PowerMenu { id: powerMenu; bar: controls.bar }
        TapHandler {
            parent: controls.bar.contentItem
            enabled: powerMenu.visible
            acceptedButtons: Qt.AllButtons
            onTapped: point => {
                if (!power.contains(parent.mapToItem(power, point.position))) powerMenu.visible = false
            }
        }
    }
}
