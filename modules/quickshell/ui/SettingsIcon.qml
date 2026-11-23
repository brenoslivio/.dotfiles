import QtQuick
import QtQuick.Controls.impl as Style
import "Palette.js" as Ink

Style.IconImage {
    required property string symbol
    width: 24; height: width
    source: symbol ? Qt.resolvedUrl(symbol + "-symbolic.svg") : ""
    sourceSize.width: width; sourceSize.height: height
    color: Ink.muted
}
