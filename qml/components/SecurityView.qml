import QtQuick
import qs.Ui

Item {
  id: root

  property var snapshot: null
  property double currentTime: Date.now()
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  readonly property var view: presentation.view

  implicitHeight: content.implicitHeight

  Column {
    id: content
    width: parent.width
    spacing: Style.spacing.sm

    Text {
      width: parent.width
      text: root.view.statusText
      textFormat: Text.PlainText
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
      wrapMode: Text.Wrap
      maximumLineCount: 3
      elide: Text.ElideRight
    }

    Text {
      width: parent.width
      text: root.view.archCoverage.text + "; observed " + root.view.archCoverage.ageText + ". " + root.view.kevCoverage.text + "; observed " + root.view.kevCoverage.ageText + "."
      textFormat: Text.PlainText
      color: Qt.darker(root.foreground, 1.4)
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.Wrap
      maximumLineCount: 3
      elide: Text.ElideRight
    }

    Repeater {
      model: root.view.groups

      delegate: Item {
        required property var modelData
        width: parent.width
        implicitHeight: findings.implicitHeight

        Column {
          id: findings
          width: parent.width
          spacing: Style.spacing.sm

          Repeater {
            model: modelData.findings

            delegate: SecurityFindingRow {
              required property var modelData
              width: parent.width
              group: parent.parent.modelData
              finding: modelData
              foreground: root.foreground
              fontFamily: root.fontFamily
            }
          }
        }
      }
    }
  }

  SecurityViewPresentation {
    id: presentation
    snapshot: root.snapshot
    currentTime: root.currentTime
  }
}
