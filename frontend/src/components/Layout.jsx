import React from 'react'
import { Outlet, Link } from 'react-router-dom'
import { useDispatch, useSelector } from 'react-redux'
import { logout } from '../features/auth/authSlice'
import { Header, Group, Container, Button, Avatar, Text } from '@mantine/core'

export default function Layout() {
  const dispatch = useDispatch()
  const user = useSelector((s) => s.auth.user)

  return (
    <div>
      <Header height={60} p="xs">
        <Container style={{ display: 'flex', alignItems: 'center', height: '100%' }}>
          <Group position="left" spacing="xl">
            <Link to="/">Trading</Link>
          </Group>
          <Group position="right" spacing="sm" style={{ marginLeft: 'auto' }}>
            {user ? (
              <>
                <Avatar radius="xl" size="sm">
                  {user.full_name ? user.full_name[0].toUpperCase() : 'U'}
                </Avatar>
                <Text size="sm">{user.full_name || user.email}</Text>
                <Button variant="outline" size="sm" onClick={() => dispatch(logout())}>
                  Logout
                </Button>
              </>
            ) : (
              <>
                <Button component={Link} to="/login" variant="subtle" size="sm">
                  Login
                </Button>
                <Button component={Link} to="/register" size="sm">
                  Register
                </Button>
              </>
            )}
          </Group>
        </Container>
      </Header>
      <main style={{ padding: 16 }}>
        <Container>
          <Outlet />
        </Container>
      </main>
    </div>
  )
}
