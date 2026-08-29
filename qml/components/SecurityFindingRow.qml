import QtQuick
import qs.Commons
import qs.Ui

Item {
  id: root

  property var group: ({})
  property var finding: ({})
  property var starState: null
  property string confirmedMode: "off"
  property bool watchable: false
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  readonly property var watchRequest: finding && finding.watchRequest ? finding.watchRequest : null
  readonly property string effectiveMode: starState && watchRequest
    ? starState.modeFor(watchRequest.itemId, confirmedMode)
    : confirmedMode
  readonly property bool canWatchForFixedVersion: watchRequest !== null && watchable
    && (!starState || !starState.pending) && effectiveMode === "off"
  readonly property Item primaryControl: fixedVersionWatch.visible ? fixedVersionWatch : null
  property alias fixedVersionWatch: fixedVersionWatch
  property alias watchUnavailable: watchUnavailable

  implicitHeight: details.implicitHeight + Style.spacing.controlPaddingY * 2
  height: implicitHeight

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

    Button {
      id: fixedVersionWatch
      objectName: root.watchRequest ? "security-fixed-watch-" + root.watchRequest.itemId + "-" + root.watchRequest.securityAdvisory : ""
      visible: root.canWatchForFixedVersion
      width: Math.min(parent.width, implicitWidth)
      text: root.watchRequest ? "Watch fixed " + root.watchRequest.fixedVersion : "Watch fixed version"
      tooltipText: root.watchRequest
        ? "Create a temporary watch for " + root.watchRequest.securityAdvisory + " evidence fixed in " + root.watchRequest.fixedVersion + "."
        : "Fixed-version watch evidence is unavailable."
      foreground: root.foreground
      fontFamily: root.fontFamily
      fontSize: Style.font.bodySmall
      focusable: true
      bordered: true
      onClicked: if (root.starState) root.starState.requestSecurityCondition(root.watchRequest, root.confirmedMode, root.watchable)
    }

    Text {
      id: watchUnavailable
      visible: !root.canWatchForFixedVersion
      width: parent.width
      text: root.watchRequest === null
        ? "Fixed-version watch unavailable: usable advisory, CVE, and fixed-version evidence is required."
        : root.starState && root.starState.pending
          ? "Fixed-version watch request is pending."
          : root.effectiveMode === "temporary"
            ? "Fixed-version watch unavailable: this package already has a temporary watch."
            : root.effectiveMode === "permanent"
              ? "Fixed-version watch unavailable: this package already has a permanent watch."
              : "Fixed-version watch unavailable: a current unconfigured package watch is required."
      textFormat: Text.PlainText
      color: Qt.darker(root.foreground, 1.4)
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.Wrap
      maximumLineCount: 2
      elide: Text.ElideRight
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
