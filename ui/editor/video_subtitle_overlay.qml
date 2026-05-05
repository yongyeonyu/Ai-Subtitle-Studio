import QtQuick 2.15

Item {
    id: root
    property string subtitleText: ""
    property var styleData: ({})
    visible: subtitleText.length > 0
    clip: true

    function outputWidth() {
        var res = String(styleData.res || "FHD (1920px)")
        return (res.indexOf("3840") >= 0 || res.toUpperCase().indexOf("4K") >= 0 || res.toUpperCase().indexOf("UHD") >= 0) ? 3840 : 1920
    }

    function scaledPx(value, fallback) {
        var numberValue = parseFloat(value)
        if (isNaN(numberValue))
            numberValue = fallback
        var resScale = outputWidth() >= 3840 ? 4.0 : 2.0
        return Math.max(1, Math.round(numberValue * resScale * Math.max(0.01, width / outputWidth())))
    }

    function textColor(key, fallback) {
        return String(styleData[key] || fallback)
    }

    readonly property int fontPx: Math.max(4, scaledPx(styleData.size, 22))
    readonly property int sideInset: Math.max(12, Math.round(width * 0.04))
    readonly property real maxTextRatio: parseFloat(styleData.max_text_width_ratio || 0.92)
    readonly property int textBoxWidth: Math.max(48, Math.round(width * Math.min(0.98, maxTextRatio)))
    readonly property int bottomInset: Math.max(8, Math.round(height * 0.11))
    readonly property int lineSpacing: scaledPx(styleData.lsp, 6)
    readonly property string alignMode: String(styleData.align || "가운데")
    readonly property int horizontalAlign: alignMode === "왼쪽" ? Text.AlignLeft : (alignMode === "오른쪽" ? Text.AlignRight : Text.AlignHCenter)
    readonly property int textLeft: alignMode === "왼쪽" ? sideInset : (alignMode === "오른쪽" ? width - textBoxWidth - sideInset : Math.round((width - textBoxWidth) / 2))
    readonly property int baselineBottom: bottomInset + fontPx

    Rectangle {
        id: backgroundPlate
        visible: !!styleData.bg
        x: styleData.bg_full ? 0 : textLeft - scaledPx(styleData.bg_margin, 18)
        y: textBlock.y - Math.round(scaledPx(styleData.bg_margin, 18) / 2)
        width: styleData.bg_full ? root.width : textBoxWidth + scaledPx(styleData.bg_margin, 18) * 2
        height: textBlock.height + scaledPx(styleData.bg_margin, 18)
        radius: styleData.bg_full ? 0 : scaledPx(styleData.bg_radius, 10)
        color: textColor("bg_c", "#000000")
        opacity: Math.max(0.0, Math.min(1.0, parseFloat(styleData.bg_op || 50) / 100.0))
        antialiasing: true
    }

    Text {
        id: shadowText
        visible: !!styleData.shadow
        x: textBlock.x + scaledPx(styleData.shdx, 3)
        y: textBlock.y + scaledPx(styleData.shdy, 3)
        width: textBlock.width
        text: root.subtitleText.replace(/\u2028/g, "\n")
        color: textColor("shd_c", "#000000")
        font.family: String(styleData.font || "Apple SD Gothic Neo")
        font.pixelSize: root.fontPx
        font.bold: styleData.bold === undefined ? true : !!styleData.bold
        horizontalAlignment: root.horizontalAlign
        wrapMode: Text.WordWrap
        lineHeightMode: Text.FixedHeight
        lineHeight: root.fontPx + root.lineSpacing
        opacity: 0.8
        renderType: Text.QtRendering
    }

    Text {
        id: textBlock
        x: root.textLeft
        y: Math.max(8, root.height - implicitHeight - root.baselineBottom)
        width: root.textBoxWidth
        text: root.subtitleText.replace(/\u2028/g, "\n")
        color: textColor("txt_c", "#FFFFFF")
        font.family: String(styleData.font || "Apple SD Gothic Neo")
        font.pixelSize: root.fontPx
        font.bold: styleData.bold === undefined ? true : !!styleData.bold
        horizontalAlignment: root.horizontalAlign
        wrapMode: Text.WordWrap
        lineHeightMode: Text.FixedHeight
        lineHeight: root.fontPx + root.lineSpacing
        style: styleData.no_bdr ? Text.Normal : Text.Outline
        styleColor: textColor("bdr_c", "#FFFFFF")
        renderType: Text.QtRendering
    }
}
