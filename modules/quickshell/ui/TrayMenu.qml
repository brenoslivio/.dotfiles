import QtQuick
import QtCore
import QtQuick.Controls.Basic as Controls
import QtQml.Models
import Quickshell
import "Palette.js" as Ink

Controls.Menu {
    id: trayMenu
    required property QsMenuHandle handle
    required property Component submenuFactory
    property url entryIcon
    property bool requested: false
    popupType: Controls.Popup.Window
    cascade: true
    padding: 6
    margins: 4
    overlap: 0
    font.family: "Inter"
    font.pixelSize: 14
    FontMetrics { id: metrics; font: trayMenu.font }
    readonly property var entries: opener.children?.values || []
    implicitWidth: Math.min(Screen.width - 8, 440, Math.max(160, ...entries.map(entry =>
        Math.ceil(metrics.advanceWidth(entry.text)) + 76)))
    height: Math.min(implicitHeight, Screen.height - 2 * margins)

    function menuIcon(source: string): string {
        const named = /^image:\/\/icon\/([^/?#]+)$/.exec(source)
        if (!named) return source
        const name = named[1]
        const base = "icons/Papirus-Dark/16x16/" + (name.endsWith("-symbolic") ? "symbolic/" : "")
        for (const group of ["actions", "status", "devices", "apps", "mimetypes", "places", "categories", "emblems", "panel"]) {
            const path = StandardPaths.locate(StandardPaths.GenericDataLocation, base + group + "/" + name + ".svg")
            if (path.toString()) return path.toString()
        }
        return Quickshell.iconPath(name, true)
    }

    background: Rectangle {
        implicitWidth: 150
        color: Ink.panel
        radius: 10
        border.color: Qt.alpha(Ink.lavender, 0.6)
    }

    component TrayItem: Controls.MenuItem {
        id: row
        property int mark: QsMenuButtonType.None
        property int stateValue: Qt.Unchecked
        implicitHeight: 32
        property string imageSource: subMenu?.entryIcon.toString() || ""
        leftPadding: imageSource || checkable ? 10 : 32
        rightPadding: subMenu ? 26 : 10
        spacing: 6
        readonly property color ink: enabled ? Ink.text : Ink.inactive
        palette.windowText: ink
        icon.source: imageSource
        icon.width: 16; icon.height: 16
        icon.color: /-symbolic(?:\.svg)?$/.test(imageSource) ? ink : "transparent"
        indicator: Item {
            x: 10; anchors.verticalCenter: parent.verticalCenter
            width: 16; height: 16
            Text {
                anchors.centerIn: parent; color: row.ink
                visible: row.mark !== QsMenuButtonType.None && row.stateValue !== Qt.Unchecked
                text: row.stateValue === Qt.PartiallyChecked ? "−" : row.mark === QsMenuButtonType.RadioButton ? "●" : "✓"
            }
        }
        arrow: Text {
            anchors.right: parent.right; anchors.rightMargin: 10
            anchors.verticalCenter: parent.verticalCenter
            text: "▸"; color: row.ink; visible: !!row.subMenu
        }
        background: Rectangle {
            color: row.highlighted && row.enabled ? Ink.selection : "transparent"
            radius: 6
        }
    }

    delegate: TrayItem {}
    QsMenuOpener { id: opener; menu: trayMenu.requested ? trayMenu.handle : null }
    onAboutToShow: requested = true
    onClosed: requested = false
    onHandleChanged: if (!handle && visible) close()

    Instantiator {
        model: trayMenu.entries.map(entry => ({
            kind: entry.isSeparator ? "separator" : entry.hasChildren ? "submenu" : "item",
            entry: entry
        }))
        delegate: DelegateChooser {
            role: "kind"
            DelegateChoice {
                roleValue: "submenu"
                delegate: trayMenu.submenuFactory
            }
            DelegateChoice {
                roleValue: "separator"
                Controls.MenuSeparator {
                    leftPadding: 8; rightPadding: 8
                    topPadding: 4; bottomPadding: 4
                    contentItem: Rectangle { implicitHeight: 1; color: Qt.alpha(Ink.lavender, 0.22) }
                }
            }
            DelegateChoice {
                TrayItem {
                    required property var modelData
                    readonly property var entry: modelData.entry
                    text: entry.text
                    enabled: entry.enabled
                    imageSource: trayMenu.menuIcon(entry.icon)
                    mark: entry.buttonType
                    stateValue: entry.checkState
                    checkable: mark !== QsMenuButtonType.None
                    checked: entry.checkState !== Qt.Unchecked
                    onTriggered: entry.triggered()
                }
            }
        }
        onObjectAdded: (index, object) => {
            if (object instanceof Controls.Menu) trayMenu.insertMenu(index, object)
            else trayMenu.insertItem(index, object)
        }
        onObjectRemoved: (index, object) => {
            if (object instanceof Controls.Menu) trayMenu.takeMenu(index)
            else trayMenu.takeItem(index)
        }
    }
}
