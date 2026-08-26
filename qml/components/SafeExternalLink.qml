import QtQuick
import qs.Ui
import "../models/SecurityLinkPolicy.js" as SecurityLinkPolicy

Button {
  id: root

  property string linkKind: ""
  property string identifier: ""
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  property int fontSize: Style.font.bodySmall
  readonly property string constructedUrl: SecurityLinkPolicy.linkFor(linkKind, identifier) || ""

  text: identifier
  tooltipText: constructedUrl === "" ? "Link unavailable" : "Open official advisory details"
  enabled: constructedUrl !== ""
  focusable: true
  bordered: true
  onClicked: if (constructedUrl !== "") Qt.openUrlExternally(constructedUrl)
}
