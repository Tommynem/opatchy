.pragma library

function scanArguments(settings) {
  return [
    "--notify-permanent", booleanValue(settings, "notifyPermanent") ? "true" : "false",
    "--notify-security", booleanValue(settings, "notifySecurity") ? "true" : "false",
    "--security-minimum-severity", severityValue(settings),
    "--enable-cisa-kev", booleanValue(settings, "enableCisaKev") ? "true" : "false",
  ]
}

function booleanValue(settings, key) {
  return !settings || typeof settings[key] !== "boolean" ? true : settings[key]
}

function severityValue(settings) {
  return settings && settings.securityMinimumSeverity === "critical" ? "critical" : "high"
}
