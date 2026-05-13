import QtQuick 2.15

Rectangle {
    id: root
    property string timeText: "00:00 / 00:00"
    property string infoText: ""
    property string frameText: ""
    property string sourceNameText: ""
    property string playText: "\u25b6"
    property bool playing: false
    property bool scanPrevActive: false
    property bool scanNextActive: false

    signal playRequested()
    signal prevFrameRequested()
    signal nextFrameRequested()
    signal prevScanRequested()
    signal nextScanRequested()

    color: "#151C20"
    radius: 12
    border.width: 1
    border.color: "#2D3942"

    function buttonBackground(active, primary) {
        if (active && primary) return "#1F8F4D"
        if (active) return "#2D3942"
        return primary ? "#27323A" : "#20282F"
    }

    function buttonBorder(active, primary) {
        if (active && primary) return "#30D158"
        if (active) return "#579DFF"
        return primary ? "#3E5661" : "#313A42"
    }

    function badgeBackground() {
        return playing ? "#173D28" : "#1D2329"
    }

    TextMetrics {
        id: infoTextMetrics
        font: infoTextItem.font
        text: root.infoText
    }

    TextMetrics {
        id: sourceTextMetrics
        font: sourceText.font
        text: root.sourceNameText
    }

    TextMetrics {
        id: frameTextMetrics
        font: frameTextItem.font
        text: root.frameText
    }

    Row {
        id: controlRow
        anchors.left: parent.left
        anchors.leftMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        height: parent.height - 16
        spacing: 6

        Rectangle {
            width: 44
            height: 32
            radius: 9
            color: buttonBackground(scanPrevActive, false)
            border.width: 1
            border.color: buttonBorder(scanPrevActive, false)
            Text {
                anchors.centerIn: parent
                text: "\u00ab\u00ab"
                color: "#F5F7FA"
                font.pixelSize: 13
                font.bold: true
            }
            MouseArea {
                anchors.fill: parent
                onClicked: root.prevScanRequested()
            }
        }

        Rectangle {
            width: 36
            height: 32
            radius: 9
            color: "#20282F"
            border.width: 1
            border.color: "#313A42"
            Text {
                anchors.centerIn: parent
                text: "\u2039"
                color: "#EAF2F8"
                font.pixelSize: 18
                font.bold: true
            }
            MouseArea {
                anchors.fill: parent
                onClicked: root.prevFrameRequested()
            }
        }

        Rectangle {
            width: 54
            height: 32
            radius: 10
            color: buttonBackground(playing, true)
            border.width: 1
            border.color: buttonBorder(playing, true)
            Text {
                anchors.centerIn: parent
                text: root.playText
                color: "#FFFFFF"
                font.pixelSize: 13
                font.bold: true
            }
            MouseArea {
                anchors.fill: parent
                onClicked: root.playRequested()
            }
        }

        Rectangle {
            width: 36
            height: 32
            radius: 9
            color: "#20282F"
            border.width: 1
            border.color: "#313A42"
            Text {
                anchors.centerIn: parent
                text: "\u203a"
                color: "#EAF2F8"
                font.pixelSize: 18
                font.bold: true
            }
            MouseArea {
                anchors.fill: parent
                onClicked: root.nextFrameRequested()
            }
        }

        Rectangle {
            width: 44
            height: 32
            radius: 9
            color: buttonBackground(scanNextActive, false)
            border.width: 1
            border.color: buttonBorder(scanNextActive, false)
            Text {
                anchors.centerIn: parent
                text: "\u00bb\u00bb"
                color: "#F5F7FA"
                font.pixelSize: 13
                font.bold: true
            }
            MouseArea {
                anchors.fill: parent
                onClicked: root.nextScanRequested()
            }
        }

        Rectangle {
            width: timeTextItem.implicitWidth + 22
            height: 32
            radius: 9
            color: badgeBackground()
            border.width: 1
            border.color: playing ? "#34C759" : "#313A42"
            Text {
                id: timeTextItem
                anchors.centerIn: parent
                text: root.timeText
                color: "#EAF2F8"
                font.pixelSize: 11
                font.bold: true
            }
        }

        Rectangle {
            id: frameBadge
            visible: root.frameText.length > 0
            width: visible ? Math.ceil(frameTextMetrics.boundingRect.width) + 24 : 0
            height: 32
            radius: 9
            color: "#132831"
            border.width: 1
            border.color: "#245A6A"
            clip: true
            Text {
                id: frameTextItem
                anchors.centerIn: parent
                text: root.frameText
                color: "#8FE7FF"
                font.pixelSize: 10
                font.bold: true
            }
        }
    }

    Item {
        id: statusRow
        anchors.left: controlRow.right
        anchors.leftMargin: 12
        anchors.right: parent.right
        anchors.rightMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        height: parent.height - 16

        Rectangle {
            id: infoBadge
            visible: root.infoText.length > 0
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            width: visible ? Math.min(280, Math.ceil(infoTextMetrics.boundingRect.width) + 26) : 0
            height: 32
            radius: 9
            color: "#1A2127"
            border.width: 1
            border.color: "#2D3942"
            clip: true
            Text {
                id: infoTextItem
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: 13
                anchors.right: parent.right
                anchors.rightMargin: 13
                text: root.infoText
                color: "#A9B0B7"
                font.pixelSize: 10
                elide: Text.ElideRight
            }
        }

        Rectangle {
            id: sourceBadge
            visible: root.sourceNameText.length > 0
            anchors.left: infoBadge.visible ? infoBadge.right : parent.left
            anchors.leftMargin: infoBadge.visible ? 6 : 0
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            width: visible ? Math.max(0, parent.width - (infoBadge.visible ? infoBadge.width + 6 : 0)) : 0
            height: 32
            radius: 9
            color: "#182126"
            border.width: 1
            border.color: "#2F4852"
            clip: true
            Text {
                id: sourceText
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: 12
                anchors.right: parent.right
                anchors.rightMargin: 12
                text: root.sourceNameText
                color: "#EAF2F8"
                font.pixelSize: 10
                font.bold: true
                elide: Text.ElideRight
                horizontalAlignment: Text.AlignRight
            }
        }
    }
}
