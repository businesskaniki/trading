import { useSelector, useDispatch } from 'react-redux'
import { login, logout, refreshToken } from '../features/auth/authSlice'

export default function useAuth() {
  const auth = useSelector((s) => s.auth)
  const dispatch = useDispatch()

  return {
    ...auth,
    login: (creds) => dispatch(login(creds)),
    logout: () => dispatch(logout()),
    refresh: () => dispatch(refreshToken()),
  }
}
