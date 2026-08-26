pragma Singleton

import QtQuick

QtObject {
  readonly property color foreground: "black"
  readonly property var font: ({ family: "Sans Serif", body: 14, bodySmall: 12, caption: 10 })
  readonly property var spacing: ({ xs: 4, sm: 8, controlPaddingY: 4 })
}
