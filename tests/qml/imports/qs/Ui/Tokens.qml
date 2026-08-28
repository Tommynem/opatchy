pragma Singleton

import QtQuick

QtObject {
  readonly property color foreground: "black"
  readonly property color urgent: "red"
  readonly property var font: ({ family: "Sans Serif", body: 14, bodySmall: 12, caption: 10, display: 18 })
  readonly property var spacing: ({ xs: 4, sm: 8, panelGap: 8, controlHeight: 28, controlPaddingY: 4 })
  function space(value) { return value }
}
