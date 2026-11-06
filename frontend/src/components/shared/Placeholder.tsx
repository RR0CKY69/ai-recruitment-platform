import Sidebar from '../layout/Sidebar'
import { PageHeader } from './Primitives'

export function Placeholder({ title }: { title: string }) {
  return (
    <div className="app-shell flex">
      <Sidebar />
      <main className="flex-1 p-4 md:p-6">
        <div className="page-shell">
          <PageHeader title={title} />
          <p className="mt-4 text-slate-300">This section is not connected to a backend workflow yet.</p>
        </div>
      </main>
    </div>
  )
}