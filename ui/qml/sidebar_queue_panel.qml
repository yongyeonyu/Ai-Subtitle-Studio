import QtQuick 2.15
import QtQuick.Controls 2.15

Item {
    id: root
    property string headerText: "큐 리스트 : (0/0) - 0% 완료"
    property var queueItems: []
    clip: true

    function activeQueueIndex() {
        for (var i = 0; i < root.queueItems.length; i++) {
            var item = root.queueItems[i]
            if (item && item.active && !item.done && !item.error)
                return i
        }
        return -1
    }

    function focusActiveQueueItem() {
        var idx = activeQueueIndex()
        if (idx >= 0 && idx < list.count) {
            list.currentIndex = idx
            list.positionViewAtIndex(idx, ListView.Center)
        }
    }

    function keycapOrder(value) {
        var numberValue = parseInt(value, 10)
        var raw = isNaN(numberValue) ? String(value || "") : ("0" + String(numberValue)).slice(-2)
        var out = ""
        for (var i = 0; i < raw.length; i++) {
            var ch = raw.charAt(i)
            if (ch >= "0" && ch <= "9")
                out += ch + "\uFE0F\u20E3"
            else
                out += ch
        }
        return out || "0\uFE0F\u20E3"
    }

    onQueueItemsChanged: activeFocusTimer.restart()

    Timer {
        id: activeFocusTimer
        interval: 20
        repeat: false
        onTriggered: root.focusActiveQueueItem()
    }

    Rectangle {
        anchors.fill: parent
        color: "#0F171B"
        border.color: "#31424A"
        border.width: 1
        radius: 8
        antialiasing: true
    }

    Column {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 9

        Text {
            width: parent.width
            text: root.headerText
            color: "#F5F7FA"
            font.pixelSize: 12
            font.bold: true
            elide: Text.ElideRight
        }

        ListView {
            id: list
            width: parent.width
            height: parent.height - y
            clip: true
            model: root.queueItems
            spacing: 6
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {
                id: queueScroll
                policy: list.contentHeight > list.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
                width: 7
                padding: 1
                minimumSize: 0.12

                background: Rectangle {
                    implicitWidth: 7
                    radius: 3
                    color: "#0A1013"
                    opacity: queueScroll.size < 1.0 ? 1.0 : 0.0
                }

                contentItem: Rectangle {
                    implicitWidth: 5
                    radius: 3
                    color: queueScroll.pressed ? "#74A9FF" : (queueScroll.hovered ? "#53636D" : "#33424A")
                    opacity: queueScroll.size < 1.0 ? 1.0 : 0.0
                }
            }

            delegate: Rectangle {
                id: queueCard
                property bool currentActive: index === root.activeQueueIndex() && modelData.active && !modelData.done && !modelData.error
                property string statusText: modelData.done ? "완료" : (modelData.statusDisplay || modelData.status || "대기 중")
                width: list.width - (list.contentHeight > list.height ? 6 : 0)
                height: 78
                color: modelData.done ? "#13261D" : (modelData.error ? "#291719" : (currentActive ? "#17242C" : "#121A1E"))
                border.color: modelData.done ? "#286B43" : (modelData.error ? "#6D2E35" : (currentActive ? "#FFD84D" : "#1D2A31"))
                border.width: currentActive ? 2 : 1
                radius: 6

                Column {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    anchors.topMargin: 8
                    anchors.bottomMargin: 8
                    spacing: 2

                    Row {
                        width: parent.width
                        height: 29
                        spacing: 4

                        Text {
                            id: orderText
                            width: implicitWidth
                            height: parent.height
                            text: root.keycapOrder(modelData.order || (index + 1))
                            color: "#CFEFFF"
                            font.pixelSize: 11
                            font.bold: true
                            verticalAlignment: Text.AlignTop
                        }

                        Text {
                            width: parent.width - orderText.width - 4
                            height: 29
                            text: modelData.file || "-"
                            color: "#F5F7FA"
                            font.pixelSize: 11
                            font.bold: true
                            wrapMode: Text.WrapAnywhere
                            maximumLineCount: 2
                            elide: Text.ElideRight
                        }
                    }

                    Item {
                        width: parent.width
                        height: 14
                        Text {
                            x: 0
                            width: parent.width
                            text: queueCard.statusText
                            color: modelData.done ? "#55D97A" : (modelData.error ? "#FF6B78" : (currentActive ? "#FFD84D" : "#9DB0BB"))
                            font.pixelSize: 9
                            font.bold: modelData.done || modelData.error || currentActive
                            horizontalAlignment: Text.AlignLeft
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                        }
                    }

                    Text {
                        width: parent.width
                        text: modelData.eta || "-"
                        color: modelData.done ? "#55D97A" : (modelData.error ? "#FF6B78" : "#FFD84D")
                        font.pixelSize: 10
                        font.bold: true
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
