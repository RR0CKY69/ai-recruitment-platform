import { Search, X } from 'lucide-react'

interface SearchFieldProps {
  label: string
  placeholder: string
  value: string
  onChange: (value: string) => void
}

export default function SearchField({ label, placeholder, value, onChange }: SearchFieldProps) {
  return (
    <div className="relative w-full">
      <Search
        aria-hidden="true"
        size={16}
        className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
      />
      <input
        type="text"
        aria-label={label}
        className="input-shell search-field-input"
        placeholder={placeholder}
        value={value}
        onChange={event => onChange(event.target.value)}
      />
      {value && (
        <button
          type="button"
          aria-label={`Clear ${label.toLowerCase()}`}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-slate-400 hover:bg-slate-700 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-400"
          onClick={() => onChange('')}
        >
          <X aria-hidden="true" size={16} />
        </button>
      )}
    </div>
  )
}
