import QtQuick

QtObject {
  property string tab: "Security"
  property bool browsing: false

  onTabChanged: browsing = false
}
