import QtQuick

Item {
    id: root
    property var segments: []
    property real pps: 200
    property real fps: 30
    property real viewportX: 0
    property string fontFamily: "Arial"
    property int segmentFontPixelSize: 14

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
                color: modelData.fill || "#242A31"
                opacity: Math.max(0.0, Math.min(1.0, modelData.alpha / 255.0))
                border.color: modelData.border || "#3A4650"
                border.width: modelData.borderWidth || 1
                radius: 0
            }

            Loader {
                active: !!modelData.showScoreSegment
                sourceComponent: scoreSegmentComponent
            }

            Loader {
                anchors.fill: parent
                active: !!modelData.showText
                sourceComponent: segmentTextComponent
            }

            Loader {
                active: !!modelData.showScoreText
                sourceComponent: scoreTextComponent
            }

            Loader {
                anchors.fill: parent
                active: !!modelData.showConfidenceChips
                sourceComponent: confidenceChipsComponent
            }

            Loader {
                active: !!modelData.showSpeakerBar
                sourceComponent: speakerBarComponent
            }

            Loader {
                active: !!modelData.showHandles
                sourceComponent: handlesComponent
            }
        }
    }

    Component {
        id: scoreSegmentComponent

        Rectangle {
            x: 0
            y: modelData.scoreSegmentY - modelData.y
            width: parent.width
            height: Math.max(1, modelData.scoreSegmentH)
            color: "#1F282E"
            opacity: 0.82
            border.color: "#52606C"
            border.width: 1
            radius: 0
        }
    }

    Component {
        id: segmentTextComponent

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
            font.pixelSize: root.segmentFontPixelSize
            elide: parent.width < 164 ? Text.ElideRight : Text.ElideNone
            wrapMode: parent.width < 164 ? Text.NoWrap : Text.WordWrap
            verticalAlignment: parent.width < 164 ? Text.AlignVCenter : Text.AlignTop
            clip: true
        }
    }

    Component {
        id: scoreTextComponent

        Text {
            x: 0
            y: modelData.scoreY - modelData.y
            width: parent.width
            height: 15
            text: modelData.scoreText
            color: modelData.scoreColor
            font.family: root.fontFamily
            font.pixelSize: 11
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            clip: true

            Text {
                anchors.fill: parent
                anchors.leftMargin: 1
                anchors.topMargin: 1
                text: parent.text
                color: "#000000"
                opacity: 0.65
                font.family: parent.font.family
                font.pixelSize: parent.font.pixelSize
                font.bold: parent.font.bold
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                z: -1
            }
        }
    }

    Component {
        id: confidenceChipsComponent

        Item {
            anchors.fill: parent
            Repeater {
                model: segItem.confidenceChips

                Rectangle {
                    x: 5 + (index * (Math.max(6, Math.min(18, (segItem.width - 10) / Math.max(1, segItem.confidenceChips.length))) + 2))
                    y: 3
                    width: Math.max(6, Math.min(18, (segItem.width - 10) / Math.max(1, segItem.confidenceChips.length)))
                    height: 4
                    color: modelData.color || "#8E8E93"
                    radius: 1
                }
            }
        }
    }

    Component {
        id: speakerBarComponent

        Rectangle {
            id: speakerBar
            property var speakerRows: modelData.speakerRows || []
            property bool speakerTextVisible: !!modelData.showSpeakerText
            x: 0
            y: modelData.speakerY - modelData.y
            width: parent.width
            height: modelData.speakerH
            color: modelData.speakerFill || "#1F252A"
            border.color: "#303840"
            border.width: 1

            Repeater {
                model: speakerBar.speakerRows.length > 0 ? speakerBar.speakerRows : [{"name": modelData.speakerText || "", "color": "#8E8E93", "fill": modelData.speakerFill || "#1F252A"}]

                Rectangle {
                    x: 0
                    y: index * (speakerBar.height / Math.max(1, speakerBar.speakerRows.length || 1))
                    width: speakerBar.width
                    height: speakerBar.height / Math.max(1, speakerBar.speakerRows.length || 1)
                    color: modelData.fill || "#1F252A"
                    clip: true

                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: 7
                        anchors.rightMargin: 7
                        text: modelData.name || ""
                        color: modelData.color || "#8E8E93"
                        font.family: root.fontFamily
                        font.pixelSize: speakerBar.speakerRows.length > 1 ? 9 : 10
                        font.bold: true
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                        clip: true
                        visible: speakerBar.speakerTextVisible
                    }
                }
            }
        }
    }

    Component {
        id: handlesComponent

        Item {
            anchors.fill: parent
            Rectangle {
                x: -2
                y: 0
                width: 4
                height: parent.height
                color: "#44FF88"
            }

            Rectangle {
                x: parent.width - 2
                y: 0
                width: 4
                height: parent.height
                color: "#44FF88"
            }
        }
    }
}
