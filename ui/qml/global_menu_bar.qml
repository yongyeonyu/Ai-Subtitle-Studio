import QtQuick 2.15

Rectangle {
    id: root
    property var leftItems: []
    property var centerItems: []
    property var rightItems: []
    property string activeActionId: ""

    signal actionTriggered(string actionId)

    radius: 7
    clip: true
    antialiasing: true

    function flashAction(actionId) {
        activeActionId = actionId || ""
        clickFlash.restart()
    }

    color: "#12191E"
    border.width: 1
    border.color: "#27343D"

    Timer {
        id: clickFlash
        interval: 180
        repeat: false
        onTriggered: root.activeActionId = ""
    }

    function fillFor(item) {
        if (!item.enabled) return "#182026"
        if (item.kind === "danger") return "#2A1C1D"
        if (item.kind === "primary") return "#18252D"
        return "#1A2228"
    }

    function hoverFillFor(item) {
        if (!item.enabled) return fillFor(item)
        if (item.kind === "danger") return "#372022"
        if (item.kind === "primary") return "#223642"
        return "#243039"
    }

    function pressFillFor(item) {
        if (!item.enabled) return fillFor(item)
        if (item.kind === "danger") return "#4A171B"
        return "#0A467A"
    }

    function borderFor(item) {
        return item.accent || "#3A424A"
    }

    function hoverBorderFor(item) {
        if (!item.enabled) return borderFor(item)
        if (item.kind === "danger") return "#FF8A80"
        return item.accent || "#74A9FF"
    }

    function textFor(item) {
        return item.enabled ? "#F5F7FA" : "#73808B"
    }

    function labelColorFor(buttonRoot, item) {
        if (!item.enabled) return root.textFor(item)
        if (buttonRoot.activePress) return "#FFFFFF"
        if (buttonRoot.hoverActive) return "#FFFFFF"
        if (item.kind === "danger") return "#FF8A80"
        return item.accent || root.textFor(item)
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
                id: leftButtonRoot
                required property var modelData
                property bool hoverActive: leftMouse.containsMouse && !!modelData.enabled
                property bool activePress: leftMouse.pressed || root.activeActionId === modelData.id
                width: 52
                height: parent.height
                radius: 12
                scale: activePress ? 0.91 : (hoverActive ? 1.035 : 1.0)
                color: activePress ? root.pressFillFor(modelData) : (hoverActive ? root.hoverFillFor(modelData) : root.fillFor(modelData))
                border.width: activePress ? 2 : (hoverActive ? 2 : 1)
                border.color: activePress ? "#D7EBFF" : (hoverActive ? root.hoverBorderFor(modelData) : root.borderFor(modelData))
                opacity: modelData.enabled ? 1.0 : 0.65
                Behavior on scale { NumberAnimation { duration: 70; easing.type: Easing.OutCubic } }
                Behavior on color { ColorAnimation { duration: 90 } }

                Item {
                    anchors.centerIn: parent
                    width: parent.width
                    height: leftLabel.implicitHeight
                    Text {
                        id: leftLabel
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: modelData.text || ""
                        color: root.labelColorFor(leftButtonRoot, modelData)
                        font.pixelSize: 11
                        font.bold: true
                        elide: Text.ElideRight
                        width: parent.width - 8
                        horizontalAlignment: Text.AlignHCenter
                    }
                }

                MouseArea {
                    id: leftMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    enabled: !!modelData.enabled
                    cursorShape: Qt.PointingHandCursor
                    onPressed: root.flashAction(modelData.id)
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
                id: centerButtonRoot
                required property var modelData
                property bool hoverActive: centerMouse.containsMouse && !!modelData.enabled
                property bool activePress: centerMouse.pressed || root.activeActionId === modelData.id
                width: Math.max(68, Math.min(94, centerLabel.implicitWidth + 34))
                height: parent.height
                radius: 12
                scale: activePress ? 0.91 : (hoverActive ? 1.035 : 1.0)
                color: activePress ? root.pressFillFor(modelData) : (hoverActive ? root.hoverFillFor(modelData) : root.fillFor(modelData))
                border.width: activePress ? 2 : (hoverActive ? 2 : 1)
                border.color: activePress ? "#D7EBFF" : (hoverActive ? root.hoverBorderFor(modelData) : root.borderFor(modelData))
                opacity: modelData.enabled ? 1.0 : 0.78
                Behavior on scale { NumberAnimation { duration: 70; easing.type: Easing.OutCubic } }
                Behavior on color { ColorAnimation { duration: 90 } }

                Item {
                    anchors.centerIn: parent
                    width: parent.width
                    height: centerLabel.implicitHeight
                    Text {
                        id: centerLabel
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: modelData.text || ""
                        color: root.labelColorFor(centerButtonRoot, modelData)
                        font.pixelSize: 11
                        font.bold: true
                        elide: Text.ElideRight
                        width: parent.width - 10
                        horizontalAlignment: Text.AlignHCenter
                    }
                }

                MouseArea {
                    id: centerMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    enabled: !!modelData.enabled
                    cursorShape: Qt.PointingHandCursor
                    onPressed: root.flashAction(modelData.id)
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
                id: rightButtonRoot
                required property var modelData
                property bool hoverActive: rightMouse.containsMouse && !!modelData.enabled
                property bool activePress: rightMouse.pressed || root.activeActionId === modelData.id
                width: Math.max(64, Math.min(88, rightLabel.implicitWidth + 30))
                height: parent.height
                radius: 12
                scale: activePress ? 0.91 : (hoverActive ? 1.035 : 1.0)
                color: activePress ? root.pressFillFor(modelData) : (hoverActive ? root.hoverFillFor(modelData) : root.fillFor(modelData))
                border.width: activePress ? 2 : (hoverActive ? 2 : 1)
                border.color: activePress ? "#D7EBFF" : (hoverActive ? root.hoverBorderFor(modelData) : root.borderFor(modelData))
                opacity: modelData.enabled ? 1.0 : 0.65
                Behavior on scale { NumberAnimation { duration: 70; easing.type: Easing.OutCubic } }
                Behavior on color { ColorAnimation { duration: 90 } }

                Item {
                    anchors.centerIn: parent
                    width: parent.width
                    height: rightLabel.implicitHeight
                    Text {
                        id: rightLabel
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: modelData.text || ""
                        color: root.labelColorFor(rightButtonRoot, modelData)
                        font.pixelSize: 11
                        font.bold: true
                        elide: Text.ElideRight
                        width: parent.width - 10
                        horizontalAlignment: Text.AlignHCenter
                    }
                }

                MouseArea {
                    id: rightMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    enabled: !!modelData.enabled
                    cursorShape: Qt.PointingHandCursor
                    onPressed: root.flashAction(modelData.id)
                    onClicked: root.actionTriggered(modelData.id)
                }
            }
        }
    }
}
