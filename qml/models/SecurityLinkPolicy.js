.pragma library

var ARCH_SECURITY_ORIGIN = "https://security.archlinux.org/"
var CVE_ORIGIN = "https://www.cve.org/CVERecord?id="

function linkFor(kind, identifier) {
  if (kind === "arch-advisory" && /^AVG-[0-9]+$/.test(identifier)) {
    return ARCH_SECURITY_ORIGIN + identifier
  }
  if (kind === "cve" && /^CVE-[0-9]{4}-[0-9]{4,}$/.test(identifier)) {
    return CVE_ORIGIN + identifier
  }
  return null
}
