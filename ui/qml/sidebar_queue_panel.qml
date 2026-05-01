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
        anchors.margins: 8
        spacing: 6

        Text {
            width: parent.width
            text: root.headerText
            color: "#F5F7FA"
            font.pixelSize: 10
            font.bold: true
            elide: Text.ElideRight
        }

        Row {
            width: parent.width
            spacing: 3
            Text {
                width: 34
                text: "순서"
                color: "#8E98A3"
                font.pixelSize: 9
                font.bold: true
                elide: Text.ElideRight
            }
            Text {
                width: Math.max(40, parent.width - 107)
                text: "파일명"
                color: "#8E98A3"
                font.pixelSize: 9
                font.bold: true
                elide: Text.ElideRight
            }
            Text {
                width: 64
                text: "예상시간"
                color: "#8E98A3"
                font.pixelSize: 9
                font.bold: true
                horizontalAlignment: Text.AlignLeft
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
                height: 38
                color: index % 2 === 0 ? "#151C20" : "#10161A"
                radius: 4

                Row {
                    anchors.fill: parent
                    anchors.leftMargin: 5
                    anchors.rightMargin: 3
                    spacing: 3

                    Text {
                        width: 34
                        height: parent.height
                        text: modelData.order || (index + 1)
                        color: modelData.done || (modelData.status || "").indexOf("완료") >= 0 ? "#34C759" : "#FFCC44"
                        font.pixelSize: 9
                        font.bold: true
                        verticalAlignment: Text.AlignVCenter
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideRight
                        maximumLineCount: 1
                    }
                    Text {
                        width: Math.max(40, parent.width - 107)
                        height: parent.height
                        text: modelData.file || "-"
                        color: modelData.done || (modelData.status || "").indexOf("완료") >= 0 ? "#34C759" : "#FFCC44"
                        font.pixelSize: 8
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideMiddle
                        wrapMode: Text.WrapAnywhere
                        maximumLineCount: 2
                    }
                    Text {
                        width: 64
                        height: parent.height
                        text: modelData.eta || "-"
                        color: modelData.done || (modelData.status || "").indexOf("완료") >= 0 ? "#34C759" : "#FFCC44"
                        font.pixelSize: 8
                        verticalAlignment: Text.AlignVCenter
                        horizontalAlignment: Text.AlignLeft
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
