import QtQuick
import Quickshell
import Quickshell.Services.Notifications

Scope {
    id: entry
    required property var hub
    required property Notification notice
    property bool banner: false
    property bool unread: false
    property bool isTransient: false
    property bool criticalBattery: false
    property string app: ""
    property string website: ""
    property string desktopId: ""
    readonly property var desktopApp: desktopId && DesktopEntries.applications.values.length
        ? DesktopEntries.byId(desktopId) : null
    readonly property var actions: notice?.actions ?? []
    readonly property var openAction: actions.find(a => a.identifier === "default")
        ?? actions.find(a => ["open", "open-message"].includes(a.identifier))
    readonly property bool canOpen: !!openAction || !!desktopApp
    property string title: ""
    property string body: ""
    property string icon: ""
    property date received
    property bool removed: false

    function iconUrl(name) {
        if (!name) return ""
        if (name.startsWith("/")) return "file://" + name
        if (name.includes("://")) return name
        if (["battery-caution-symbolic", "battery-low-symbolic", "appointment-soon-symbolic"].includes(name))
            return Qt.resolvedUrl(name + ".svg").toString()
        return Quickshell.iconPath(name, true)
    }
    function hideBanner() {
        banner = false
        if (isTransient && notice) notice.expire()
    }
    function present(fromReload = false) {
        if (!notice || removed) return
        const n = notice
        app = n.appName || "Notification"
        desktopId = n.desktopEntry.replace(/\.desktop$/, "")
        title = n.summary
        body = n.body.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"')
            .replace(/&#x27;|&apos;/g, "'").replace(/&amp;/g, "&")
        // Brave prefixes web messages with the origin and an empty line.
        const brave = app === "Brave" || desktopId === "brave-browser"
        const prefix = brave && /^((?:https?:\/\/)?(?:localhost|[\w-]+(?:\.[\w-]+)+|\[[\da-f:]+\])(?::\d+)?)\r?\n\r?\n/i.exec(body)
        website = prefix ? prefix[1] : ""
        if (prefix) body = body.slice(prefix[0].length)
        const imagePath = n.hints["image-path"] || n.hints.image_path
        icon = iconUrl(n.appIcon || desktopApp?.icon) || (imagePath ? iconUrl(imagePath) : n.image)
            || (n.hints.category?.startsWith("email") ? iconUrl("mail-unread") : "")
        received = new Date()
        isTransient = n.transient
        criticalBattery = n.urgency === NotificationUrgency.Critical && n.appName === "Power" && n.hints.category === "device"
        unread = !isTransient && !hub.centerScreen
        banner = !fromReload && !hub.centerScreen
            && (criticalBattery || (!hub.manual && !hub.focusAt(Date.now() / 1000)))
        hub.entries = [entry, ...hub.entries.filter(e => e !== entry)]
        timeout.stop()
        if (isTransient && !banner) {
            // NotificationServer finishes registering new IDs after this callback.
            Qt.callLater(entry.hideBanner)
            return
        }
        if (n.expireTimeout > 0) timeout.interval = n.expireTimeout
        else if (n.expireTimeout < 0 && n.urgency !== NotificationUrgency.Critical) timeout.interval = isTransient ? 1600 : 6000
        else return
        timeout.start()
    }
    function dismiss() {
        if (notice) notice.dismiss()
        else discard()
    }
    function open() {
        if (!canOpen) return
        unread = false
        banner = false
        hub.centerScreen = null
        if (openAction) openAction.invoke()
        else desktopApp.execute()
    }
    function discard() {
        if (removed) return
        removed = true
        hub.remove(entry)
    }
    Timer {
        id: timeout
        onTriggered: {
            entry.banner = false
            if (entry.notice && (entry.isTransient || entry.notice.expireTimeout > 0)) entry.notice.expire()
        }
    }
    Connections {
        target: entry.notice
        function onClosed(reason) {
            timeout.stop()
            entry.banner = false
            entry.notice = null
            if (reason !== NotificationCloseReason.Expired || entry.isTransient) entry.discard()
        }
        // Quickshell updates the existing object for a replacement notification.
        function onSummaryChanged() { Qt.callLater(entry.present) }
        function onBodyChanged() { Qt.callLater(entry.present) }
        function onHintsChanged() { Qt.callLater(entry.present) }
        function onExpireTimeoutChanged() { Qt.callLater(entry.present) }
        function onUrgencyChanged() { Qt.callLater(entry.present) }
        function onActionsChanged() { Qt.callLater(entry.present) }
    }
}
