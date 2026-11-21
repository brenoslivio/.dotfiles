import QtQuick
import Quickshell.Io

Process {
    id: feed
    signal line(string data)
    stdout: SplitParser { onRead: data => feed.line(data) }
    running: true
    onExited: retry.restart()
    property Timer retry: Timer {
        interval: 2000
        onTriggered: feed.running = true
    }
}
