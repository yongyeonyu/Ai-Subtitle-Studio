import QtQuick 2.15

Rectangle {
    id: root
    width: 260
    implicitHeight: menuColumn.implicitHeight + 16
    radius: 15
    color: "#F6F7F9"
    border.width: 1
    border.color: "#D7DEE7"
    clip: true

    property var menuItems: []

    Flickable {
        id: menuFlick
        anchors.fill: parent
        anchors.margins: 8
        clip: true
        contentHeight: menuColumn.implicitHeight
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: menuColumn
            width: menuFlick.width
            spacing: 3

            Repeater {
                model: root.menuItems
                delegate: Item {
                    required property var modelData
                    width: menuColumn.width
                    height: modelData.separator ? 7 : 32

                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        height: modelData.separator ? 1 : parent.height
                        radius: modelData.separator ? 0 : 9
                        color: modelData.separator ? "#DDE3EA" : (hoverArea.pressed ? "#D9EBFF" : (hoverArea.containsMouse ? "#E8F1FF" : "transparent"))
                        visible: true
                    }

                    Rectangle {
                        visible: !modelData.separator && String(modelData.accent || "").length > 0
                        x: 10
                        y: (parent.height - 8) / 2
                        width: 8
                        height: 8
                        radius: 4
                        color: String(modelData.accent || "#34C759")
                        opacity: modelData.enabled === false ? 0.4 : 1.0
                    }

                    Text {
                        visible: !modelData.separator && modelData.checked === true
                        x: 10
                        anchors.verticalCenter: parent.verticalCenter
                        text: "✓"
                        color: "#0A84FF"
                        font.pixelSize: 14
                        font.bold: true
                    }

                    Text {
                        visible: !modelData.separator
                        anchors.left: parent.left
                        anchors.leftMargin: (modelData.checked === true || String(modelData.accent || "").length > 0) ? 30 : 12
                        anchors.verticalCenter: parent.verticalCenter
                        text: String(modelData.label || "")
                        color: modelData.enabled === false ? "#8A929C"
                            : (modelData.danger === true ? "#D70015" : "#111820")
                        font.pixelSize: 13
                        font.bold: modelData.checked === true
                        elide: Text.ElideRight
                        width: parent.width - anchors.leftMargin - 16
                    }

                    MouseArea {
                        id: hoverArea
                        anchors.fill: parent
                        hoverEnabled: true
                        enabled: !modelData.separator && modelData.enabled !== false
                        onClicked: popupBridge.triggered(String(modelData.id || ""))
                    }
                }
            }
        }
    }
}
