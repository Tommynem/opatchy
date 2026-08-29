import QtQuick
import "../models/UpdateViewModel.js" as UpdateViewModel

QtObject {
  property var row: ({})
  readonly property string label: value(row.label, "Not recorded")
  readonly property string detailsText: value(row.source, "Unknown source") + " | " + value(row.installed, "Not recorded") + " -> " + value(row.candidate, "Not recorded")
  readonly property string scanText: value(row.installed, "Not recorded") + " -> " + value(row.candidate, "Not recorded") + " | " + value(row.source, "Unknown source")
  readonly property string metaText: value(row.watchText, "Watch: unavailable") + " | " + value(row.healthText, "Evidence: unavailable")
  readonly property string identity: value(row.identity, "Unknown identity")

  function value(text, fallback) {
    return typeof text === "string" && text.length > 0 ? UpdateViewModel.presentationText(text) : fallback
  }
}
