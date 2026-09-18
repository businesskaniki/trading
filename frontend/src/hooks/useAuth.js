import { useDispatch, useSelector } from "react-redux";
import {
  loginUser,
  logoutUser,
  refreshAccessToken,
} from "../redux/auth/authThunks";

export default function useAuth() {
  const auth = useSelector((s) => s.auth);
  const dispatch = useDispatch();

  return {
    ...auth,
    login: (creds) => dispatch(loginUser(creds)),
    logout: () => dispatch(logoutUser()),
    refresh: () => dispatch(refreshAccessToken()),
  };
}
