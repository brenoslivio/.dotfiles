import QtQuick
import Quickshell
import Quickshell.Services.SystemTray

Row {
    spacing: 2
    Repeater {
        model: SystemTray.items
        BarButton {
            id: entry
            required property var modelData
            visible: modelData.status !== Status.Passive
            minimumWidth: 19; padding: 2; iconSize: 16
            iconSource: {
                const url = modelData.icon.toString()
                // Dropbox publishes a private hicolor theme outside the system icon paths.
                const dropbox = /^image:\/\/icon\/(dropboxstatus-[\w-]+)\?path=(.+)$/.exec(url)
                if (dropbox) return "file://" + decodeURIComponent(dropbox[2]) + "/hicolor/16x16/status/" + dropbox[1] + ".png"
                return url
            }
            hint: nativeMenu.visible ? "" : modelData.tooltipTitle || modelData.title || modelData.id
            buttons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
            onTriggered: button => {
                if (button === Qt.MiddleButton) modelData.secondaryActivate()
                else if ((button === Qt.RightButton || modelData.onlyMenu) && modelData.menu) nativeMenu.open()
                else if (button === Qt.LeftButton) modelData.activate()
            }
            onScrolled: delta => modelData.scroll(delta, false)
            QsMenuAnchor {
                id: nativeMenu
                menu: entry.modelData.menu
                anchor.item: entry; anchor.edges: Edges.Bottom; anchor.gravity: Edges.Bottom
            }
        }
    }
}
