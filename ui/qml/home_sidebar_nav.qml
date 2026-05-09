import QtQuick 2.15

Rectangle {
    id: root
    property var menuItems: []

    signal actionTriggered(string actionId)

    color: "transparent"
    clip: true
    implicitWidth: 204
    implicitHeight: contentColumn.implicitHeight

    Column {
        id: contentColumn
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: 4

        Repeater {
            model: root.menuItems

            delegate: Rectangle {
                required property var modelData

                width: root.width
                height: 26
                radius: 7
                color: modelData.active ? "#26313A" : (hitArea.containsMouse ? "#1B2429" : "#141C20")
                border.width: 1
                border.color: modelData.active
                              ? (modelData.accent || "#3F8CFF")
                              : (hitArea.containsMouse ? "#34424B" : "#223038")
                opacity: modelData.enabled === false ? 0.55 : 1.0
                antialiasing: true

                Rectangle {
                    anchors.left: parent.left
                    anchors.leftMargin: 7
                    anchors.verticalCenter: parent.verticalCenter
                    width: 4
                    height: parent.height - 10
                    radius: 2
                    color: modelData.accent || "#3F8CFF"
                    visible: !!modelData.active
                }

                Row {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    spacing: 7

                    Rectangle {
                        width: 16
                        height: 16
                        radius: 4
                        color: modelData.active ? "#10181D" : "#182126"
                        border.width: 1
                        border.color: modelData.active ? (modelData.accent || "#3F8CFF") : "#243139"

                        Text {
                            anchors.centerIn: parent
                            text: modelData.badge || ""
                            color: modelData.active ? (modelData.accent || "#74A9FF") : "#A9B0B7"
                            font.pixelSize: 8
                            font.bold: true
                        }
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width - 23
                        text: modelData.title || ""
                        color: modelData.active ? "#F5F7FA" : "#D7DEE5"
                        font.pixelSize: 10
                        font.bold: true
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                    }
                }

                MouseArea {
                    id: hitArea
                    anchors.fill: parent
                    hoverEnabled: true
                    enabled: modelData.enabled !== false
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.actionTriggered(modelData.id)
                }
            }
        }
    }
}
