import QtQuick
import QtCore
import Quickshell
import Quickshell.Hyprland
import Quickshell.Services.Notifications

Scope {
    id: controller
    required property var focusSession
    required property double now
    required property bool barVisible
    property var entries: []
    property var centerScreen: null
    readonly property var history: entries.filter(e => !e.isTransient)
    readonly property int unreadCount: history.filter(e => e.unread).length
    readonly property var banners: entries.filter(e => e.banner && (!quiet || e.criticalBattery))
    readonly property bool focusing: focusAt(now)
    property bool manual: false
    readonly property bool quiet: manual || focusing
    readonly property string description: (unreadCount ? unreadCount + " unread" : "No unread notifications")
        + (manual ? " · Do Not Disturb on" : "") + (focusing ? " · Silenced during focus" : "")
    readonly property var activeScreen: Quickshell.screens.find(s => s.name === Hyprland.focusedMonitor?.name)
        || Quickshell.screens[0] || null

    Settings {
        id: preferences
        location: "file://" + Quickshell.statePath("notifications.ini")
        Component.onCompleted: controller.manual = String(value("manualDnd", false)) === "true"
    }
    function focusAt(seconds) {
        return focusSession?.status === "running" && (focusSession.cutoff == null || seconds < focusSession.cutoff)
    }
    function toggleManual() {
        manual = !manual
        preferences.setValue("manualDnd", manual)
        preferences.sync()
    }
    function toggleCenter(output) { centerScreen = centerScreen === output ? null : output }
    function remove(entry) {
        entries = entries.filter(other => other !== entry)
    }
    function clearHistory() { for (const entry of history.slice()) entry.dismiss() }

    onCenterScreenChanged: {
        if (centerScreen) for (const e of entries) { e.unread = false; e.hideBanner() }
    }
    onQuietChanged: {
        if (quiet) for (const e of entries) if (!e.criticalBattery) e.hideBanner()
    }
    onBarVisibleChanged: if (!barVisible) centerScreen = null
    Connections {
        target: Quickshell
        function onScreensChanged() {
            if (!Quickshell.screens.includes(controller.centerScreen)) controller.centerScreen = null
        }
    }

    Component { id: entryFactory; NotificationEntry {} }
    NotificationServer {
        keepOnReload: true
        actionsSupported: true
        bodySupported: true
        imageSupported: true
        persistenceSupported: true
        onNotification: n => {
            n.tracked = true
            const tag = n.hints["x-canonical-private-synchronous"]
            if (tag && n.transient) {
                const old = controller.entries.find(e => e.isTransient && e.notice?.appName === n.appName
                    && e.notice.hints["x-canonical-private-synchronous"] === tag)
                if (old) old.dismiss()
            }
            // A removed row may still be rendered during the next layout pass.
            // Let QML release the entry once the model and its delegates drop it.
            const e = entryFactory.createObject(null, { hub: controller, notice: n })
            e.present(n.lastGeneration)
        }
    }
    NotificationWindow { hub: controller; centerMode: true }
    NotificationWindow { hub: controller; centerMode: false }
}
