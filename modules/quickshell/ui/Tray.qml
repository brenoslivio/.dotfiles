import QtQuick
import Quickshell
import Quickshell.Services.SystemTray
import "TrayIcons.js" as TrayIcons

Row {
    spacing: 2
    Component {
        id: submenu
        TrayMenu {
            required property var modelData
            handle: modelData.entry
            title: modelData.entry.text
            enabled: modelData.entry.enabled
            entryIcon: menuIcon(modelData.entry.icon)
            submenuFactory: submenu
        }
    }
    Repeater {
        model: SystemTray.items
        BarButton {
            id: entry
            required property var modelData
            visible: modelData.status !== Status.Passive
            minimumWidth: 19; padding: 2; iconSize: 16
            iconSource: {
                const url = modelData.icon.toString()
                if (modelData.id === "nm-applet" || modelData.id === "blueman") {
                    const name = /^image:\/\/icon\/([^/?#]+)/.exec(url)
                    const file = name && name[1] + ".svg"
                    if (TrayIcons.names.includes(file)) return Qt.resolvedUrl("tray/" + file)
                }
                // Dropbox publishes a private hicolor theme outside the system icon paths.
                const dropbox = /^image:\/\/icon\/(dropboxstatus-[\w-]+)\?path=(.+)$/.exec(url)
                if (dropbox) return "file://" + decodeURIComponent(dropbox[2]) + "/hicolor/16x16/status/" + dropbox[1] + ".png"
                return url
            }
            hint: trayMenu.visible ? "" : modelData.tooltipTitle || modelData.title || modelData.id
            buttons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
            onTriggered: button => {
                if (button === Qt.MiddleButton) modelData.secondaryActivate()
                else if ((button === Qt.RightButton || modelData.onlyMenu) && modelData.menu)
                    trayMenu.popup(entry, 0, entry.height + 2)
                else if (button === Qt.LeftButton) modelData.activate()
            }
            onScrolled: delta => modelData.scroll(delta, false)
            TrayMenu {
                id: trayMenu
                handle: entry.modelData.menu
                submenuFactory: submenu
            }
        }
    }
}
