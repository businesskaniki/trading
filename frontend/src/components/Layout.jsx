import React from 'react'
import { Outlet, Link } from 'react-router-dom'
import { useDispatch, useSelector } from 'react-redux'
import { logout } from '../features/auth/authSlice'

export default function Layout() {
  const dispatch = useDispatch()
  const user = useSelector((s) => s.auth.user)

  return (
    <div>
      <header style={{ display: 'flex', gap: 12, padding: 12, alignItems: 'center' }}>
        <Link to="/">Trading</Link>
        <nav style={{ marginLeft: 'auto' }}>
          {user ? (
            <>
              <span style={{ marginRight: 8 }}>{user.email || user.full_name}</span>
              <button onClick={() => dispatch(logout())}>Logout</button>
            </>
          ) : (
            <>
              <Link to="/login" style={{ marginRight: 8 }}>
                Login
              </Link>
              <Link to="/register">Register</Link>
            </>
          )}
        </nav>
      </header>
      <main style={{ padding: 16 }}>
        <Outlet />
      </main>
    </div>
  )
}
