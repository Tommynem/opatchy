pragma Singleton

import QtQuick

QtObject {
  readonly property var font: ({ family: "Sans Serif", body: 14, bodySmall: 12, caption: 10, display: 18 })
  readonly property var spacing: ({ xxs: 2, xs: 4, sm: 8, md: 12, panelGap: 8, controlHeight: 28, controlPaddingY: 4 })
  function space(value) { return value }
}
