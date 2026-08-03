import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/axios'
import { Paper, TextInput, PasswordInput, Button, Title, Stack, Alert } from '@mantine/core'

export default function Register() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      await api.post('/auth/register', { email, password, full_name: fullName })
      navigate('/login')
    } catch (err) {
      setError(err.response?.data || err.message)
    }
  }

  return (
    <Paper radius="md" p="lg" withBorder style={{ maxWidth: 540 }}>
      <Stack>
        <Title order={2}>Create account</Title>
        {error && <Alert title="Register failed" color="red">{typeof error === 'string' ? error : JSON.stringify(error)}</Alert>}
        <form onSubmit={handleSubmit}>
          <Stack>
            <TextInput label="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
            <TextInput label="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            <PasswordInput label="Password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            <Button type="submit">Register</Button>
          </Stack>
        </form>
      </Stack>
    </Paper>
  )
}
