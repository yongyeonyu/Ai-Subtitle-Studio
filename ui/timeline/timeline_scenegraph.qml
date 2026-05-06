import QtQuick

Item {
    id: root
    property var segments: []
    property real pps: 200
    property real fps: 30
    property real viewportX: 0
    property string fontFamily: "Arial"

    Repeater {
        model: root.segments

        Item {
            id: segItem
            property var confidenceChips: modelData.confidenceChips || []
            x: modelData.x - root.viewportX
            y: modelData.y
            width: Math.max(2, modelData.w)
            height: Math.max(1, modelData.h)
            visible: x + width >= -64 && x <= root.width + 64

            Rectangle {
                id: body
                anchors.fill: parent
                color: modelData.fill
                opacity: Math.max(0.0, Math.min(1.0, modelData.alpha / 255.0))
                border.color: modelData.border
                border.width: modelData.borderWidth
                radius: 0
            }

            Text {
                anchors.left: parent.left
                anchors.leftMargin: 10
                anchors.right: parent.right
                anchors.rightMargin: 10
                anchors.top: parent.top
                anchors.topMargin: (segItem.confidenceChips.length > 0 && parent.width >= 72) ? 12 : 5
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 5
                text: modelData.text
                color: modelData.textColor
                font.family: root.fontFamily
                font.pixelSize: modelData.preview ? 11 : 12
                elide: parent.width < 164 ? Text.ElideRight : Text.ElideNone
                wrapMode: parent.width < 164 ? Text.NoWrap : Text.WordWrap
                verticalAlignment: parent.width < 164 ? Text.AlignVCenter : Text.AlignTop
                clip: true
                visible: parent.width >= 44
            }

            Repeater {
                model: parent.width >= 72 ? segItem.confidenceChips : []

                Rectangle {
                    x: 5 + (index * (Math.max(6, Math.min(18, (segItem.width - 10) / Math.max(1, segItem.confidenceChips.length))) + 2))
                    y: 3
                    width: Math.max(6, Math.min(18, (segItem.width - 10) / Math.max(1, segItem.confidenceChips.length)))
                    height: 4
                    color: modelData.color || "#8E8E93"
                    radius: 1
                }
            }

            Rectangle {
                x: 0
                y: modelData.speakerY - modelData.y
                width: parent.width
                height: modelData.speakerH
                color: modelData.speakerFill
                border.color: "#2D3942"
                border.width: 1
                visible: modelData.showSpeaker

                Text {
                    anchors.fill: parent
                    anchors.leftMargin: 6
                    anchors.rightMargin: 6
                    text: modelData.speakerText
                    color: "#DCE3EA"
                    font.family: root.fontFamily
                    font.pixelSize: 10
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                    clip: true
                }
            }

            Rectangle {
                x: -2
                y: 0
                width: 4
                height: parent.height
                color: "#44FF88"
                visible: modelData.showHandles
            }

            Rectangle {
                x: parent.width - 2
                y: 0
                width: 4
                height: parent.height
                color: "#44FF88"
                visible: modelData.showHandles
            }
        }
    }
}
