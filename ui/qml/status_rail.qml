import QtQuick 2.15

Rectangle {
    id: root
    property string modeText: "에디터"
    property string stageText: "대기"
    property string iconText: "AI"
    property color accentColor: "#34C759"
    property bool flashOn: false
    property real progressRatio: 0.0
    property bool progressActive: false
    property bool progressCompleted: false

    radius: 8
    clip: true
    color: root.progressCompleted ? (flashOn ? "#173D28" : "#15331F") : "transparent"
    border.width: 1
    border.color: root.accentColor

    Rectangle {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: root.progressCompleted
               ? parent.width
               : Math.max(0, Math.min(parent.width, parent.width * Math.max(0.0, Math.min(root.progressRatio, 0.99))))
        radius: parent.radius
        visible: root.progressCompleted || root.progressActive
        color: root.progressCompleted
               ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, root.flashOn ? 0.20 : 0.16)
               : Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, root.flashOn ? 0.34 : 0.24)
    }

    Row {
        anchors.fill: parent
        anchors.margins: 5
        spacing: 7

        Rectangle {
            width: 30
            height: 16
            radius: 6
            color: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.20)
            border.width: 1
            border.color: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.55)

            Text {
                anchors.centerIn: parent
                text: root.iconText
                color: root.accentColor
                font.pixelSize: 8
                font.bold: true
            }
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.modeText + " | " + root.stageText
            color: "#D9FFE3"
            font.pixelSize: 11
            font.bold: true
            elide: Text.ElideRight
            width: parent.width - 44
        }
    }
}
