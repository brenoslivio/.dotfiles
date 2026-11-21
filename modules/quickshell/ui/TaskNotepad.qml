import QtQuick
import QtQuick.Controls.Basic as Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import "Config.js" as Config
import "Palette.js" as Ink

PanelWindow {
    id: pad
    visible: false
    anchors { top: true; left: true }
    implicitWidth: Math.min(440, (screen?.width || 456) - 16); implicitHeight: 320
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.namespace: "dotfiles-task-notepad"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: focusPulse.running ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.OnDemand
    color: "transparent"

    property var base: null
    property var changedSection: null
    property bool reviewing: false
    property bool hasDraft: false
    property bool legacy: false
    property bool loaded: false
    property string message: ""
    property var request: null
    readonly property bool dirty: editor.text !== (base ?? "")

    function openAt(button) {
        const bar = button.QsWindow.window
        screen = bar.screen
        const center = bar.margins.left + button.mapToItem(null, button.width / 2, 0).x
        margins.left = Math.max(8, Math.min(screen.width - implicitWidth - 8, center - implicitWidth / 2))
        margins.top = bar.margins.top + bar.height + 4
        if (!visible) {
            visible = true
            loaded = false
            reviewing = false
            changedSection = null
            run("open")
        }
        focusPulse.restart()
        editor.forceActiveFocus()
    }
    function run(action) {
        if (request) return
        request = {action: action, base: action === "save" && reviewing ? changedSection : base,
                   text: editor.text, cursor: editor.cursorPosition}
        worker.running = true
    }
    function save() {
        if (!loaded || request || (!dirty && !hasDraft)) return
        if (changedSection !== null && !reviewing) reviewing = true
        else run("save")
    }
    function finish() {
        if (request) return
        if (loaded && (dirty || hasDraft)) run("draft")
        else visible = false
    }
    function complete(result) {
        const action = request.action
        if (action === "open" && result.text !== undefined) {
            base = result.base
            editor.text = result.text
            editor.cursorPosition = Math.min(result.cursor, editor.length)
            hasDraft = result.draft
            legacy = result.legacy
            changedSection = result.conflict ?? null
            loaded = true
            message = result.error || (changedSection !== null ? "Note changed · draft saved locally"
                                                              : (hasDraft ? "Draft saved locally" : ""))
            editor.forceActiveFocus()
        } else if (result.error) {
            message = result.error
        } else if (action === "draft") {
            visible = false
        } else if (result.conflict !== undefined) {
            changedSection = result.conflict
            reviewing = false
            hasDraft = true
            message = "Note changed · draft saved locally"
        } else if (action === "save") {
            base = editor.text
            changedSection = null
            reviewing = false
            hasDraft = false
            message = "Saved to note"
        }
        request = null
    }
    Timer { id: focusPulse; interval: 120 }
    Process {
        id: worker
        command: Config.commands.tasks.concat("notepad")
        stdinEnabled: true
        onStarted: write(JSON.stringify(pad.request) + "\n")
        stdout: StdioCollector {
            onStreamFinished: {
                try { pad.complete(JSON.parse(text)) }
                catch (error) { pad.request = null; pad.message = "Could not read the task helper's response." }
            }
        }
    }
    Shortcut { sequence: "Escape"; enabled: pad.visible; onActivated: pad.finish() }
    Shortcut { sequences: [StandardKey.Save]; enabled: pad.visible; onActivated: pad.save() }

    component Button: BarButton {
        activeFocusOnTab: true
        border.color: activeFocus ? Ink.lavender : "transparent"
        Accessible.role: Accessible.Button; Accessible.name: label
        Accessible.onPressAction: triggered(Qt.LeftButton)
        Keys.onReturnPressed: triggered(Qt.LeftButton)
        Keys.onSpacePressed: triggered(Qt.LeftButton)
    }
    component Caption: Text {
        color: Ink.muted; font.family: "Inter"; font.pixelSize: 12
        textFormat: Text.PlainText
    }
    Rectangle {
        anchors.fill: parent; radius: 10; color: Ink.panel; border.color: Ink.inactive
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 12; spacing: 6
            RowLayout {
                Layout.fillWidth: true
                Caption {
                    text: "Tasks"; font.pixelSize: 16; font.bold: true; color: Ink.lavender
                    Layout.fillWidth: true
                }
                Button {
                    id: older
                    visible: pad.legacy; label: "Older drafts…"
                    onTriggered: legacyMenu.toggle()
                    ActionMenu { id: legacyMenu; anchor.item: older; command: Config.commands.tasks; choicesArgument: "drafts" }
                }
                Button { label: "×"; Accessible.name: "Close notepad"; onTriggered: pad.finish() }
            }
            Caption { visible: pad.reviewing; text: "Current tasks in the note"; color: Ink.lavender }
            Controls.ScrollView {
                visible: pad.reviewing; Layout.fillWidth: true; Layout.preferredHeight: 69; clip: true
                Controls.TextArea {
                    text: pad.changedSection ?? ""; textFormat: TextEdit.PlainText; readOnly: true
                    selectByMouse: true; wrapMode: TextEdit.Wrap; padding: 7
                    color: Ink.muted; font.family: "Inter"; font.pixelSize: 13
                    background: Rectangle { color: Ink.field; radius: 5 }
                }
            }
            Caption { visible: pad.reviewing; text: "Your draft · edit before saving"; color: Ink.lavender }
            Controls.ScrollView {
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 32; clip: true
                Controls.ScrollBar.horizontal.policy: Controls.ScrollBar.AlwaysOff
                background: Rectangle { radius: 6; color: Ink.field; border.color: Qt.alpha(Ink.lavender, 0.35) }
                TaskTextArea {
                    id: editor
                    readOnly: !pad.loaded || !!pad.request
                    onTextChanged: if (pad.loaded && !pad.request && pad.changedSection === null) pad.message = ""
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Caption {
                    Layout.fillWidth: true; wrapMode: Text.Wrap
                    text: pad.message || (pad.dirty ? "Unsaved changes" : "")
                }
                Button {
                    label: pad.changedSection === null ? "Save" : (pad.reviewing ? "Save reviewed draft" : "Review changes")
                    enabled: pad.loaded && !pad.request && (pad.dirty || pad.hasDraft)
                    labelColor: Ink.lavender; opacity: enabled ? 1 : 0.5
                    onTriggered: pad.save()
                }
            }
        }
    }
}
