pragma Singleton

import QtQuick

QtObject {
  readonly property var font: ({ family: "Sans Serif", body: 14, bodySmall: 13, caption: 10, title: 16, display: 28 })
  readonly property var spacing: ({ xxs: 2, xs: 4, sm: 8, md: 12, panelGap: 8, controlHeight: 28, controlPaddingX: 12, controlPaddingY: 7 })
  function space(value) { return Math.round(value * 14 / 12) }
}
