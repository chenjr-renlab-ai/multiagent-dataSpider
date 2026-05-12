import { MissionForm } from '../mission/MissionForm'
import { MissionList } from '../mission/MissionList'

export function Sidebar() {
  return (
    <aside className="flex h-full w-[340px] flex-shrink-0 flex-col border-r border-zinc-800 bg-zinc-950 overflow-hidden">
      {/* Mission creation form */}
      <div className="flex-shrink-0 border-b border-zinc-800">
        <MissionForm />
      </div>
      {/* Mission history */}
      <div className="flex-1 overflow-y-auto">
        <MissionList />
      </div>
    </aside>
  )
}
