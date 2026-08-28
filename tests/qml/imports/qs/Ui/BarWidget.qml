import QtQuick

Item {
  property var bar: null
  property string moduleName: ""
  property var settings: ({})

  function setting(name, fallback) {
    const value = settings ? settings[name] : undefined
    return value === undefined || value === null ? fallback : value
  }
}
