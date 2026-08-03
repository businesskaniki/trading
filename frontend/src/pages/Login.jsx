import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDispatch, useSelector } from 'react-redux'
import { login } from '../features/auth/authSlice'
import { Paper, TextInput, PasswordInput, Button, Title, Text, Stack, Alert } from '@mantine/core'

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
    <Paper radius="md" p="lg" withBorder style={{ maxWidth: 480 }}>
      <Stack spacing="md">
        <Title order={2}>Sign in</Title>
        <Text color="dimmed" size="sm">
          Sign in to your account to access your trading dashboard
        </Text>

        {auth.error && (
          <Alert title="Login failed" color="red">
            {typeof auth.error === 'string' ? auth.error : JSON.stringify(auth.error)}
          </Alert>
        )}

        <form onSubmit={handleSubmit}>
          <Stack>
            <TextInput label="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            <PasswordInput label="Password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            <Button type="submit" loading={auth.status === 'loading'}>Login</Button>
          </Stack>
        </form>
      </Stack>
    </Paper>
  )
}
