import QtQuick
import QtQuick.Controls.Basic as Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import "Palette.js" as Ink

PanelWindow {
    id: popup
    required property PanelWindow bar
    required property var state
    required property Item button
    property string ranking: "Memory"
    function close() { state.controlPopup = null }

    screen: bar.screen
    visible: !!bar.screen && state.controlPopup === popup
    anchors { top: true; left: true }
    margins {
        top: bar.margins.top + bar.height + 5
        left: Math.max(bar.margins.left, Math.min(bar.margins.left + button.parent.x + button.x,
            (screen?.width || 450) - implicitWidth - bar.margins.right))
    }
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    WlrLayershell.namespace: "dotfiles-resources"
    implicitWidth: Math.min(456, (screen?.width || 480) - 28)
    implicitHeight: Math.min(690, (screen?.height || 600) - margins.top - 14)
    color: "transparent"
    onVisibleChanged: if (visible) {
        ranking = "Memory"
        programs.reset()
        scroll.contentY = 0
        frame.forceActiveFocus()
    }

    component Caption: Text {
        color: Ink.muted; textFormat: Text.PlainText
        font.family: "Inter"; font.pixelSize: 12
    }
    component MetricCard: Rectangle {
        id: metric
        required property string title
        required property var sample
        Layout.fillWidth: true; Layout.preferredWidth: 1; implicitHeight: 97
        color: Ink.field; radius: 9
        Caption { x: 10; y: 8; text: metric.title }
        Caption {
            x: 10; y: 25; text: (metric.sample.text ?? "–") + "%"
            color: Ink.text; font.weight: Font.DemiBold; font.pixelSize: 22
        }
        Canvas {
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 10 }
            height: 28
            property var history: metric.sample.history ?? []
            onHistoryChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                ctx.fillStyle = Ink.inactive
                ctx.globalAlpha = 0.35
                ctx.fillRect(0, height - 1, width, 1)
                ctx.globalAlpha = 1
                ctx.beginPath()
                history.forEach(([age, percent], i) => {
                    const x = (1 - age / 60) * (width - 2) + 1
                    const y = (1 - percent / 100) * (height - 3) + 1
                    if (i === 0) ctx.moveTo(x, y)
                    else ctx.lineTo(x, y)
                })
                ctx.lineWidth = 2
                ctx.strokeStyle = Ink.lavender
                ctx.stroke()
            }
        }
    }
    Rectangle {
        id: frame
        anchors.fill: parent; radius: 13; color: Ink.panel; border.color: Qt.alpha(Ink.lavender, 0.48)
        focus: true; Keys.onEscapePressed: popup.close()
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 16; spacing: 10
            Flickable {
                id: scroll
                Layout.fillWidth: true; Layout.preferredHeight: Math.min(contents.implicitHeight, frame.height * 0.47)
                contentWidth: width; contentHeight: contents.implicitHeight
                clip: true; boundsBehavior: Flickable.StopAtBounds
                Controls.ScrollBar.vertical: Controls.ScrollBar {}
                ColumnLayout {
                    id: contents
                    width: scroll.width; spacing: 8
                    RowLayout {
                        Layout.fillWidth: true
                        Caption { Layout.fillWidth: true; text: "Resources"; color: Ink.text; font.pixelSize: 19; font.weight: Font.DemiBold }
                        Caption { text: "Last 60 seconds" }
                        TaskButton { label: "×"; Accessible.name: "Close resources"; onTriggered: popup.close() }
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 8
                        MetricCard { title: "Memory"; sample: popup.state.memory }
                        MetricCard { title: "CPU"; sample: popup.state.cpu }
                    }
                    Caption {
                        Layout.fillWidth: true; wrapMode: Text.Wrap
                        text: popup.state.memory.total ? popup.state.memory.used + " of " + popup.state.memory.total +
                            " used · " + popup.state.memory.available + " available" : "Reading memory…"
                    }
                    Caption { text: "Swap   " + (popup.state.memory.swap ?? "–") }
                    Caption { text: "Logical CPUs"; color: Ink.text; font.weight: Font.DemiBold; Layout.topMargin: 4 }
                    GridLayout {
                        Layout.fillWidth: true; columns: 4; rowSpacing: 4; columnSpacing: 8
                        Repeater {
                            model: popup.state.cpu.cores?.length ?? 0
                            RowLayout {
                                id: core
                                required property int index
                                readonly property var usage: popup.state.cpu.cores[index]
                                Layout.fillWidth: true; spacing: 4
                                Accessible.role: Accessible.StaticText
                                Accessible.name: "CPU " + usage.name + ", " + usage.percent + "%"
                                Caption { text: core.usage.name; font.pixelSize: 10 }
                                Rectangle {
                                    Layout.fillWidth: true; Layout.preferredWidth: 32; height: 5; radius: 2; color: Ink.field
                                    Rectangle { width: parent.width * core.usage.percent / 100; height: 5; radius: 2; color: Ink.lavender }
                                }
                                Caption { Layout.preferredWidth: 28; horizontalAlignment: Text.AlignRight; text: core.usage.percent + "%"; font.pixelSize: 10 }
                            }
                        }
                    }
                }
            }
            ProgramList {
                id: programs
                Layout.fillWidth: true; Layout.fillHeight: true
                state: popup.state; showing: popup.visible; ranking: popup.ranking
                onSortBy: metric => popup.ranking = metric
            }
        }
    }
}
