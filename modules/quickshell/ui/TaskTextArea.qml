import QtQuick
import QtQuick.Controls.Basic as Controls
import "Palette.js" as Ink

Controls.TextArea {
    id: editor
    textFormat: TextEdit.PlainText; wrapMode: TextEdit.Wrap; selectByMouse: true
    padding: 10; color: Ink.text; selectionColor: Ink.selection; selectedTextColor: Ink.text
    font.family: "Inter"; font.pixelSize: 14
    placeholderText: "- Project"; placeholderTextColor: Ink.inactive
    background: null

    function indentLines(outdent) {
        const start = selectionStart, end = selectionEnd
        const first = text.slice(0, start).lastIndexOf("\n") + 1
        const last = end > start && text[end - 1] === "\n" ? end - 1 : text.indexOf("\n", end)
        const stop = last === -1 ? length : last
        const original = text.slice(first, stop)
        const indents = text.match(/^[ \t]+(?=- )/gm) || []
        const indent = indents.length ? indents.reduce((a, b) => a.length <= b.length ? a : b) : "  "
        const lines = original.split("\n")
        const edited = lines.map(line => {
            if (!outdent) return indent + line
            return line.startsWith(indent) ? line.slice(indent.length) : line.replace(/^[ \t]/, "")
        })
        const replacement = edited.join("\n")
        if (replacement === original) return
        remove(first, stop)
        insert(first, replacement)
        if (end > start) select(first, first + replacement.length)
        else cursorPosition = Math.max(first, start + edited[0].length - lines[0].length)
    }

    Keys.onPressed: event => {
        if (readOnly || (event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier))) return
        if (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) {
            indentLines(event.key === Qt.Key_Backtab || !!(event.modifiers & Qt.ShiftModifier))
            event.accepted = true
        } else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                   && event.modifiers === Qt.NoModifier && selectionStart === selectionEnd) {
            const start = text.slice(0, cursorPosition).lastIndexOf("\n") + 1
            const prefix = text.slice(start, cursorPosition).match(/^([ \t]*- [ \t]*)/)
            if (!prefix) return
            if (text.slice(start, cursorPosition) === prefix[0] && (cursorPosition === length || text[cursorPosition] === "\n"))
                remove(start, cursorPosition)
            else insert(cursorPosition, "\n" + prefix[0])
            event.accepted = true
        }
    }
}
