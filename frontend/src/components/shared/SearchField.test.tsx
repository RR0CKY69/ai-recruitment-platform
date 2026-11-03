import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import SearchField from './SearchField'

test('keeps the search icon in its own padded area and supports typing and clearing', () => {
  const onChange = vi.fn()
  const { container, rerender } = render(
    <SearchField label="Search candidates" placeholder="Search candidates" value="" onChange={onChange} />,
  )

  const input = screen.getByRole('textbox', { name: 'Search candidates' })
  expect(input).toHaveAttribute('placeholder', 'Search candidates')
  expect(input).toHaveClass('search-field-input')
  expect(container.querySelector('svg')).toHaveClass('left-3', 'top-1/2', '-translate-y-1/2', 'pointer-events-none')
  fireEvent.change(input, { target: { value: 'Amina' } })
  expect(onChange).toHaveBeenCalledWith('Amina')

  rerender(<SearchField label="Search candidates" placeholder="Search candidates" value="Amina" onChange={onChange} />)
  fireEvent.click(screen.getByRole('button', { name: 'Clear search candidates' }))
  expect(onChange).toHaveBeenLastCalledWith('')
})
