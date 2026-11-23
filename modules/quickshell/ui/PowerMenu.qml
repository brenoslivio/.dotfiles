import QtQuick
import QtQuick.Controls.Basic as Controls
import QtQuick.Layouts
import "Palette.js" as Ink
import "PowerActions.js" as Power

GridLayout {
    id: menu
    columns: 2
    columnSpacing: 7; rowSpacing: 7
    signal chosen(var command)
    readonly property bool confirming: confirmation.visible

    function request(action) {
        if (!visible || confirming) return
        confirmation.action = action
        confirmation.open()
    }
    onVisibleChanged: if (!visible && confirming) confirmation.close()

    function handleKey(event) {
        if (confirming || event.modifiers !== Qt.NoModifier || event.isAutoRepeat) return
        const index = Power.actions.findIndex(action => action.key === event.text.toLowerCase())
        if (index >= 0) {
            event.accepted = true
            request(Power.actions[index])
            return
        }
        const steps = { [Qt.Key_Right]: 1, [Qt.Key_Left]: -1, [Qt.Key_Up]: -columns, [Qt.Key_Down]: columns }
        const step = steps[event.key]
        if (step === undefined) return
        const current = Power.actions.findIndex((_, i) => tiles.itemAt(i)?.activeFocus)
        const next = current < 0 ? (step > 0 ? 0 : tiles.count - 1) : (current + step + tiles.count) % tiles.count
        tiles.itemAt(next).forceActiveFocus()
        event.accepted = true
    }
    Repeater {
        id: tiles
        model: Power.actions
        QuickChoice {
            required property var modelData
            Layout.fillWidth: true; Layout.preferredWidth: 1
            text: modelData.label
            symbol: modelData.symbol
            onClicked: menu.request(modelData)
        }
    }
    Controls.Popup {
        id: confirmation
        property var action: null
        parent: menu.Controls.Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(320, (parent?.width ?? 344) - 24)
        padding: 14; modal: true; focus: true
        closePolicy: Controls.Popup.CloseOnEscape | Controls.Popup.CloseOnPressOutside
        onOpened: cancelButton.forceActiveFocus()
        onAboutToHide: action = null
        Controls.Overlay.modal: Rectangle { color: Qt.alpha(Ink.panel, 0.72) }
        background: Rectangle { color: Ink.panel; radius: 11; border.color: Ink.lavender }
        contentItem: ColumnLayout {
            spacing: 12
            RowLayout {
                SettingsIcon { symbol: confirmation.action?.symbol ?? ""; color: Ink.lavender }
                Text {
                    Layout.fillWidth: true
                    text: confirmation.action ? confirmation.action.label + "?" : ""
                    color: Ink.text; font.family: "Inter"; font.pixelSize: 17; font.weight: Font.DemiBold
                }
            }
            RowLayout {
                QuickChoice {
                    id: cancelButton
                    Layout.fillWidth: true; Layout.preferredWidth: 1
                    text: "Cancel"
                    onClicked: confirmation.close()
                    Keys.onReturnPressed: event => { if (!event.isAutoRepeat) confirmation.close() }
                }
                QuickChoice {
                    id: confirmButton
                    Layout.fillWidth: true; Layout.preferredWidth: 1
                    text: confirmation.action?.label ?? ""; current: true
                    onClicked: {
                        if (!confirmation.visible || !confirmation.action || !menu.visible) return
                        const command = confirmation.action.command
                        confirmation.close()
                        menu.chosen(command)
                    }
                    Keys.onReturnPressed: event => { if (!event.isAutoRepeat) confirmButton.clicked() }
                }
            }
        }
    }
}
