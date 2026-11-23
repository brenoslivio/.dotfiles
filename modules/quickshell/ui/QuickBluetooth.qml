import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic as Controls
import Quickshell.Io
import Quickshell.Bluetooth
import "Palette.js" as Ink
import "Config.js" as Config

Column {
    id: page
    required property var adapter
    spacing: 6
    signal showPrompt()
    property var scanAdapter: null
    property string message: ""
    property string prompt: ""
    property string pairingName: ""
    readonly property var devices: (adapter?.devices.values ?? [])
        .filter(d => d.paired || d.connected || !!scanAdapter)
        .sort((a,b) => Number(b.connected) - Number(a.connected) || Number(b.paired) - Number(a.paired)
            || a.name.localeCompare(b.name))
    function stopScan() {
        scanTimer.stop()
        if (scanAdapter) scanAdapter.discovering = false
        scanAdapter = null
    }
    function scan() {
        if (scanAdapter) { stopScan(); return }
        message = ""
        scanAdapter = adapter
        adapter.discovering = true
        scanTimer.start()
    }
    function cancel() {
        if (pairer.running) {
            pairer.write("null\n")
            page.message = "Pairing canceled"
        }
        page.prompt = ""
    }
    function answer(value) {
        pairer.write(JSON.stringify(value) + "\n")
        pin.clear()
        page.prompt = "progress"
    }
    onVisibleChanged: if (!visible) { stopScan(); cancel(); message = "" }
    onAdapterChanged: if (scanAdapter && scanAdapter !== adapter) stopScan()
    Connections {
        target: page.adapter
        function onEnabledChanged() {
            if (!page.adapter?.enabled) { page.stopScan(); page.cancel() }
        }
    }
    Timer { id: scanTimer; interval: 20000; onTriggered: page.stopScan() }
    Process {
        id: pairer
        stdinEnabled: true
        stdout: SplitParser {
            onRead: data => {
                const result = JSON.parse(data)
                page.prompt = result.kind
                page.message = ["confirm", "input", "display"].includes(result.kind)
                    ? page.pairingName + " · " + result.message : result.message
                page.showPrompt()
                if (result.kind === "input") pin.forceActiveFocus()
            }
        }
        onExited: code => {
            if (code && page.prompt !== "error") page.message = "Pairing stopped. Try again."
            page.prompt = ""; pin.clear()
        }
    }
    Process {
        id: connection
        property string operation
        onExited: code => page.message = code === 0 ? "" : "Couldn’t " + operation + ". Check the device and try again."
    }
    function choose(d) {
        page.message = ""
        if (d.paired || d.connected) {
            connection.operation = d.connected ? "disconnect" : "connect"
            connection.command = Config.commands.bluetoothDevice.concat([d.dbusPath, "org.bluez.Device1", d.connected ? "Disconnect" : "Connect"])
            page.message = d.connected ? "Disconnecting…" : "Connecting…"
            connection.running = true
        } else {
            pairingName = d.name
            prompt = "progress"
            message = "Pairing with " + d.name + "…"
            pairer.command = Config.commands.bluetoothPair.concat(d.dbusPath)
            page.showPrompt()
            pairer.running = true
        }
    }
    QuickChoice {
        width: parent.width; visible: !!page.adapter?.enabled && !pairer.running
        text: page.scanAdapter ? "Stop searching" : "Find devices"; trailing: page.scanAdapter ? "×" : "+"
        onClicked: page.scan()
    }
    Text {
        width: parent.width; visible: !!text; wrapMode: Text.Wrap; textFormat: Text.PlainText
        text: page.message || (!page.adapter?.enabled ? "Bluetooth is off"
            : !page.devices.length ? (page.scanAdapter ? "Looking for nearby devices…" : "No paired devices") : "")
        color: Ink.muted
    }
    RowLayout {
        width: parent.width; visible: pairer.running
        Controls.TextField {
            id: pin
            Layout.fillWidth: true; visible: page.prompt === "input"
            placeholderText: "PIN or passkey"; echoMode: TextInput.Password
            Accessible.name: placeholderText; color: Ink.text
            background: Rectangle { color: Ink.field; radius: 6; border.color: Ink.lavender }
            onAccepted: if (text) page.answer(text)
        }
        TaskButton {
            visible: ["input", "confirm"].includes(page.prompt)
            label: page.prompt === "confirm" ? "Confirm" : "Submit"
            enabled: page.prompt === "confirm" || !!pin.text
            onTriggered: page.answer(page.prompt === "input" ? pin.text : true)
        }
        TaskButton { label: "Cancel"; onTriggered: page.cancel() }
    }
    Repeater {
        model: page.adapter?.enabled ? page.devices : []
        QuickChoice {
            required property var modelData
            width: page.width; text: modelData.name || modelData.address
            current: modelData.connected; enabled: !pairer.running && !connection.running && !modelData.blocked
            detail: (current ? "Connected" : modelData.paired ? "Paired" : "Nearby")
                + (modelData.batteryAvailable ? " · " + Math.round(modelData.battery * 100) + "%" : "")
            trailing: current ? "Disconnect" : modelData.paired ? "Connect" : "Pair"
            onClicked: page.choose(modelData)
        }
    }
}
