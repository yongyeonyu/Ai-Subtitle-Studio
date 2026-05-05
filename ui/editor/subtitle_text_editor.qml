import QtQuick 2.15

Item {
    id: root
    property int lineCount: 0
    property int currentLine: 0
    property bool locked: false
    property string renderBackend: "qwidget"
    clip: true

    Rectangle {
        anchors.fill: parent
        color: "transparent"
    }

    Rectangle {
        id: rail
        width: 3
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        color: root.locked ? "#5E5E64" : "#34C759"
        opacity: 0.9
    }

    Rectangle {
        id: statusPill
        width: Math.min(176, Math.max(112, parent.width * 0.42))
        height: 32
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: 8
        anchors.rightMargin: 12
        radius: 16
        color: root.locked ? "#24282D" : "#14261D"
        border.color: root.locked ? "#5E5E64" : "#2F9E58"
        border.width: 1
        opacity: 0.96
        antialiasing: true

        Row {
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: 10
            spacing: 7

            Rectangle {
                width: 8
                height: 8
                radius: 4
                anchors.verticalCenter: parent.verticalCenter
                color: root.locked ? "#8E8E93" : "#34C759"
            }

            Text {
                width: parent.width - 15
                anchors.verticalCenter: parent.verticalCenter
                text: (root.locked ? "잠금" : "QML") + " · " + Math.max(0, root.currentLine + 1) + "/" + Math.max(0, root.lineCount)
                color: "#DCE3EA"
                font.pixelSize: 10
                font.bold: true
                elide: Text.ElideRight
            }
        }
    }

    Text {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: 12
        anchors.bottomMargin: 8
        text: root.renderBackend
        color: "#56636B"
        font.pixelSize: 9
        font.bold: true
        opacity: 0.75
    }
}
