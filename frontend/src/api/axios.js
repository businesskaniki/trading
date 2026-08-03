import axios from 'axios'

const base = (import.meta.env.VITE_API_BASE_URL || '') + '/api/v1'

const api = axios.create({
  baseURL: base,
  withCredentials: true,
})

// Attach access token from localStorage
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('accessToken')
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Refresh on 401
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    if (error.response && error.response.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true
      try {
        const resp = await axios.post(base + '/auth/refresh', {}, { withCredentials: true })
        const { access_token } = resp.data
        if (access_token) {
          localStorage.setItem('accessToken', access_token)
          api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`
          originalRequest.headers['Authorization'] = `Bearer ${access_token}`
          return api(originalRequest)
        }
      } catch (e) {
        return Promise.reject(error)
      }
    }
    return Promise.reject(error)
  },
)

export default api
