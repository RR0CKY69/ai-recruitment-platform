import * as Select from '@radix-ui/react-select'
import { Check, ChevronDown } from 'lucide-react'

export interface StyledSelectOption {
  value: string
  label: string
  disabled?: boolean
}

interface StyledSelectProps {
  id?: string
  'aria-label'?: string
  title?: string
  value: string
  placeholder?: string
  options: StyledSelectOption[]
  disabled?: boolean
  className?: string
  onValueChange: (value: string) => void
}

export default function StyledSelect({
  id,
  'aria-label': ariaLabel,
  title,
  value,
  placeholder,
  options,
  disabled = false,
  className = '',
  onValueChange,
}: StyledSelectProps) {
  return (
    <Select.Root value={value} onValueChange={onValueChange} disabled={disabled}>
      <Select.Trigger
        id={id}
        aria-label={ariaLabel}
        title={title}
        className={`select-trigger ${className}`}
      >
        <Select.Value placeholder={placeholder} />
        <Select.Icon aria-hidden="true" className="shrink-0 text-slate-400">
          <ChevronDown size={16} />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content className="select-content" position="popper" sideOffset={4}>
          <Select.Viewport className="select-viewport">
            {options.map(option => (
              <Select.Item
                key={option.value}
                value={option.value}
                disabled={option.disabled}
                className="select-item"
              >
                <Select.ItemText>{option.label}</Select.ItemText>
                <Select.ItemIndicator className="select-item-indicator">
                  <Check size={15} />
                </Select.ItemIndicator>
              </Select.Item>
            ))}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  )
}
