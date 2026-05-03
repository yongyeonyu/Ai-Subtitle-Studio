import QtQuick 2.15
import QtQuick.Controls 2.15

Item {
    id: root
    property string headerText: "큐 리스트 : (0/0) - 0% 완료"
    property var queueItems: []
    clip: true

    Rectangle {
        anchors.fill: parent
        color: "#11181C"
        border.color: "#2D3942"
        border.width: 1
        radius: 7
        antialiasing: true
    }

    Column {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 7

        Text {
            width: parent.width
            text: root.headerText
            color: "#F5F7FA"
            font.pixelSize: 11
            font.bold: true
            elide: Text.ElideRight
        }

        Row {
            width: parent.width
            spacing: 3
            Text {
                width: 30
                text: "순서"
                color: "#8E98A3"
                font.pixelSize: 9
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
            }
            Text {
                width: Math.max(62, parent.width - 104)
                text: "파일명"
                color: "#8E98A3"
                font.pixelSize: 9
                font.bold: true
                elide: Text.ElideRight
            }
            Text {
                width: 62
                text: "시간"
                color: "#8E98A3"
                font.pixelSize: 9
                font.bold: true
                horizontalAlignment: Text.AlignRight
                elide: Text.ElideRight
            }
        }

        Rectangle {
            width: parent.width
            height: 1
            color: "#2D3942"
        }

        ListView {
            id: list
            width: parent.width
            height: parent.height - y
            clip: true
            model: root.queueItems
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {
                policy: list.contentHeight > list.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
                width: 6
            }

            delegate: Rectangle {
                width: list.width
                height: 48
                color: index % 2 === 0 ? "#151C20" : "#10161A"
                radius: 6

                Row {
                    anchors.fill: parent
                    anchors.leftMargin: 6
                    anchors.rightMargin: 6
                    spacing: 6

                    Text {
                        width: 30
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.order || (index + 1)
                        color: modelData.done ? "#34C759" : "#FFCC44"
                        font.pixelSize: 10
                        font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideRight
                    }

                    Column {
                        width: Math.max(62, parent.width - 110)
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 3

                        Text {
                            width: parent.width
                            text: modelData.file || "-"
                            color: "#F5F7FA"
                            font.pixelSize: 10
                            font.bold: false
                            elide: Text.ElideMiddle
                        }

                        Text {
                            width: parent.width
                            text: modelData.done ? "완료" : (modelData.statusDisplay || modelData.status || "대기 중")
                            color: modelData.done ? "#34C759" : "#8E98A3"
                            font.pixelSize: 8
                            font.bold: false
                            elide: Text.ElideRight
                        }
                    }

                    Text {
                        width: 62
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.eta || modelData.statusDisplay || modelData.status || "-"
                        color: modelData.done ? "#34C759" : "#FFCC44"
                        font.pixelSize: 10
                        font.bold: true
                        horizontalAlignment: Text.AlignRight
                        elide: Text.ElideRight
                    }
                }
            }

            Text {
                anchors.centerIn: parent
                visible: root.queueItems.length === 0
                text: "대기 중"
                color: "#6F767D"
                font.pixelSize: 10
                font.bold: true
            }
        }
    }
}
