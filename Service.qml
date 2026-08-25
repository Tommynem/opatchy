import QtQuick

Item {
  id: root

  property var shell: null
  property var manifest: null
  readonly property string sourceDir: manifest && typeof manifest.__sourceDir === "string"
    ? manifest.__sourceDir
    : ""
}
