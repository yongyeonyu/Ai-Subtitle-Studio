import QtQuick 2.15

Item {
    id: root
    clip: true

    Rectangle {
        id: card
        anchors.fill: parent
        color: "#1B2429"
        border.color: "#3A4650"
        border.width: 1
        radius: 7
        antialiasing: true
    }

    Column {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 7

        Row {
            width: parent.width
            spacing: 7

            Rectangle {
                width: 20
                height: 20
                radius: 2
                color: "#11181C"
                Text {
                    anchors.centerIn: parent
                    text: "▣"
                    color: "#E8EEF5"
                    font.pixelSize: 10
                    font.bold: true
                }
            }

            Text {
                width: parent.width - 27
                text: "프로젝트 정보"
                color: "#F5F7FA"
                font.pixelSize: 12
                font.bold: true
                verticalAlignment: Text.AlignVCenter
                height: 20
                elide: Text.ElideRight
            }
        }

        Repeater {
            model: projectInfoSections
            delegate: Column {
                width: parent.width
                spacing: 3

                Text {
                    width: parent.width
                    text: modelData.title
                    color: "#34C759"
                    font.pixelSize: 10
                    font.bold: true
                    wrapMode: Text.NoWrap
                    elide: Text.ElideRight
                }

                Repeater {
                    model: modelData.rows
                    delegate: Text {
                        width: parent.width
                        text: modelData
                        color: "#A9B0B7"
                        font.pixelSize: 9
                        wrapMode: Text.Wrap
                    }
                }
            }
        }
    }
}
