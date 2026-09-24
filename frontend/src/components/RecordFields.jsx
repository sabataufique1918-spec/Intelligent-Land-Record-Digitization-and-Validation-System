// Shared form fields for entering / editing land record metadata.
export const EMPTY_FIELDS = {
  document_type: 'Other',
  owner_name: '',
  father_name: '',
  document_date: '',
  previous_owner: '',
  survey_number: '',
  khata_number: '',
  village: '',
  tehsil: '',
  district: '',
  state: '',
  area_value: '',
  area_unit: '',
  language: '',
  remarks: '',
}

const LANGUAGES = ['Hindi', 'English', 'Marathi', 'Punjabi', 'Bengali', 'Gujarati', 'Odia', 'Tamil', 'Telugu', 'Kannada', 'Malayalam', 'Urdu', 'Other']

export default function RecordFields({ values, onChange, options }) {
  const set = (key) => (e) => onChange({ ...values, [key]: e.target.value })
  const input = (key, label, props = {}) => (
    <label className="field">
      <span>{label}</span>
      <input value={values[key] ?? ''} onChange={set(key)} {...props} />
    </label>
  )

  return (
    <div className="form-grid">
      <label className="field">
        <span>Document type</span>
        <select value={values.document_type} onChange={set('document_type')}>
          {(options?.document_types || ['Other']).map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Document language</span>
        <select value={values.language ?? ''} onChange={set('language')}>
          <option value="">Select…</option>
          {LANGUAGES.map((l) => (
            <option key={l}>{l}</option>
          ))}
        </select>
      </label>
      {input('owner_name', 'Owner name *')}
      {input('father_name', "Father's / husband's name")}
      {input('document_date', 'Document / registration date', { type: 'date' })}
      {input('previous_owner', 'Previous owner / seller (for transfers)', { placeholder: 'Only for sale deed, mutation, gift…' })}
      {input('survey_number', 'Survey / Khasra no. *', { placeholder: 'e.g. 112/3' })}
      {input('khata_number', 'Khata / Khatauni no.')}
      {input('village', 'Village *')}
      {input('tehsil', 'Tehsil / Taluka')}
      {input('district', 'District *', { list: 'district-options' })}
      {input('state', 'State')}
      {input('area_value', 'Area', { type: 'number', step: 'any', min: '0' })}
      <label className="field">
        <span>Area unit</span>
        <select value={values.area_unit ?? ''} onChange={set('area_unit')}>
          <option value="">Select…</option>
          {(options?.area_units || []).map((u) => (
            <option key={u}>{u}</option>
          ))}
        </select>
      </label>
      <label className="field field-wide">
        <span>Remarks</span>
        <textarea rows={2} value={values.remarks ?? ''} onChange={set('remarks')} />
      </label>
      <datalist id="district-options">
        {(options?.districts || []).map((d) => (
          <option key={d} value={d} />
        ))}
      </datalist>
    </div>
  )
}
