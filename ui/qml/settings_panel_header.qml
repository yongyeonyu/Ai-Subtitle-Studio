import QtQuick 2.15

Item {
    id: root
    property string titleText: "Settings"
    property string subtitleText: "QML SceneGraph panel"
    property string badgeText: "GPU"
    height: 60
    clip: true

    Rectangle {
        anchors.fill: parent
        radius: 14
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#17252B" }
            GradientStop { position: 1.0; color: "#10181D" }
        }
        border.color: "#2D4048"
        border.width: 1
        antialiasing: true
    }

    Rectangle {
        width: 4
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        radius: 2
        color: "#34C759"
        opacity: 0.95
    }

    Column {
        anchors.left: parent.left
        anchors.right: badge.left
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: 16
        anchors.rightMargin: 12
        spacing: 4

        Text {
            width: parent.width
            text: root.titleText
            color: "#F5F7FA"
            font.pixelSize: 15
            font.bold: true
            elide: Text.ElideRight
        }

        Text {
            width: parent.width
            text: root.subtitleText
            color: "#9FB0BA"
            font.pixelSize: 10
            font.bold: true
            elide: Text.ElideRight
        }
    }

    Rectangle {
        id: badge
        width: Math.max(56, badgeTextItem.implicitWidth + 20)
        height: 24
        radius: 12
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.rightMargin: 14
        color: "#14261D"
        border.color: "#2F9E58"
        border.width: 1
        antialiasing: true

        Text {
            id: badgeTextItem
            anchors.centerIn: parent
            text: root.badgeText
            color: "#85E3A5"
            font.pixelSize: 10
            font.bold: true
            elide: Text.ElideRight
        }
    }
}
