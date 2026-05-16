import QtQuick 2.15
import "AppPalette.js" as Palette

Item {
    id: root
    property real playheadX: 0
    property string lineColor: "#FF4444"
    property bool playheadBusy: false
    property bool visiblePlayhead: true
    property bool centerLocked: false
    clip: false

    Item {
        id: playheadVisual
        visible: root.visiblePlayhead
        x: (root.centerLocked ? (root.width / 2.0) : root.playheadX)
        y: 0
        width: 1
        height: root.height

        Behavior on x {
            SmoothedAnimation {
                velocity: 2400
                maximumEasingTime: 72
            }
        }

        Rectangle {
            x: -1
            y: 0
            width: 2
            height: root.height
            color: root.lineColor
            antialiasing: false
        }

        Rectangle {
            x: -7
            y: 2
            width: 14
            height: 14
            radius: 7
            color: root.playheadBusy ? Palette.danger : Palette.warning
            border.color: "#FFFFFF"
            border.width: 1
            antialiasing: true
        }
    }
}
