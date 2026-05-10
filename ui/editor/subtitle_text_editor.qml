import QtQuick 2.15

Item {
    id: root
    property bool locked: false
    property bool editorFocused: false
    property int contentLeft: 0
    property var visibleLines: []
    property int cardInset: 4
    property int accentInset: 8
    property int textInset: 24
    property int rightInset: 28
    property int timeLeft: 28
    property int timeWidth: 92
    property int circleX: Math.max(0, contentLeft - 22)
    property int cardRadius: 3
    property color surfaceColor: locked ? "#1C1C1E" : "#11181C"
    clip: true

    Rectangle {
        anchors.fill: parent
        color: "transparent"
    }

    Rectangle {
        x: root.contentLeft
        y: 0
        width: Math.max(0, root.width - root.contentLeft)
        height: root.height
        color: root.surfaceColor
    }

    Rectangle {
        x: 0
        y: 0
        width: Math.max(0, root.contentLeft)
        height: root.height
        color: root.surfaceColor
    }

    Repeater {
        model: root.visibleLines

        Item {
            x: 0
            y: modelData.y
            width: root.width
            height: Math.max(24, modelData.height)

            Rectangle {
                visible: String(modelData.fill || "transparent") !== "transparent"
                x: root.contentLeft + root.cardInset
                y: 1
                width: Math.max(24, parent.width - root.contentLeft - root.rightInset)
                height: Math.max(20, parent.height - 2)
                radius: root.cardRadius
                color: modelData.fill || (root.locked ? "#182026" : "#141C21")
                border.width: modelData.active ? 1 : 0
                border.color: modelData.active ? "#34C759" : "transparent"
                opacity: modelData.active ? 0.98 : 0.90
                antialiasing: true
            }

            Rectangle {
                visible: !!modelData.deleteVisible
                x: 5
                y: Math.round((parent.height - 16) / 2)
                width: 16
                height: 16
                radius: 4
                color: modelData.deleteHovered ? "#FF4444" : "#442222"
                antialiasing: true

                Text {
                    anchors.centerIn: parent
                    text: "\u00d7"
                    color: modelData.deleteHovered ? "#FFFFFF" : "#FF8888"
                    font.pixelSize: 11
                    font.bold: true
                }
            }

            Text {
                visible: String(modelData.timestamp || "").length > 0
                x: root.timeLeft
                y: 0
                width: root.timeWidth
                height: parent.height
                text: "[" + String(modelData.timestamp || "") + "]"
                color: modelData.active ? (modelData.accent || "#00FF88") : "#00E58C"
                font.family: "Menlo"
                font.pixelSize: 13
                font.bold: true
                verticalAlignment: Text.AlignVCenter
                horizontalAlignment: Text.AlignLeft
                renderType: Text.QtRendering
                clip: true
            }

            Rectangle {
                visible: !!modelData.showCircle
                x: root.circleX
                y: Math.round((parent.height - width) / 2)
                width: modelData.active ? 10 : 6
                height: width
                radius: width / 2
                color: modelData.active ? (modelData.accent || "#34C759") : "#555555"
                antialiasing: true
            }

            Rectangle {
                x: root.contentLeft + root.accentInset
                y: 2
                width: 4
                height: Math.max(14, parent.height - 4)
                radius: 2
                color: modelData.accent || "#465663"
                opacity: modelData.active ? 1.0 : 0.92
                antialiasing: true
            }

            Text {
                x: root.contentLeft + root.textInset
                width: Math.max(24, parent.width - root.contentLeft - (root.textInset + root.rightInset))
                height: parent.height
                text: modelData.text || ""
                color: modelData.active ? "#EEF5FA" : "#D4DCE3"
                font.pixelSize: 13
                font.italic: !!modelData.italic
                font.bold: !!modelData.active
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                renderType: Text.QtRendering
                clip: true
            }
        }
    }

}
