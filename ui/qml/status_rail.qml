import QtQuick 2.15

Rectangle {
    id: root
    property string modeText: "에디터"
    property string stageText: "대기"
    property string iconText: "AI"
    property color accentColor: "#34C759"
    property bool flashOn: false

    radius: 9
    color: flashOn ? "#173D28" : "#15331F"
    border.width: 1
    border.color: root.accentColor

    Row {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 8

        Rectangle {
            width: 34
            height: 20
            radius: 6
            color: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.20)
            border.width: 1
            border.color: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.55)

            Text {
                anchors.centerIn: parent
                text: root.iconText
                color: root.accentColor
                font.pixelSize: 9
                font.bold: true
            }
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.modeText + " | " + root.stageText
            color: "#D9FFE3"
            font.pixelSize: 12
            font.bold: true
            elide: Text.ElideRight
            width: parent.width - 52
        }
    }
}
