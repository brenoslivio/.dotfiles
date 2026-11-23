import QtQuick
import QtQuick.Controls.Basic as Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import Quickshell.Networking
import Quickshell.Bluetooth
import "Palette.js" as Ink

PanelWindow {
    id: popup
    required property PanelWindow bar
    required property var state
    readonly property var battery: state.hardware.battery
    readonly property var brightness: state.hardware.brightness
    readonly property string brightnessIcon: "display-brightness-" + (brightness === 0 ? "off"
        : brightness < 34 ? "low" : brightness < 67 ? "medium" : "high")
    readonly property string batteryIcon: "battery-" + String(Math.round((battery?.level ?? 0) / 10) * 10).padStart(3, "0")
        + (battery?.plugged ? "-charging" : "")
    readonly property var wifi: Networking.devices.values.find(d => d.type === DeviceType.Wifi && d.connected)
        || Networking.devices.values.find(d => d.type === DeviceType.Wifi) || null
    readonly property var network: wifi?.networks.values.find(n => n.connected) || null
    readonly property var adapter: Bluetooth.defaultAdapter
    readonly property var connectedDevices: adapter?.devices.values.filter(d => d.connected) ?? []
    readonly property string wifiIcon: !Networking.wifiEnabled ? "network-wireless-disabled"
        : !network ? "network-wireless-offline" : "network-wireless-signal-" +
            (network.signalStrength > 0.75 ? "excellent" : network.signalStrength > 0.5 ? "good"
            : network.signalStrength > 0.25 ? "ok" : "weak")
    readonly property string bluetoothIcon: !adapter?.enabled ? "bluetooth-disabled"
        : connectedDevices.length ? "bluetooth-active" : "bluetooth-disconnected"
    property string page: ""
    function close() { if (state.controlPopup === popup) state.controlPopup = null }
    function back() { if (page) page = ""; else close() }
    onVisibleChanged: if (!visible) page = ""
    onPageChanged: {
        scroll.contentY = 0
        frame.forceActiveFocus()
    }
    visible: !!bar.screen && state.controlPopup === popup
    screen: bar.screen
    anchors { top: true; right: true }
    margins { top: bar.visible ? bar.margins.top + bar.height + 5 : 10; right: bar.margins.right }
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    WlrLayershell.namespace: "dotfiles-quick-settings"
    implicitWidth: Math.min(404, (screen?.width || 440) - 28)
    implicitHeight: Math.min((screen?.height || 600) - margins.top - 14, contents.implicitHeight + 32)
    color: "transparent"

    component SettingsTile: Rectangle {
        id: tile
        required property string label
        required property string detail
        required property string icon
        required property bool powered
        property bool canToggle: true
        signal toggled()
        signal openDetails()
        Layout.fillWidth: true; Layout.preferredWidth: 1; implicitHeight: 58
        color: powered ? Qt.alpha(Ink.lavender, 0.16) : Ink.field
        radius: 10
        RowLayout {
            anchors.fill: parent; anchors.margins: 4; spacing: 0
            TaskButton {
                SettingsIcon { anchors.centerIn: parent; symbol: tile.icon; color: tile.powered ? Ink.lavender : Ink.inactive }
                enabled: tile.canToggle; minimumWidth: 33
                Accessible.name: "Turn " + tile.label + (tile.powered ? " off" : " on")
                onTriggered: tile.toggled()
            }
            Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 24; color: Qt.alpha(Ink.lavender, 0.24) }
            QuickChoice {
                Layout.fillWidth: true; Layout.fillHeight: true; horizontalPadding: 6; padding: 3
                text: tile.label; detail: tile.detail; trailing: "›"
                background: Rectangle {
                    radius: 7; color: parent.hovered ? Ink.selection : "transparent"
                    border.color: parent.visualFocus ? Ink.lavender : "transparent"
                }
                onClicked: tile.openDetails()
            }
        }
    }

    Rectangle {
        id: frame
        anchors.fill: parent; color: Ink.panel; radius: 13; border.color: Qt.alpha(Ink.lavender, 0.48)
        focus: true
        Keys.onPressed: event => { if (popup.page === "Power") powerPage.handleKey(event) }
        Shortcut { sequence: "Escape"; enabled: popup.visible; onActivated: popup.back() }
        Flickable {
            id: scroll
            anchors.fill: parent; anchors.margins: 16; clip: true
            contentWidth: width; contentHeight: contents.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            Controls.ScrollBar.vertical: Controls.ScrollBar {}
            ColumnLayout {
                id: contents
                width: scroll.width; spacing: 9
                RowLayout {
                    id: header
                    Layout.fillWidth: true
                    TaskButton {
                        visible: !!popup.page; Accessible.name: "Back"
                        SettingsIcon { anchors.centerIn: parent; symbol: "go-previous" }
                        onTriggered: popup.back()
                    }
                    Text {
                        Layout.fillWidth: true
                        text: popup.page || "Quick Settings"; color: Ink.text
                        font.family: "Inter"; font.pixelSize: 19; font.weight: Font.DemiBold
                    }
                    RowLayout {
                        visible: !popup.page && !!popup.battery
                        spacing: 4
                        SettingsIcon { symbol: popup.batteryIcon }
                        Text {
                            text: popup.battery ? popup.battery.level + "% · " + popup.battery.label : ""
                            color: Ink.muted; font.family: "Inter"; font.pixelSize: 11
                        }
                    }
                    TaskButton { label: "×"; Accessible.name: "Close Quick Settings"; onTriggered: popup.close() }
                }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 6; visible: !popup.page
                    QuickLevel {
                        Layout.fillWidth: true; label: "Screen brightness"; icon: "display-brightness"; minimum: 1
                        visible: popup.state.hardware.brightness != null
                        percent: popup.state.hardware.brightness ?? 0
                        onAdjusted: (percent, finalValue) => popup.state.brightnessControl.setLevel(percent, finalValue)
                    }
                    RowLayout {
                        Layout.fillWidth: true; Layout.topMargin: 4; spacing: 7
                        SettingsTile {
                            label: "Wi-Fi"; icon: popup.wifiIcon
                            powered: Networking.wifiEnabled; canToggle: !!popup.wifi && Networking.wifiHardwareEnabled
                            detail: !popup.wifi ? "Unavailable" : !powered ? "Off" : popup.network?.name || "Disconnected"
                            onToggled: Networking.wifiEnabled = !powered
                            onOpenDetails: popup.page = "Wi-Fi"
                        }
                        SettingsTile {
                            label: "Bluetooth"; icon: popup.bluetoothIcon
                            powered: !!popup.adapter?.enabled; canToggle: !!popup.adapter && popup.adapter.state !== BluetoothAdapterState.Blocked
                            detail: !popup.adapter ? "Unavailable" : !powered ? "Off" : popup.connectedDevices[0]?.name || "On"
                            onToggled: popup.adapter.enabled = !powered
                            onOpenDetails: popup.page = "Bluetooth"
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 7
                        SettingsTile {
                            label: "Night Light"; icon: "weather-clear-night"
                            powered: night.powered; detail: night.detail; canToggle: !!night.state.available
                            onToggled: night.request("toggle")
                            onOpenDetails: popup.page = "Night Light"
                        }
                        QuickChoice {
                            Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.preferredHeight: 58
                            text: "Power"; detail: "Session actions"; symbol: "system-shutdown"; trailing: "›"
                            iconDivider: true; horizontalPadding: 7
                            onClicked: popup.page = "Power"
                        }
                    }
                }
                NightLight {
                    id: night
                    Layout.fillWidth: true; visible: popup.page === "Night Light"
                    showing: popup.visible && (!popup.page || visible)
                    city: popup.state.clock?.zoneMismatch ? "" : popup.state.clock?.place?.name ?? ""
                }
                PowerMenu {
                    id: powerPage
                    Layout.fillWidth: true; visible: popup.page === "Power"
                    onChosen: command => { popup.close(); Quickshell.execDetached(command) }
                }
                Loader {
                    Layout.fillWidth: true
                    active: popup.visible && popup.page === "Wi-Fi"; visible: active
                    sourceComponent: Component {
                        QuickWifi {
                            device: popup.wifi
                            availableHeight: Math.min(410, (popup.screen?.height || 600) - popup.margins.top
                                - 14 - 2 * scroll.anchors.margins - header.height - contents.spacing)
                            onShowPrompt: scroll.contentY = 0
                        }
                    }
                }
                QuickBluetooth { Layout.fillWidth: true; visible: popup.visible && popup.page === "Bluetooth"; adapter: popup.adapter; onShowPrompt: scroll.contentY = 0 }
            }
        }
    }
}
