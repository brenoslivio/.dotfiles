import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic as Controls
import "Palette.js" as Ink

RowLayout {
    id: level
    required property string label
    required property string icon
    required property real percent
    property bool canMute: false
    property bool muted: false
    property int minimum: 0
    property int maximum: Math.max(100, Math.ceil(percent / 25) * 25)
    property bool boostRange: false
    signal toggleMute()
    signal adjusted(int percent, bool finalValue)
    function syncLevel() {
        if (!slider.pressed) {
            slider.value = percent
        }
    }
    onPercentChanged: if (slider) syncLevel()
    Component.onCompleted: syncLevel()
    spacing: 8
    TaskButton {
        minimumWidth: 34
        SettingsIcon { anchors.centerIn: parent; symbol: level.icon; color: level.muted ? Ink.inactive : Ink.lavender }
        enabled: level.canMute; opacity: 1
        labelColor: level.muted ? Ink.inactive : Ink.lavender
        Accessible.name: (level.muted ? "Unmute " : "Mute ") + level.label
        onTriggered: level.toggleMute()
    }
    Controls.Slider {
        id: slider
        Layout.fillWidth: true; Layout.preferredHeight: 32
        Accessible.name: level.label
        from: level.minimum; to: level.maximum; stepSize: 1
        live: true
        onMoved: level.adjusted(Math.round(value), !pressed)
        onPressedChanged: if (!pressed) level.adjusted(Math.round(value), true)
        background: Rectangle {
            x: slider.leftPadding; y: (slider.height - height) / 2
            width: slider.availableWidth; height: 8; radius: 4; color: Ink.field
            Rectangle {
                width: parent.width * slider.visualPosition; height: parent.height; radius: 4
                color: level.muted ? Ink.inactive : Ink.lavender
            }
            Rectangle {
                visible: level.boostRange
                x: parent.width / 2; width: Math.max(0, parent.width * (slider.visualPosition - 0.5))
                height: parent.height; radius: 3; color: Ink.magenta
            }
            Rectangle {
                visible: level.boostRange; anchors.centerIn: parent
                width: 2; height: 12; radius: 1; color: Ink.text
            }
        }
        handle: Rectangle {
            x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - width)
            y: (slider.height - height) / 2
            width: 15; height: 15; radius: 8
            color: Ink.text; border.color: slider.visualFocus ? Ink.magenta : Ink.lavender
        }
    }
    Text {
        Layout.preferredWidth: 34; horizontalAlignment: Text.AlignRight
        text: Math.round(slider.value) + "%"
        color: Ink.muted; font.family: "Inter"; font.pixelSize: 11
    }
}
