import QtQuick 2.15

Rectangle {
    id: root
    width: 560
    height: 260
    color: "transparent"

    property string titleText: "알림"
    property string messageText: ""
    property string iconKind: "info"
    property var buttonsModel: []

    readonly property color surfaceColor: "#171E23"
    readonly property color borderColor: "#32414B"
    readonly property color textColor: "#F5F7FA"
    readonly property color mutedColor: "#A9B0B7"
    readonly property color accentColor: iconKind === "danger" ? "#FF453A"
        : iconKind === "warning" ? "#FF9F0A"
        : iconKind === "question" ? "#5AC8FA"
        : "#34C759"

    Rectangle {
        anchors.fill: parent
        radius: 26
        color: "#88000000"
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: 14
        radius: 28
        color: surfaceColor
        border.width: 1
        border.color: borderColor

        Rectangle {
            x: 18
            y: 18
            width: 12
            height: Math.max(28, titleLabel.paintedHeight + 12)
            radius: 6
            color: accentColor
        }

        Column {
            anchors.fill: parent
            anchors.margins: 34
            spacing: 22

            Item {
                width: parent.width
                height: titleLabel.paintedHeight + 6
                Text {
                    id: titleLabel
                    anchors.left: parent.left
                    anchors.right: parent.right
                    text: root.titleText
                    color: textColor
                    font.pixelSize: 30
                    font.bold: true
                    elide: Text.ElideRight
                }
            }

            Text {
                width: parent.width
                text: root.messageText
                wrapMode: Text.WordWrap
                color: mutedColor
                font.pixelSize: 18
                lineHeight: 1.25
            }

            Item {
                width: parent.width
                height: 62

                Row {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 14

                    Repeater {
                        model: root.buttonsModel
                        delegate: Rectangle {
                            required property var modelData

                            width: Math.max(116, buttonLabel.paintedWidth + 42)
                            height: 54
                            radius: 14
                            color: modelData.kind === "primary" ? "#0A84FF"
                                : modelData.kind === "warning" ? "#FF9F0A"
                                : modelData.kind === "danger" ? "#FF453A"
                                : "#232E36"
                            border.width: modelData.default ? 2 : 1
                            border.color: modelData.kind === "primary" ? "#52A6FF"
                                : modelData.kind === "warning" ? "#FFC46A"
                                : modelData.kind === "danger" ? "#FF8B84"
                                : "#44535E"

                            Text {
                                id: buttonLabel
                                anchors.centerIn: parent
                                text: String(modelData.label || "")
                                color: "#F5F7FA"
                                font.pixelSize: 17
                                font.bold: true
                            }

                            MouseArea {
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: popupBridge.triggered(String(modelData.id || ""))
                                onEntered: parent.opacity = 0.92
                                onExited: parent.opacity = 1.0
                            }
                        }
                    }
                }
            }
        }
    }
}
