import QtQuick

Item {
  property var bar: null
  property string moduleName: ""
  property var settings: ({})
  property string ipcTarget: ""
  property bool manageIpc: true
  property bool opened: false
  property bool popoutSwitchClosing: false
  property color barForeground: "black"
  property alias controller: controller

  QtObject {
    id: controller
    function show() { root.opened = true }
    function hide() { root.opened = false }
  }

  function open() { controller.show() }
  function close() { controller.hide() }
  function toggle() { opened ? close() : open() }
  function setting(name, fallback) {
    const value = settings ? settings[name] : undefined
    return value === undefined || value === null ? fallback : value
  }
}
