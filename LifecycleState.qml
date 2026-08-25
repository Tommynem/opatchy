import QtQml

QtObject {
  required property var shell
  required property var manifest

  readonly property var service: shell && manifest && typeof shell.serviceFor === "function"
    ? shell.serviceFor(manifest.id)
    : null
  readonly property bool serviceAvailable: service !== null
  readonly property string statusText: serviceAvailable ? "Opatchy" : "Service unavailable"
}
