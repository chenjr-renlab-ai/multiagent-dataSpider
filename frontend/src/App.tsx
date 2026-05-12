import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { clsx } from 'clsx'
import { MonitorPage } from './pages/MonitorPage'
import { DataPage } from './pages/DataPage'

function NavBar() {
  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 flex h-10 items-center justify-center gap-1 border-t border-zinc-800 bg-zinc-950 sm:bottom-auto sm:top-0 sm:left-0 sm:w-12 sm:flex-col sm:h-screen sm:border-t-0 sm:border-r">
      <NavLink
        to="/"
        end
        title="监控"
        className={({ isActive }) =>
          clsx(
            'flex h-9 w-9 items-center justify-center rounded transition-colors',
            isActive ? 'bg-blue-700 text-white' : 'text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800'
          )
        }
      >
        {/* Monitor icon */}
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="2" y="3" width="20" height="14" rx="2" />
          <path d="M8 21h8M12 17v4" />
        </svg>
      </NavLink>
      <NavLink
        to="/data"
        title="数据"
        className={({ isActive }) =>
          clsx(
            'flex h-9 w-9 items-center justify-center rounded transition-colors',
            isActive ? 'bg-blue-700 text-white' : 'text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800'
          )
        }
      >
        {/* Table icon */}
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <path d="M3 9h18M3 15h18M9 3v18" />
        </svg>
      </NavLink>
    </nav>
  )
}

export function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen overflow-hidden bg-zinc-950">
        {/* Side nav */}
        <NavBar />
        {/* Main content shifted to account for nav */}
        <div className="flex-1 overflow-hidden sm:ml-12">
          <Routes>
            <Route path="/" element={<MonitorPage />} />
            <Route path="/data" element={<DataPage />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  )
}
