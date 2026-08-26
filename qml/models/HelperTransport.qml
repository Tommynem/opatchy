import QtQml
import QtQuick
import Quickshell.Io

QtObject {
  id: root

  readonly property int maxProtocolBytes: 5 * 1024 * 1024
  readonly property int maxDiagnosticBytes: 16 * 1024
  property string helperEntrypoint: ""
  property int timeoutMs: 120000
  readonly property bool running: helperProcess.running
  property var activeOperation: null
  property string stdoutText: ""
  property string stderrText: ""
  property int stdoutBytes: 0
  property int stderrBytes: 0
  property bool outputTooLarge: false
  property bool timedOut: false

  signal completed(var operation, var result)

  function run(operation) {
    if (helperProcess.running || helperEntrypoint === "") return false
    activeOperation = operation
    stdoutText = ""
    stderrText = ""
    stdoutBytes = 0
    stderrBytes = 0
    outputTooLarge = false
    timedOut = false
    helperProcess.command = ["/usr/bin/python3", helperEntrypoint].concat(operation.argv)
    helperProcess.running = true
    timeoutTimer.restart()
    return true
  }

  function stop() {
    timeoutTimer.stop()
    activeOperation = null
    if (helperProcess.running) helperProcess.running = false
  }

  function collectStdout(data) {
    if (outputTooLarge) return
    var text = String(data)
    stdoutBytes += utf8Length(text)
    if (stdoutBytes >= maxProtocolBytes) {
      outputTooLarge = true
      helperProcess.running = false
      return
    }
    stdoutText += text
  }

  function collectStderr(data) {
    var text = String(data)
    var remaining = maxDiagnosticBytes - stderrBytes
    if (remaining <= 0) return
    if (utf8Length(text) <= remaining) {
      stderrText += text
      stderrBytes += utf8Length(text)
      return
    }
    stderrText += text.substring(0, remaining)
    stderrBytes = maxDiagnosticBytes
  }

  function finish(exitCode) {
    timeoutTimer.stop()
    var operation = activeOperation
    activeOperation = null
    if (operation === null) return
    completed(operation, {
      exitCode: exitCode,
      stdout: stdoutText,
      stderr: stderrText,
      timedOut: timedOut,
      outputTooLarge: outputTooLarge
    })
  }

  function utf8Length(value) {
    var length = 0
    for (var index = 0; index < value.length; index += 1) {
      var code = value.charCodeAt(index)
      if (code < 0x80) length += 1
      else if (code < 0x800) length += 2
      else if (code >= 0xd800 && code <= 0xdbff && index + 1 < value.length
        && value.charCodeAt(index + 1) >= 0xdc00 && value.charCodeAt(index + 1) <= 0xdfff) {
        length += 4
        index += 1
      } else length += 3
    }
    return length
  }

  property Timer timeoutTimer: Timer {
    interval: root.timeoutMs
    repeat: false
    onTriggered: {
      root.timedOut = true
      if (helperProcess.running) helperProcess.running = false
    }
  }

  property Process helperProcess: Process {
    running: false
    stdout: SplitParser {
      splitMarker: ""
      onRead: function(data) { root.collectStdout(data) }
    }
    stderr: SplitParser {
      splitMarker: ""
      onRead: function(data) { root.collectStderr(data) }
    }
    onExited: function(exitCode) { Qt.callLater(function() { root.finish(exitCode) }) }
  }

  Component.onDestruction: stop()
}
