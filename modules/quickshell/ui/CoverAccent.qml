import QtQuick
import "Palette.js" as Ink

Canvas {
    id: sample
    required property string artwork
    property color accent: Ink.lavender
    property string requested: ""
    width: 12; height: 12; opacity: 0

    function loadArtwork() {
        if (!available || requested === artwork) return
        if (requested) unloadImage(requested)
        requested = artwork
        accent = Ink.lavender
        if (requested) {
            loadImage(requested)
            if (isImageLoaded(requested)) requestPaint()
        }
    }
    onArtworkChanged: loadArtwork()
    onAvailableChanged: loadArtwork()
    onImageLoaded: requestPaint()
    onPaint: {
        if (!requested || !isImageLoaded(requested)) return
        const ctx = getContext("2d")
        ctx.clearRect(0, 0, width, height)
        ctx.drawImage(requested, 0, 0, width, height)
        const pixels = ctx.getImageData(0, 0, width, height).data
        // Vote by hue so small bright details or neutral backgrounds don't dominate.
        const weights = Array(12).fill(0)
        let opaque = false
        for (let i = 0; i < pixels.length; i += 4) {
            if (pixels[i + 3] < 128) continue
            opaque = true
            const color = Qt.rgba(pixels[i] / 255, pixels[i + 1] / 255, pixels[i + 2] / 255, 1)
            if (color.hsvHue < 0) continue
            const bin = Math.round(color.hsvHue * weights.length) % weights.length
            weights[bin] += color.hsvSaturation * color.hsvValue
        }
        const weight = Math.max(...weights)
        if (weight > 0.5) accent = Qt.hsla(weights.indexOf(weight) / weights.length, 0.70, 0.74, 1)
        else accent = opaque ? "#c8c5cc" : Ink.lavender
    }
}
