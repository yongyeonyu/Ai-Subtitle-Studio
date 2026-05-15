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
                height: modelData.height || (modelData.progressVisible ? ((modelData.meta || "") ? 50 : 38) : 26)
                radius: 7
                color: modelData.progressVisible
                       ? (hitArea.containsMouse ? "#10181D" : "transparent")
                       : (modelData.active ? "#26313A" : (hitArea.containsMouse ? "#1B2429" : "#141C20"))
                border.width: 1
                border.color: modelData.progressVisible
                              ? (modelData.accent || "#00D46A")
                              : (modelData.active
                                 ? (modelData.accent || "#3F8CFF")
                                 : (hitArea.containsMouse ? "#34424B" : "#223038"))
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
                    visible: !!modelData.active && !modelData.progressVisible
                }

                Rectangle {
                    visible: !!modelData.progressVisible && (modelData.progressPercent || 0) > 0
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.margins: 1
                    width: Math.max(0, (parent.width - 2) * Math.max(0, Math.min(100, modelData.progressPercent || 0)) / 100.0)
                    radius: 6
                    color: modelData.fillColor || "#153A25"
                    antialiasing: true
                }

                Row {
                    visible: !modelData.progressVisible
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

                Row {
                    visible: !!modelData.progressVisible
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    anchors.topMargin: 4
                    anchors.bottomMargin: 4
                    spacing: 7

                    Rectangle {
                        width: 16
                        height: 16
                        radius: 4
                        color: "#182126"
                        border.width: 1
                        border.color: modelData.accent || "#00D46A"

                        Text {
                            anchors.centerIn: parent
                            text: modelData.badge || ""
                            color: modelData.accent || "#00D46A"
                            font.pixelSize: 8
                            font.bold: true
                        }
                    }

                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width - 23
                        spacing: 1

                        Row {
                            width: parent.width
                            spacing: 6

                            Text {
                                width: parent.width - percentText.implicitWidth - 6
                                text: modelData.title || ""
                                color: "#F5F7FA"
                                font.pixelSize: 10
                                font.bold: true
                                elide: Text.ElideRight
                                verticalAlignment: Text.AlignVCenter
                            }

                            Text {
                                id: percentText
                                text: modelData.progressText || ""
                                color: modelData.accent || "#00D46A"
                                font.pixelSize: 10
                                font.bold: true
                                verticalAlignment: Text.AlignVCenter
                            }
                        }

                        Text {
                            visible: !!(modelData.subtitle || "")
                            width: parent.width
                            text: modelData.subtitle || ""
                            color: "#B9C7D3"
                            font.pixelSize: 8
                            font.bold: true
                            elide: Text.ElideRight
                            verticalAlignment: Text.AlignVCenter
                        }

                        Text {
                            visible: !!(modelData.meta || "")
                            width: parent.width
                            text: modelData.meta || ""
                            color: "#7F919D"
                            font.pixelSize: 8
                            font.bold: true
                            elide: Text.ElideRight
                            verticalAlignment: Text.AlignVCenter
                        }
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
