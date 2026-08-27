import QtQml
import "../models/BarStatusModel.js" as BarStatusModel

QtObject {
  property var snapshot: null
  property bool refreshing: false
  property bool serviceAvailable: false
  readonly property var status: BarStatusModel.status(snapshot, refreshing, serviceAvailable)
}
