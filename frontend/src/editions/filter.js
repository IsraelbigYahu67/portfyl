export function enabledEditionEntries(entries, capabilities) {
  const enabled = new Set(capabilities || []);
  return entries.filter((entry) => enabled.has(entry.capability));
}
