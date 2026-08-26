import QtQuick
import "../models/UpdateViewModel.js" as UpdateViewModel

QtObject {
  property var state: null
  readonly property var view: state
    ? UpdateViewModel.inventoryState(state.inventory, state.source, state.generationId)
    : ({ kind: "empty", rows: [], total: 0, summaryText: "Cached inventory is unavailable." })
}
