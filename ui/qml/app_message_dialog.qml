import QtQuick 2.15
import "AppPalette.js" as Palette

Rectangle {
    id: root
    width: 560
    height: 260
    color: "transparent"

    property string titleText: "알림"
    property string messageText: ""
    property string iconKind: "info"
    property var buttonsModel: []

    readonly property color surfaceColor: "#F6F7F9"
    readonly property color borderColor: "#D7DEE7"
    readonly property color textColor: "#111820"
    readonly property color mutedColor: "#52606B"
    readonly property color accentColor: iconKind === "danger" ? Palette.danger
        : iconKind === "warning" ? Palette.warning
        : iconKind === "question" ? Palette.info
        : Palette.accent

    Rectangle {
        anchors.fill: parent
        radius: 22
        color: "#44000000"
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: 10
        radius: 22
        color: surfaceColor
        border.width: 1
        border.color: borderColor

        Rectangle {
            x: 18
            y: 18
            width: 8
            height: Math.max(22, titleLabel.paintedHeight + 8)
            radius: 4
            color: accentColor
        }

        Column {
            anchors.fill: parent
            anchors.margins: 28
            spacing: 16

            Item {
                width: parent.width
                height: titleLabel.paintedHeight + 6
                Text {
                    id: titleLabel
                    anchors.left: parent.left
                    anchors.right: parent.right
                    text: root.titleText
                    color: textColor
                    font.pixelSize: 22
                    font.bold: true
                    elide: Text.ElideRight
                }
            }

            Text {
                width: parent.width
                text: root.messageText
                wrapMode: Text.WordWrap
                color: mutedColor
                font.pixelSize: 14
                lineHeight: 1.25
            }

            Item {
                width: parent.width
                height: 46

                Row {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 9

                    Repeater {
                        model: root.buttonsModel
                        delegate: Rectangle {
                            required property var modelData

                            width: Math.max(88, buttonLabel.paintedWidth + 32)
                            height: 36
                            radius: 10
                            color: modelData.kind === "primary" ? "#0A84FF"
                                : modelData.kind === "warning" ? Palette.warning
                                : modelData.kind === "danger" ? Palette.danger
                                : "#E8ECF2"
                            border.width: modelData.default ? 2 : 1
                            border.color: modelData.kind === "primary" ? "#52A6FF"
                                : modelData.kind === "warning" ? Palette.warning
                                : modelData.kind === "danger" ? "#FF8B84"
                                : "#D1D8E0"

                            Text {
                                id: buttonLabel
                                anchors.centerIn: parent
                                text: String(modelData.label || "")
                                color: modelData.kind === "secondary" ? "#111820" : "#FFFFFF"
                                font.pixelSize: 13
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
