import { NavLink, useNavigate } from "react-router-dom";
import {
    FaBell,
    FaUserCircle,
    FaSignOutAlt,
} from "react-icons/fa";
import { useDispatch, useSelector } from "react-redux";

import { logoutUser } from "../redux/auth/authThunks";

import "../css/navcss.css"

const Navbar = () => {
    const dispatch = useDispatch();
    const navigate = useNavigate();

    const { isAuthenticated, user } = useSelector(
        (state) => state.auth
    );

    console.log(user);
    

    const handleLogout = async () => {
        await dispatch(logoutUser());

        navigate("/login");
    };

    return (
        <header className="navbar">
            <div className="navbar__logo">
                <h2>AQE</h2>
                <span>Athena Quant Engine</span>
            </div>

            <nav className="navbar__links">
                <NavLink to="/" end>
                    Dashboard
                </NavLink>

                <NavLink to="/accounts">
                    Accounts
                </NavLink>

                <NavLink to="/symbols">
                    Symbols
                </NavLink>

                <NavLink to="/bots">
                    Bots
                </NavLink>

                <NavLink to="/orders">
                    Orders
                </NavLink>

                <NavLink to="/positions">
                    Positions
                </NavLink>

                <NavLink to="/history">
                    History
                </NavLink>

                <NavLink to="/logs">
                    Logs
                </NavLink>
            </nav>

            <div className="navbar__right">
                {isAuthenticated ? (
                    <>
                        <button className="notification-btn">
                            <FaBell />
                        </button>

                        <button className="profile-btn">
                            <FaUserCircle />

                            <span>
                                {user?.full_name ||
                                    user?.username ||
                                    user?.email ||
                                    "User"}
                            </span>
                        </button>

                        <button
                            className="logout-btn"
                            onClick={handleLogout}
                        >
                            <FaSignOutAlt />

                            <span>Logout</span>
                        </button>
                    </>
                ) : (
                    <div className="auth-links">
                        <NavLink
                            to="/login"
                            className={({ isActive }) =>
                                isActive
                                    ? "login-btn active-auth"
                                    : "login-btn"
                            }
                        >
                            Login
                        </NavLink>

                        <NavLink
                            to="/register"
                            className={({ isActive }) =>
                                isActive
                                    ? "register-btn active-register"
                                    : "register-btn"
                            }
                        >
                            Register
                        </NavLink>
                    </div>
                )}
            </div>
        </header>
    );
};

export default Navbar;