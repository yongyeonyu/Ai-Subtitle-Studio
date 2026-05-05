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
            rightMargin: queueScroll.visible ? 4 : 0
            ScrollBar.vertical: ScrollBar {
                id: queueScroll
                policy: list.contentHeight > list.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
                width: 8
                padding: 2
                minimumSize: 0.12

                background: Rectangle {
                    implicitWidth: 8
                    radius: 4
                    color: "#0A1013"
                    opacity: queueScroll.size < 1.0 ? 1.0 : 0.0
                }

                contentItem: Rectangle {
                    implicitWidth: 6
                    radius: 4
                    color: queueScroll.pressed ? "#74A9FF" : (queueScroll.hovered ? "#53636D" : "#33424A")
                    opacity: queueScroll.size < 1.0 ? 1.0 : 0.0
                }
            }

            delegate: Rectangle {
                id: queueCard
                property bool currentActive: index === root.activeQueueIndex() && modelData.active && !modelData.done && !modelData.error
                property string statusText: modelData.done ? "완료" : (modelData.statusDisplay || modelData.status || "대기 중")
                property color statusColor: modelData.done ? "#55D97A" : (modelData.error ? "#FF6B78" : (currentActive ? "#FFD84D" : "#9DB0BB"))
                property string timeText: modelData.eta || "-"
                width: list.width - (list.contentHeight > list.height ? 8 : 0)
                height: 86
                color: modelData.done ? "#13261D" : (modelData.error ? "#291719" : (currentActive ? "#17242C" : "#121A1E"))
                border.color: modelData.done ? "#286B43" : (modelData.error ? "#6D2E35" : (currentActive ? "#FFD84D" : "#1D2A31"))
                border.width: currentActive ? 2 : 1
                radius: 6

                Column {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    anchors.topMargin: 7
                    anchors.bottomMargin: 7
                    spacing: 4

                    Row {
                        width: parent.width
                        height: 22
                        spacing: 8

                        Rectangle {
                            id: orderChip
                            width: 34
                            height: 20
                            radius: 10
                            anchors.verticalCenter: parent.verticalCenter
                            color: currentActive ? "#244455" : "#17262D"
                            border.color: currentActive ? "#7CC5FF" : "#31424A"
                            border.width: 1

                            Text {
                                anchors.centerIn: parent
                                text: root.keycapOrder(modelData.order || (index + 1))
                                color: "#CFEFFF"
                                font.pixelSize: 10
                                font.bold: true
                            }
                        }

                        Item {
                            width: parent.width - orderChip.width - timeBadge.width - 16
                        }

                        Rectangle {
                            id: timeBadge
                            width: 84
                            height: 22
                            radius: 11
                            anchors.verticalCenter: parent.verticalCenter
                            color: modelData.done ? "#173222" : (modelData.error ? "#351C1F" : "#121E24")
                            border.color: modelData.done ? "#286B43" : (modelData.error ? "#6D2E35" : "#31424A")
                            border.width: 1

                            Text {
                                anchors.fill: parent
                                anchors.leftMargin: 8
                                anchors.rightMargin: 8
                                text: queueCard.timeText
                                color: queueCard.statusColor
                                font.pixelSize: 9
                                font.bold: true
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                elide: Text.ElideRight
                            }
                        }
                    }

                    Rectangle {
                        width: parent.width
                        height: 1
                        color: currentActive ? "#27414F" : "#1A272D"
                        opacity: 0.9
                    }

                    Text {
                        width: parent.width
                        height: 18
                        text: modelData.file || "-"
                        color: "#F5F7FA"
                        font.pixelSize: 11
                        font.bold: true
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideMiddle
                    }

                    Row {
                        width: parent.width
                        height: 16
                        spacing: 6

                        Rectangle {
                            width: 8
                            height: 8
                            radius: 4
                            anchors.verticalCenter: parent.verticalCenter
                            color: queueCard.statusColor
                        }

                        Text {
                            width: parent.width - 14
                            text: queueCard.statusText
                            color: queueCard.statusColor
                            font.pixelSize: 9
                            font.bold: modelData.done || modelData.error || currentActive
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                        }
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
