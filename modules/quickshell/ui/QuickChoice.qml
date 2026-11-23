import QtQuick
import QtQuick.Controls.Basic as Controls
import QtQuick.Layouts
import "Palette.js" as Ink

Controls.Button {
    id: button
    property string symbol: ""
    property bool iconDivider: false
    property string detail: ""
    property string trailing: ""
    property bool current: false
    padding: 10
    verticalPadding: symbol ? 6 : padding
    horizontalPadding: 12
    implicitHeight: detail ? 53 : 37
    Accessible.name: [text, detail, trailing].filter(Boolean).join(", ")
    background: Rectangle {
        radius: 9
        color: button.down || button.hovered ? Ink.selection : Ink.field
        border.color: button.visualFocus ? Ink.lavender : "transparent"
    }
    contentItem: RowLayout {
        spacing: 6
        SettingsIcon { visible: !!button.symbol; symbol: button.symbol; color: Ink.lavender }
        Rectangle {
            visible: button.iconDivider
            Layout.preferredWidth: 1; Layout.preferredHeight: 24
            color: Qt.alpha(Ink.lavender, 0.24)
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text {
                Layout.fillWidth: true
                text: button.text; textFormat: Text.PlainText; elide: Text.ElideRight
                color: button.current ? Ink.lavender : Ink.text
                font.family: "Inter"; font.pixelSize: 13; font.weight: Font.Medium
            }
            Text {
                Layout.fillWidth: true; visible: !!text
                text: button.detail; textFormat: Text.PlainText; elide: Text.ElideRight
                color: Ink.muted; font.family: "Inter"; font.pixelSize: 11
            }
        }
        Text {
            visible: !!text; text: button.trailing; textFormat: Text.PlainText
            font.family: "Inter"; font.pixelSize: ["✓", "›", "+"].includes(text) ? 18 : 12; color: Ink.lavender
        }
    }
}
