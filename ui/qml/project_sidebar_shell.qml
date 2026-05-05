import QtQuick 2.15

Item {
    id: root
    property string panelTitle: "Project"
    property string accentText: "GPU Shell"
    clip: true

    Rectangle {
        anchors.fill: parent
        color: "#10181D"
    }

    Rectangle {
        width: 2
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        color: "#34C759"
        opacity: 0.9
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 64
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#17252B" }
            GradientStop { position: 1.0; color: "#10181D" }
        }
    }

    Column {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 12
        spacing: 5

        Text {
            width: parent.width
            text: root.panelTitle
            color: "#EEF5FA"
            font.pixelSize: 13
            font.bold: true
            elide: Text.ElideRight
        }

        Text {
            width: parent.width
            text: root.accentText
            color: "#78D79B"
            font.pixelSize: 9
            font.bold: true
            opacity: 0.88
            elide: Text.ElideRight
        }
    }

    Repeater {
        model: 5
        Rectangle {
            x: 12
            y: 86 + index * 58
            width: Math.max(24, root.width - 24)
            height: 42
            radius: 7
            color: "#121D22"
            border.color: "#1E3138"
            border.width: 1
            opacity: 0.55
            antialiasing: true
        }
    }
}
