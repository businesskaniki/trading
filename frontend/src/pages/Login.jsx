import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDispatch, useSelector } from 'react-redux'
import { login } from '../features/auth/authSlice'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const dispatch = useDispatch()
  const auth = useSelector((s) => s.auth)
  const navigate = useNavigate()

  useEffect(() => {
    if (auth.user) navigate('/')
  }, [auth.user, navigate])

  const handleSubmit = async (e) => {
    e.preventDefault()
    try {
      await dispatch(login({ email, password })).unwrap()
      navigate('/')
    } catch (err) {
      // error shown by selector
    }
  }

  return (
    <div style={{ maxWidth: 420 }}>
      <h2>Login</h2>
      <form onSubmit={handleSubmit}>
        <label>
          Email
          <input value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <br />
        <label>
          Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <br />
        <button type="submit">Login</button>
        {auth.status === 'loading' && <div>Logging in...</div>}
        {auth.error && <div style={{ color: 'red' }}>{JSON.stringify(auth.error)}</div>}
      </form>
    </div>
  )
}
