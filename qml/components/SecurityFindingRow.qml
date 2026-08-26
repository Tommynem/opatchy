import QtQuick
import qs.Ui

Item {
  id: root

  property var group: ({})
  property var finding: ({})
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family

  implicitHeight: details.implicitHeight + Style.spacing.controlPaddingY * 2

  Column {
    id: details
    width: parent.width
    spacing: Style.spacing.xs

    Text {
      width: parent.width
      text: presentation.packageName
      textFormat: Text.PlainText
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
      elide: Text.ElideRight
      maximumLineCount: 1
    }

    SafeExternalLink {
      width: parent.width
      linkKind: "arch-advisory"
      identifier: root.finding.advisoryId
      foreground: root.foreground
      fontFamily: root.fontFamily
      fontSize: Style.font.bodySmall
    }

    Text {
      width: parent.width
      text: presentation.versionText + " | " + presentation.statusText
      textFormat: Text.PlainText
      color: Qt.darker(root.foreground, 1.4)
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
      wrapMode: Text.Wrap
      maximumLineCount: 2
      elide: Text.ElideRight
    }

    Repeater {
      model: Array.isArray(root.finding.cveIds) ? root.finding.cveIds : []

      delegate: SafeExternalLink {
        required property string modelData
        width: parent.width
        linkKind: "cve"
        identifier: modelData
        foreground: root.foreground
        fontFamily: root.fontFamily
        fontSize: Style.font.caption
      }
    }

    Text {
      width: parent.width
      text: presentation.kevText + " " + presentation.provenanceText + " " + presentation.ageText + " " + presentation.coverageText
      textFormat: Text.PlainText
      color: Qt.darker(root.foreground, 1.4)
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.Wrap
      maximumLineCount: 4
      elide: Text.ElideRight
    }
  }

  SecurityFindingPresentation {
    id: presentation
    group: root.group
    finding: root.finding
  }
}
