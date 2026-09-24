export const STATUS_META = {
  pending: { label: 'Pending', tone: 'neutral' },
  flagged: { label: 'Flagged', tone: 'danger' },
  rules_passed: { label: 'Rules Passed', tone: 'info' },
  verified: { label: 'Verified', tone: 'success' },
  rejected: { label: 'Rejected', tone: 'muted' },
}

export const STATUS_ORDER = ['flagged', 'rules_passed', 'pending', 'verified', 'rejected']

export function formatDate(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatBytes(bytes) {
  if (!bytes) return '—'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let n = bytes
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024
    i += 1
  }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

export function formatArea(record) {
  if (record.area_value === null || record.area_value === undefined) return '—'
  return `${record.area_value} ${record.area_unit || ''}`.trim()
}

export function display(value) {
  return value === null || value === undefined || value === '' ? '—' : value
}

export const OCR_STATUS = {
  not_run: 'Not run',
  completed: 'Text extracted',
  no_text: 'No text found',
  failed: 'Failed',
  not_available: 'No document',
}

export const FIELD_LABELS = {
  document_type: 'Document type',
  owner_name: 'Owner name',
  father_name: "Father's / husband's name",
  previous_owner: 'Previous owner / seller',
  document_date: 'Document date',
  survey_number: 'Survey / Khasra no.',
  khata_number: 'Khata no.',
  village: 'Village',
  tehsil: 'Tehsil / Taluka',
  district: 'District',
  state: 'State',
  area_value: 'Area',
  area_unit: 'Area unit',
}
