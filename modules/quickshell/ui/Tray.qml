import QtQuick
import Quickshell
import Quickshell.Services.SystemTray

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
            // These AppIndicators export a menu but omit both Activate and ItemIsMenu.
            readonly property bool primaryOpensMenu: modelData.onlyMenu
                || /^dropbox-client(?:-|$)/.test(modelData.id)
            visible: modelData.status !== Status.Passive && !["nm-applet", "blueman"].includes(modelData.id)
            minimumWidth: 19; padding: 2; iconSize: 16
            iconSource: {
                const url = modelData.icon.toString()
                // Dropbox publishes a private hicolor theme outside the system icon paths.
                const dropbox = /^image:\/\/icon\/(dropboxstatus-[\w-]+)\?path=(.+)$/.exec(url)
                if (dropbox) return "file://" + decodeURIComponent(dropbox[2]) + "/hicolor/16x16/status/" + dropbox[1] + ".png"
                return url
            }
            hint: trayMenu.visible ? "" : modelData.tooltipTitle || modelData.title || modelData.id
            buttons: (primaryOpensMenu && !modelData.menu ? Qt.NoButton : Qt.LeftButton | Qt.MiddleButton)
                | (modelData.menu ? Qt.RightButton : Qt.NoButton)
            highlight: buttons !== Qt.NoButton
            onTriggered: button => {
                if (button === Qt.MiddleButton) modelData.secondaryActivate()
                else if (button === Qt.RightButton || primaryOpensMenu)
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
