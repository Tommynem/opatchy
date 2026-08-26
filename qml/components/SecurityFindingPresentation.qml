import QtQuick
import "../models/SecurityViewModel.js" as SecurityViewModel

QtObject {
  property var group: ({})
  property var finding: ({})
  readonly property string packageName: value(group.packageName)
  readonly property string versionText: value(finding.versionText)
  readonly property string statusText: "Status: " + value(finding.status) + " | Type: " + value(finding.type)
  readonly property string provenanceText: "Arch provenance: " + value(finding.provenance) + " | KEV provenance: " + value(finding.kevProvenance)
  readonly property string ageText: "Arch evidence observed " + value(finding.ageText)
  readonly property string coverageText: value(finding.sourceCoverageText)
  readonly property string kevText: value(finding.kevText)

  function value(text) {
    return typeof text === "string" && text.length > 0 ? SecurityViewModel.presentationText(text) : "Not recorded"
  }
}
