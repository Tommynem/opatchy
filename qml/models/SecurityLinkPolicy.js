.pragma library

var ARCH_SECURITY_ORIGIN = "https://security.archlinux.org/"
var CVE_ORIGIN = "https://www.cve.org/CVERecord?id="

function linkFor(kind, identifier) {
  if (kind === "arch-advisory" && canonicalAverage(identifier)) {
    return ARCH_SECURITY_ORIGIN + identifier
  }
  if (kind === "cve" && canonicalCve(identifier)) {
    return CVE_ORIGIN + identifier
  }
  return null
}

function canonicalAverage(value) { return typeof value === "string" && value.length <= 128 && /^AVG-[0-9]+$/.test(value) }
function canonicalCve(value) { return typeof value === "string" && value.length <= 128 && /^CVE-[0-9]{4}-[0-9]{4,19}$/.test(value) }
