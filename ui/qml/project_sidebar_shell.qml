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
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 64
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#17252B" }
            GradientStop { position: 1.0; color: "#10181D" }
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
