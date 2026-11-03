const COMPACT_TABLES_KEY = 'apex-recruit.preferences.compact-tables'

export function readCompactTablesPreference(): boolean {
  return window.localStorage.getItem(COMPACT_TABLES_KEY) === 'true'
}

export function saveCompactTablesPreference(enabled: boolean): void {
  window.localStorage.setItem(COMPACT_TABLES_KEY, String(enabled))
}
