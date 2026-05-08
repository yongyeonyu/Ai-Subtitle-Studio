import QtQuick 2.15

Item {
    id: root
    property var actions: []
    property bool compact: false
    signal actionTriggered(string actionId)

    height: compact ? 38 : 52

    Rectangle {
        anchors.fill: parent
        radius: compact ? 12 : 15
        color: "#121C22"
        border.color: "#25343D"
        border.width: 1
        antialiasing: true
    }

    Row {
        id: row
        anchors.fill: parent
        anchors.margins: compact ? 5 : 7
        spacing: compact ? 5 : 7

        Repeater {
            model: root.actions

            Rectangle {
                required property var modelData

                property string actionId: String((modelData && modelData.id) || "")
                property string title: String((modelData && modelData.title) || "")
                property string kind: String((modelData && modelData.kind) || "secondary")
                property bool enabledState: modelData ? modelData.enabled !== false : true

                width: Math.max(root.compact ? 76 : 98, titleText.implicitWidth + (root.compact ? 24 : 30))
                height: row.height
                radius: root.compact ? 10 : 13
                color: {
                    if (!enabledState) return "#182228"
                    if (kind === "primary") return "#1E7CF0"
                    if (kind === "danger") return "#AA2D2D"
                    return "#1B2830"
                }
                border.color: {
                    if (!enabledState) return "#24323A"
                    if (kind === "primary") return "#4FA1FF"
                    if (kind === "danger") return "#FF6666"
                    return "#324552"
                }
                border.width: 1
                opacity: enabledState ? 1.0 : 0.55
                antialiasing: true

                Text {
                    id: titleText
                    anchors.centerIn: parent
                    text: parent.title
                    color: parent.kind === "primary" ? "#FFFFFF" : "#EAF1F5"
                    font.pixelSize: root.compact ? 12 : 13
                    font.bold: true
                    elide: Text.ElideRight
                }

                MouseArea {
                    anchors.fill: parent
                    enabled: parent.enabledState
                    hoverEnabled: true
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: root.actionTriggered(parent.actionId)
                }
            }
        }
    }
}
