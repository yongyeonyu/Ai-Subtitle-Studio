import QtQuick 2.15

Rectangle {
    id: root
    width: 280
    height: menuColumn.implicitHeight + 20
    radius: 18
    color: "#171E23"
    border.width: 1
    border.color: "#32414B"

    property var menuItems: []

    Column {
        id: menuColumn
        anchors.fill: parent
        anchors.margins: 10
        spacing: 6

        Repeater {
            model: root.menuItems
            delegate: Item {
                required property var modelData
                width: menuColumn.width
                height: modelData.separator ? 8 : 38

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    height: modelData.separator ? 1 : parent.height
                    radius: modelData.separator ? 0 : 10
                    color: modelData.separator ? "#2D3942" : (hoverArea.containsMouse ? "#21313C" : "transparent")
                    visible: true
                }

                Rectangle {
                    visible: !modelData.separator && String(modelData.accent || "").length > 0
                    x: 10
                    y: (parent.height - 10) / 2
                    width: 10
                    height: 10
                    radius: 5
                    color: String(modelData.accent || "#34C759")
                    opacity: modelData.enabled === false ? 0.4 : 1.0
                }

                Text {
                    visible: !modelData.separator && modelData.checked === true
                    x: 10
                    anchors.verticalCenter: parent.verticalCenter
                    text: "✓"
                    color: "#5AC8FA"
                    font.pixelSize: 15
                    font.bold: true
                }

                Text {
                    visible: !modelData.separator
                    anchors.left: parent.left
                    anchors.leftMargin: (modelData.checked === true || String(modelData.accent || "").length > 0) ? 30 : 12
                    anchors.verticalCenter: parent.verticalCenter
                    text: String(modelData.label || "")
                    color: modelData.enabled === false ? "#6F7A83"
                        : (modelData.danger === true ? "#FFB4AE" : "#F5F7FA")
                    font.pixelSize: 15
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
