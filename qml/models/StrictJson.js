.pragma library

var MAX_JSON_DEPTH = 100

function hasDuplicateObjectKey(text) {
  var scanner = { text: text, index: 0, duplicate: false, depth: 0 }
  if (typeof text !== "string") return false
  scanSpace(scanner)
  scanValue(scanner)
  scanSpace(scanner)
  return scanner.duplicate
}

function scanValue(scanner) {
  if (scanner.duplicate || scanner.index >= scanner.text.length) return false
  var character = scanner.text.charAt(scanner.index)
  if (character === "{") return scanObject(scanner)
  if (character === "[") return scanArray(scanner)
  if (character === "\"") return scanString(scanner) !== null
  if (character === "t") return scanLiteral(scanner, "true")
  if (character === "f") return scanLiteral(scanner, "false")
  if (character === "n") return scanLiteral(scanner, "null")
  return scanNumber(scanner)
}

function scanObject(scanner) {
  if (!enter(scanner)) return false
  scanner.index += 1
  scanSpace(scanner)
  var keys = []
  if (scanner.text.charAt(scanner.index) === "}") {
    scanner.index += 1
    scanner.depth -= 1
    return true
  }
  while (scanner.index < scanner.text.length) {
    var key = scanString(scanner)
    if (key === null) return leave(scanner, false)
    if (keys.indexOf(key) !== -1) scanner.duplicate = true
    keys.push(key)
    scanSpace(scanner)
    if (scanner.text.charAt(scanner.index) !== ":") return leave(scanner, false)
    scanner.index += 1
    scanSpace(scanner)
    if (!scanValue(scanner)) return leave(scanner, false)
    scanSpace(scanner)
    var separator = scanner.text.charAt(scanner.index)
    if (separator === "}") {
      scanner.index += 1
      return leave(scanner, true)
    }
    if (separator !== ",") return leave(scanner, false)
    scanner.index += 1
    scanSpace(scanner)
  }
  return leave(scanner, false)
}

function scanArray(scanner) {
  if (!enter(scanner)) return false
  scanner.index += 1
  scanSpace(scanner)
  if (scanner.text.charAt(scanner.index) === "]") {
    scanner.index += 1
    scanner.depth -= 1
    return true
  }
  while (scanner.index < scanner.text.length) {
    if (!scanValue(scanner)) return leave(scanner, false)
    scanSpace(scanner)
    var separator = scanner.text.charAt(scanner.index)
    if (separator === "]") {
      scanner.index += 1
      return leave(scanner, true)
    }
    if (separator !== ",") return leave(scanner, false)
    scanner.index += 1
    scanSpace(scanner)
  }
  return leave(scanner, false)
}

function scanString(scanner) {
  if (scanner.text.charAt(scanner.index) !== "\"") return null
  scanner.index += 1
  var value = ""
  while (scanner.index < scanner.text.length) {
    var character = scanner.text.charAt(scanner.index)
    scanner.index += 1
    if (character === "\"") return value
    if (character.charCodeAt(0) < 0x20) return null
    if (character !== "\\") {
      value += character
      continue
    }
    if (scanner.index >= scanner.text.length) return null
    var escape = scanner.text.charAt(scanner.index)
    scanner.index += 1
    if (escape === "u") {
      var hex = scanner.text.substr(scanner.index, 4)
      if (!/^[0-9a-fA-F]{4}$/.test(hex)) return null
      value += String.fromCharCode(parseInt(hex, 16))
      scanner.index += 4
      continue
    }
    var escapes = { "\"": "\"", "\\": "\\", "/": "/", b: "\b", f: "\f", n: "\n", r: "\r", t: "\t" }
    if (!(escape in escapes)) return null
    value += escapes[escape]
  }
  return null
}

function scanLiteral(scanner, literal) {
  if (scanner.text.substr(scanner.index, literal.length) !== literal) return false
  scanner.index += literal.length
  return true
}

function scanNumber(scanner) {
  var match = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/.exec(scanner.text.substring(scanner.index))
  if (match === null) return false
  scanner.index += match[0].length
  return true
}

function scanSpace(scanner) {
  while (scanner.index < scanner.text.length && /[ \t\n\r]/.test(scanner.text.charAt(scanner.index))) scanner.index += 1
}

function enter(scanner) {
  scanner.depth += 1
  return scanner.depth <= MAX_JSON_DEPTH
}

function leave(scanner, result) {
  scanner.depth -= 1
  return result
}
