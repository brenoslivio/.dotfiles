import QtQuick
import QtQuick.Layouts
import "PowerActions.js" as Power

GridLayout {
    id: menu
    columns: 2
    columnSpacing: 7; rowSpacing: 7
    signal chosen(var command)

    function handleKey(event) {
        if (event.modifiers !== Qt.NoModifier || event.isAutoRepeat) return
        const index = Power.actions.findIndex(action => action.key === event.text.toLowerCase())
        if (index >= 0) {
            event.accepted = true
            chosen(Power.actions[index].command)
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
            onClicked: menu.chosen(modelData.command)
        }
    }
}
