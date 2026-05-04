import QtQuick 2.15

Item {
    id: root
    property int playheadX: 0
    property string lineColor: "#FF4444"
    property bool playheadBusy: false
    property bool visiblePlayhead: true
    clip: false

    Rectangle {
        visible: root.visiblePlayhead
        x: root.playheadX - 1
        y: 0
        width: 2
        height: root.height
        color: root.lineColor
    }

    Rectangle {
        visible: root.visiblePlayhead
        x: root.playheadX - 7
        y: 2
        width: 14
        height: 14
        radius: 7
        color: root.playheadBusy ? "#FF453A" : "#FFCC00"
        border.color: "#FFFFFF"
        border.width: 1
        antialiasing: true
    }
}
