import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic as Controls
import Quickshell
import Quickshell.Networking
import "Palette.js" as Ink

Column {
    id: page
    required property var device
    required property real availableHeight
    spacing: 6
    signal showPrompt()
    onMessageChanged: if (message) showPrompt()
    property var selectedNetwork: null
    property var attempted: null
    property string message: ""
    property var networks: []
    function refreshNetworks() {
        networks = Networking.wifiEnabled ? (device?.networks.values ?? []).filter(n => n?.name)
            .sort((a,b) => Number(b.connected) - Number(a.connected)
                || b.signalStrength - a.signalStrength || a.name.localeCompare(b.name)) : []
    }
    // NetworkManager can publish dozens of access points in the same scan.
    Connections {
        target: page.device?.networks ?? null
        function onValuesChanged() { Qt.callLater(page.refreshNetworks) }
    }
    onDeviceChanged: Qt.callLater(refreshNetworks)
    Timer {
        interval: 2500; running: page.visible && Networking.wifiEnabled; repeat: true; triggeredOnStart: true
        onTriggered: Qt.callLater(page.refreshNetworks)
    }
    Binding {
        target: page.device; property: "scannerEnabled"; value: true
        when: !!page.device && page.visible && Networking.wifiEnabled
    }
    function usesPassword(n) {
        return [WifiSecurityType.WpaPsk, WifiSecurityType.Wpa2Psk, WifiSecurityType.Sae].includes(n.security)
    }
    function choose(n) {
        message = ""
        selectedNetwork = null
        timeout.stop()
        if (n.connected) { attempted = null; n.disconnect(); return }
        attempted = n
        if (n.known || [WifiSecurityType.Open, WifiSecurityType.Owe].includes(n.security)) {
            connecting()
            n.connect()
        }
        else if (usesPassword(n)) selectedNetwork = n
        else message = "Set up this network’s authentication profile in NetworkManager first."
    }
    onSelectedNetworkChanged: {
        password.clear()
        if (selectedNetwork) { showPrompt(); password.forceActiveFocus() }
    }
    Connections {
        target: page.attempted
        function onConnectionFailed(reason) {
            timeout.stop()
            page.message = reason === ConnectionFailReason.NoSecrets || reason === ConnectionFailReason.WifiAuthTimeout
                ? "Authentication failed. Check the Wi-Fi password and try again."
                : "Couldn’t connect. Check the network and try again."
            if (page.attempted && page.usesPassword(page.attempted)) page.selectedNetwork = page.attempted
        }
        function onConnectedChanged() {
            if (page.attempted?.connected) {
                timeout.stop()
                page.message = ""
                page.selectedNetwork = null
            }
        }
    }
    function connecting() {
        message = "Connecting to " + attempted.name + "…"
        timeout.restart()
    }
    Timer {
        id: timeout
        interval: 45000
        onTriggered: page.message = "Connection timed out. Select the network to retry."
    }
    Connections {
        target: Networking
        function onWifiEnabledChanged() {
            Qt.callLater(page.refreshNetworks)
            if (!Networking.wifiEnabled) {
                timeout.stop()
                page.selectedNetwork = null; page.attempted = null; page.message = ""
            }
        }
    }
    function submit() {
        if (!selectedNetwork || !password.text) return
        const network = selectedNetwork
        const secret = password.text
        selectedNetwork = null
        connecting()
        network.connectWithPsk(secret)
    }
    Text {
        id: status
        width: parent.width; visible: !!text
        text: page.message || (!page.device ? "No Wi-Fi adapter" : !Networking.wifiEnabled ? "Wi-Fi is off"
            : !page.networks.length ? "Looking for networks…" : "")
        color: Ink.muted; wrapMode: Text.Wrap; textFormat: Text.PlainText
    }
    ColumnLayout {
        id: prompt
        visible: !!page.selectedNetwork; width: parent.width
        Text {
            Layout.fillWidth: true; elide: Text.ElideRight; textFormat: Text.PlainText
            text: "Password for " + (page.selectedNetwork?.name || ""); color: Ink.text
        }
        RowLayout {
            Layout.fillWidth: true
            Controls.TextField {
                id: password
                Layout.fillWidth: true; echoMode: TextInput.Password
                Accessible.name: "Wi-Fi password"; color: Ink.text
                background: Rectangle { color: Ink.field; radius: 6; border.color: Ink.lavender }
                onAccepted: page.submit()
            }
            TaskButton { label: "Connect"; enabled: !!password.text; onTriggered: page.submit() }
            TaskButton { label: "Cancel"; onTriggered: page.selectedNetwork = null }
        }
    }
    ListView {
        id: list
        width: page.width
        height: Math.min(contentHeight, Math.max(53, page.availableHeight
            - (status.visible ? status.height + page.spacing : 0) - (prompt.visible ? prompt.height + page.spacing : 0)))
        clip: true; reuseItems: true; spacing: 6; boundsBehavior: Flickable.StopAtBounds
        model: ScriptModel { values: page.networks }
        Controls.ScrollBar.vertical: Controls.ScrollBar { id: scrollbar }
        delegate: QuickChoice {
            required property var modelData
            width: list.width - (list.contentHeight > list.height ? scrollbar.implicitWidth : 0)
            text: modelData.name
            current: modelData.connected
            detail: modelData.stateChanging ? ConnectionState.toString(modelData.state)
                : current ? "Connected · Click to disconnect" : modelData.known ? "Saved network"
                : [WifiSecurityType.Open, WifiSecurityType.Owe].includes(modelData.security) ? "Password-free" : "Secured"
            trailing: Math.round(modelData.signalStrength * 100) + "%"
            enabled: !modelData.stateChanging
            onClicked: page.choose(modelData)
        }
    }
}
