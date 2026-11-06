import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import ConfirmationDialog from './ConfirmationDialog'

function ConfirmationHost() {
  const [open, setOpen] = useState(false)

  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Open confirmation</button>
      <ConfirmationDialog
        open={open}
        title="Sign out?"
        description="You will need to sign in again."
        confirmLabel="Sign Out"
        onCancel={() => setOpen(false)}
        onConfirm={() => setOpen(false)}
      />
    </>
  )
}

test('focuses dialog actions, traps keyboard focus, and restores focus after Escape', async () => {
  const user = userEvent.setup()
  render(<ConfirmationHost />)

  const trigger = screen.getByRole('button', { name: 'Open confirmation' })
  await user.click(trigger)
  const dialog = screen.getByRole('alertdialog', { name: 'Sign out?' })
  const cancel = screen.getByRole('button', { name: 'Cancel' })
  const confirm = screen.getByRole('button', { name: 'Sign Out' })
  await waitFor(() => expect(cancel).toHaveFocus())

  confirm.focus()
  fireEvent.keyDown(dialog, { key: 'Tab' })
  expect(cancel).toHaveFocus()

  fireEvent.keyDown(dialog, { key: 'Escape' })
  await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
  expect(trigger).toHaveFocus()
})
