import QtQuick
import Quickshell
import Quickshell.Io

ShellRoot {
    NotificationHub {
        id: hub
        barVisible: true
        focusSession: null
        now: Date.now() / 1000
    }
    IpcHandler {
        target: "fixture"
        function counts(): string {
            return [hub.history.length, hub.unreadCount, hub.banners.length].join(",")
        }
        function latestText(): string {
            const e = hub.history[0]
            return JSON.stringify([e.website, e.title, e.body])
        }
        function focus(status: string, cutoff: int): void {
            hub.now = Date.now() / 1000
            hub.focusSession = {status: status, cutoff: cutoff || null}
        }
        function toggleDnd(): void { hub.toggleManual() }
        function toggleCenter(): void { hub.toggleCenter(Quickshell.screens[0]) }
        function hideBar(): void { hub.barVisible = false }
        function invokeFirst(): void { hub.history[0].notice.actions[0].invoke() }
        function openLatest(): void { hub.history[0].open() }
        function clear(): void { hub.clearHistory() }
    }
}
