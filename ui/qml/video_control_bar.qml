import QtQuick 2.15

Rectangle {
    id: root
    property int gap: 6
    property string timeText: "00:00 / 00:00"
    property string infoText: ""
    property string frameText: ""
    property string sourceNameText: ""
    property string playText: "\u25b6"
    property bool playing: false
    property bool scanPrevActive: false
    property bool scanNextActive: false
    property int contentLeftInset: 0
    property int contentRightInset: 0

    signal playRequested()
    signal prevFrameRequested()
    signal nextFrameRequested()
    signal prevScanRequested()
    signal nextScanRequested()

    color: "transparent"
    radius: 12
    border.width: 0
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
        text: (root.infoText || "").replace(/\n/g, " | ")
    }

    TextMetrics {
        id: sourceTextMetrics
        font: sourceText.font
        text: (root.sourceNameText || "").replace(/\n/g, " ")
    }

    Row {
        id: controlRow
        anchors.left: parent.left
        anchors.leftMargin: root.contentLeftInset + 8
        anchors.verticalCenter: parent.verticalCenter
        height: 32
        spacing: root.gap

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
            width: visible ? 124 : 0
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
        anchors.leftMargin: root.gap
        anchors.right: parent.right
        anchors.rightMargin: root.contentRightInset + 8
        anchors.verticalCenter: parent.verticalCenter
        height: 36

        Rectangle {
            id: infoBadge
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            width: Math.max(
                160,
                Math.min(
                    Math.ceil(infoTextMetrics.boundingRect.width) + 28,
                    Math.max(160, Math.floor(parent.width * 0.24))
                )
            )
            height: 36
            radius: 9
            color: "#1A2127"
            border.width: 1
            border.color: "#2D3942"
            clip: true
            Text {
                id: infoTextItem
                anchors.fill: parent
                anchors.leftMargin: 13
                anchors.rightMargin: 13
                anchors.topMargin: 4
                anchors.bottomMargin: 4
                text: root.infoText
                color: "#A9B0B7"
                font.pixelSize: 9
                wrapMode: Text.WrapAtWordBoundaryOrAnywhere
                maximumLineCount: 2
                elide: Text.ElideRight
                verticalAlignment: Text.AlignVCenter
            }
        }

        Rectangle {
            id: sourceBadge
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            visible: root.sourceNameText.length > 0
            width: visible ? Math.max(
                156,
                Math.min(
                    Math.ceil(sourceTextMetrics.boundingRect.width) + 28,
                    Math.max(156, Math.floor(parent.width * 0.22))
                )
            ) : 0
            height: 36
            radius: 9
            color: "#182126"
            border.width: 1
            border.color: "#2F4852"
            clip: true
            Text {
                id: sourceText
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                anchors.topMargin: 4
                anchors.bottomMargin: 4
                text: root.sourceNameText
                color: "#EAF2F8"
                font.pixelSize: 10
                font.bold: true
                wrapMode: Text.WrapAtWordBoundaryOrAnywhere
                maximumLineCount: 2
                elide: Text.ElideRight
                horizontalAlignment: Text.AlignRight
                verticalAlignment: Text.AlignVCenter
            }
        }
    }
}
