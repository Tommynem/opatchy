import QtQuick
import "../models/SecurityViewModel.js" as SecurityViewModel

QtObject {
  property var snapshot: null
  property double currentTime: Date.now()
  readonly property var view: SecurityViewModel.securityView(snapshot, currentTime)
}
