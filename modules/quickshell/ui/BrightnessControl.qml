import QtQuick
import Quickshell
import Quickshell.Io
import "Config.js" as Config

Scope {
    id: control
    property int pending: -1
    function setLevel(percent, finalValue) {
        pending = percent
        if (finalValue) cooldown.stop()
        flush()
    }
    function flush() {
        if (pending < 0 || writer.running || cooldown.running) return
        writer.command = Config.commands.brightness.concat(pending + "%")
        pending = -1
        cooldown.start()
        writer.running = true
    }
    Timer { id: cooldown; interval: 50; onTriggered: control.flush() }
    Process { id: writer; onExited: Qt.callLater(control.flush) }
}
