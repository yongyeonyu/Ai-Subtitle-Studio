import QtQuick 2.15

Rectangle {
    id: root
    property var leftItems: []
    property var centerItems: []
    property var rightItems: []

    signal actionTriggered(string actionId)

    color: "#151C20"
    border.width: 1
    border.color: "#2D3942"

    function fillFor(item) {
        if (!item.enabled) return "#182026"
        if (item.kind === "danger") return "#2A1D1D"
        if (item.kind === "primary") return "#1B2730"
        return "#1C2329"
    }

    function borderFor(item) {
        return item.accent || "#3A424A"
    }

    function textFor(item) {
        return item.enabled ? "#F5F7FA" : "#73808B"
    }

    function badgeFor(item) {
        return item.badge || ""
    }

    Row {
        id: leftRow
        anchors.left: parent.left
        anchors.leftMargin: 6
        anchors.verticalCenter: parent.verticalCenter
        height: parent.height - 12
        spacing: 5
        Repeater {
            model: root.leftItems
            delegate: Rectangle {
                required property var modelData
                width: 52
                height: parent.height
                radius: 10
                color: root.fillFor(modelData)
                border.width: 1
                border.color: root.borderFor(modelData)
                opacity: modelData.enabled ? 1.0 : 0.65

                Column {
                    anchors.centerIn: parent
                    spacing: 3
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: root.badgeFor(modelData)
                        color: modelData.accent || "#A9B0B7"
                        font.pixelSize: 10
                        font.bold: true
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: modelData.text || ""
                        color: root.textFor(modelData)
                        font.pixelSize: 10
                        font.bold: true
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    enabled: !!modelData.enabled
                    onClicked: root.actionTriggered(modelData.id)
                }
            }
        }
    }

    Row {
        id: centerRow
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        height: parent.height - 12
        spacing: 5
        Repeater {
            model: root.centerItems
            delegate: Rectangle {
                required property var modelData
                width: Math.max(68, Math.min(94, centerLabel.implicitWidth + 30, centerBadge.implicitWidth + 24))
                height: parent.height
                radius: 10
                color: root.fillFor(modelData)
                border.width: 1
                border.color: root.borderFor(modelData)
                opacity: modelData.enabled ? 1.0 : 0.78

                Column {
                    anchors.centerIn: parent
                    spacing: 3
                    Text {
                        id: centerBadge
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: root.badgeFor(modelData)
                        color: modelData.accent || "#F5F7FA"
                        font.pixelSize: 10
                        font.bold: true
                    }
                    Text {
                        id: centerLabel
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: modelData.text || ""
                        color: root.textFor(modelData)
                        font.pixelSize: 10
                        font.bold: true
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    enabled: !!modelData.enabled
                    onClicked: root.actionTriggered(modelData.id)
                }
            }
        }
    }

    Row {
        id: rightRow
        anchors.right: parent.right
        anchors.rightMargin: 6
        anchors.verticalCenter: parent.verticalCenter
        height: parent.height - 12
        spacing: 5
        Repeater {
            model: root.rightItems
            delegate: Rectangle {
                required property var modelData
                width: Math.max(64, Math.min(88, label.implicitWidth + 30))
                height: parent.height
                radius: 10
                color: root.fillFor(modelData)
                border.width: 1
                border.color: root.borderFor(modelData)
                opacity: modelData.enabled ? 1.0 : 0.65

                Column {
                    anchors.centerIn: parent
                    spacing: 3
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: root.badgeFor(modelData)
                        color: modelData.kind === "danger" ? "#FF8A80" : (modelData.accent || "#A9B0B7")
                        font.pixelSize: 10
                        font.bold: true
                    }
                    Text {
                        id: label
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: modelData.text || ""
                        color: root.textFor(modelData)
                        font.pixelSize: 10
                        font.bold: true
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    enabled: !!modelData.enabled
                    onClicked: root.actionTriggered(modelData.id)
                }
            }
        }
    }
}
