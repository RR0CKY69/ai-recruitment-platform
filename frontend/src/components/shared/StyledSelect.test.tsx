import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { expect, test, vi } from 'vitest'
import StyledSelect from './StyledSelect'

test('renders a custom listbox and supports keyboard selection and Escape', async () => {
  const onChange = vi.fn()
  function SelectHarness() {
    const [value, setValue] = useState('one')
    return (
      <StyledSelect
        aria-label="Job"
        value={value}
        options={[
          { value: 'one', label: 'Job One' },
          { value: 'two', label: 'Job Two' },
        ]}
        onValueChange={nextValue => {
          onChange(nextValue)
          setValue(nextValue)
        }}
      />
    )
  }
  const user = userEvent.setup()
  render(<SelectHarness />)

  const select = screen.getByRole('combobox', { name: 'Job' })
  expect(select).toHaveClass('select-trigger')
  await user.tab()
  expect(select).toHaveFocus()
  await user.keyboard('{Enter}')
  const menu = await screen.findByRole('listbox')
  expect(menu).toBeInTheDocument()
  const option = screen.getByRole('option', { name: 'Job Two' })
  expect(option).toHaveClass('select-item')
  await user.keyboard('{ArrowDown}{Enter}')
  expect(onChange).toHaveBeenCalledWith('two')
  expect(select).toHaveTextContent('Job Two')

  await user.keyboard('{Enter}')
  expect(screen.getByRole('listbox')).toBeInTheDocument()
  await user.keyboard('{Escape}')
  expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
})
