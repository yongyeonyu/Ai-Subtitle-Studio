import QtQuick 2.15

Item {
    id: root
    property var tabItems: []
    property int currentIndex: 0
    property string accentColor: "#2D8CFF"
    signal tabTriggered(int index)

    height: 44

    Rectangle {
        anchors.fill: parent
        radius: 14
        color: "#121C22"
        border.color: "#25343D"
        border.width: 1
        antialiasing: true
    }

    Row {
        id: row
        anchors.fill: parent
        anchors.margins: 5
        spacing: 6

        Repeater {
            model: root.tabItems

            Rectangle {
                required property int index
                required property var modelData

                width: Math.max(96, label.implicitWidth + 28)
                height: row.height
                radius: 11
                color: index === root.currentIndex ? "#1B2830" : "#1A252D"
                border.color: index === root.currentIndex ? root.accentColor : "#31434E"
                border.width: 1
                antialiasing: true

                Text {
                    id: label
                    anchors.centerIn: parent
                    text: String((parent.modelData && parent.modelData.title) || "")
                    color: index === root.currentIndex ? "#F4F7FA" : "#A6B7C1"
                    font.pixelSize: 12
                    font.bold: true
                    elide: Text.ElideRight
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: root.tabTriggered(parent.index)
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                }
            }
        }
    }
}
