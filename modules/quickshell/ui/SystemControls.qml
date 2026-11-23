import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Wayland
import "Palette.js" as Ink
import "Config.js" as Config

Row {
    id: controls
    required property PanelWindow bar
    required property var state
    readonly property alias mediaAccent: mediaButton.accent
    function togglePowerMenu() {
        if (quick.visible && quick.page === "Power") quick.close()
        else {
            controls.state.controlPopup = quick
            quick.page = "Power"
        }
    }
    spacing: 2
    Repeater {
        model: controls.state.capture.indicators || []
        BarButton {
            required property var modelData
            label: modelData.icon; hint: modelData.hint
            glyph: true; labelColor: Ink.lavender
            minimumWidth: 21; padding: 2; buttons: Qt.NoButton; highlight: false
            Accessible.name: hint
        }
    }
    MediaControl {
        id: mediaButton
        output: controls.state.sink?.audio ?? null
        boostAllowed: controls.state.boostAllowed === true
        selected: mediaPopup.visible
        onOpenRequested: controls.state.controlPopup = mediaPopup.visible ? null : mediaPopup
    }
    Divider { height: 15 }
    Rectangle {
        id: resources
        width: metrics.width; height: metrics.height; radius: 7
        color: resourcePopup.visible || memoryButton.hovered || cpuButton.hovered ? Ink.selection : "transparent"
        component MetricButton: TaskButton {
            required property string metric
            required property var sample
            id: metricButton
            minimumWidth: Math.max(48, metricLabel.implicitWidth + 6)
            padding: 3; color: "transparent"; richHint: true
            Row {
                id: metricLabel
                anchors.centerIn: parent; spacing: 4
                SettingsIcon { width: 17; anchors.verticalCenter: parent.verticalCenter; symbol: metricButton.metric === "Memory" ? "ram" : "cpu" }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: (metricButton.sample.text ?? "–") + "%"
                    color: Ink.muted; font.family: "Inter"; font.pixelSize: 13
                }
            }
            hint: resourcePopup.visible ? "" : sample.tooltip ?? ""
            Accessible.name: metric + " " + (sample.text ?? "–") + "%, open resources"
            onTriggered: resourcePopup.toggle(metric)
        }
        Row {
            id: metrics
            MetricButton { id: memoryButton; metric: "Memory"; sample: controls.state.memory }
            MetricButton { id: cpuButton; metric: "CPU"; sample: controls.state.cpu }
        }
        Rectangle {
            visible: resourcePopup.visible; anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width - 12; height: 2; radius: 1; color: Ink.magenta
        }
    }
    Divider {}
    Tray { id: tray; anchors.verticalCenter: parent.verticalCenter }
    Divider { visible: tray.implicitWidth > 0 }
    BarButton {
        visible: !!controls.state.display.text
        label: controls.state.display.text || ""; glyph: true; labelColor: Ink.lavender
        hint: controls.state.display.tooltip || ""
        onTriggered: Quickshell.execDetached(controls.state.displayCommand.concat("menu"))
    }
    component StatusIcon: SettingsIcon {
        anchors.verticalCenter: parent.verticalCenter
        width: 22
    }
    TaskButton {
        id: settings
        underlineWidth: width - 2 * padding
        minimumWidth: indicators.implicitWidth + 14
        Row {
            id: indicators
            anchors.centerIn: parent; spacing: 6
            StatusIcon { symbol: quick.wifiIcon }
            StatusIcon { symbol: quick.bluetoothIcon }
            StatusIcon {
                visible: quick.brightness != null; symbol: quick.brightnessIcon
                WheelHandler {
                    onWheel: event => {
                        if (event.angleDelta.y) Quickshell.execDetached(Config.commands.brightness.concat(event.angleDelta.y > 0 ? "+5%" : "5%-"))
                        event.accepted = true
                    }
                }
            }
            StatusIcon { visible: !!quick.battery; symbol: quick.batteryIcon }
            StatusIcon { symbol: "system-shutdown"; color: Ink.lavender }
        }
        Accessible.name: "Quick Settings"
        hint: quick.visible ? "" : ["Quick Settings", quick.brightness != null ? "Brightness · " + quick.brightness + "%" : "",
            quick.battery ? "Battery · " + quick.battery.tooltip : ""].filter(Boolean).join("\n")
        selected: quick.visible
        onTriggered: controls.state.controlPopup = quick.visible ? null : quick
    }
    QuickSettings { id: quick; bar: controls.bar; state: controls.state }
    ResourcePopup { id: resourcePopup; bar: controls.bar; state: controls.state; button: resources }
    PanelWindow {
        id: mediaPopup
        screen: controls.bar.screen
        visible: !!controls.bar.screen && controls.state.controlPopup === mediaPopup
        anchors { top: true; left: true }
        margins {
            top: controls.bar.margins.top + controls.bar.height + 5
            left: Math.max(0, Math.min(controls.bar.margins.left + controls.x + mediaButton.x,
                (mediaPopup.screen?.width || 400) - mediaPopup.implicitWidth - controls.bar.margins.right))
        }
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
        WlrLayershell.namespace: "dotfiles-audio"
        implicitWidth: Math.min(380, (screen?.width || 400) - 28)
        implicitHeight: Math.max(1, Math.min(card.implicitHeight, (screen?.height || 600) - margins.top - 14))
        color: "transparent"
        QuickAudio {
            id: card
            anchors.fill: parent; media: mediaButton; showing: mediaPopup.visible; focus: true
            onCloseRequested: controls.state.controlPopup = null
            Keys.onEscapePressed: controls.state.controlPopup = null
        }
    }
    HyprlandFocusGrab {
        active: quick.visible || mediaPopup.visible || resourcePopup.visible
        windows: [quick, mediaPopup, resourcePopup, controls.bar]
        onCleared: if (quick.visible || mediaPopup.visible || resourcePopup.visible) controls.state.controlPopup = null
    }
    TapHandler {
        parent: controls.bar.contentItem
        enabled: quick.visible || mediaPopup.visible || resourcePopup.visible
        acceptedButtons: Qt.AllButtons
        onTapped: point => {
            if (!settings.contains(parent.mapToItem(settings, point.position))
                && !resources.contains(parent.mapToItem(resources, point.position))
                && !(mediaButton.visible && mediaButton.contains(parent.mapToItem(mediaButton, point.position))))
                controls.state.controlPopup = null
        }
    }
}
