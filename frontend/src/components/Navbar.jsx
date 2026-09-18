import { useEffect, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useNavigate } from "react-router-dom";

import {
  FaBell,
  FaChevronDown,
  FaSignOutAlt,
  FaThLarge,
  FaUserCircle,
} from "react-icons/fa";

import { logoutUser } from "../redux/auth/authThunks";

import "../css/navcss.css";

const Navbar = () => {
  const dispatch = useDispatch();
  const navigate = useNavigate();

  const { isAuthenticated } = useSelector((state) => state.auth);

  const [user, setUser] = useState(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const dropdownRef = useRef(null);

  // ==========================================================
  // Load User
  // ==========================================================

  useEffect(() => {
    const loadUser = () => {
      const storedUser = localStorage.getItem("user");

      if (!storedUser) {
        setUser(null);
        return;
      }

      try {
        setUser(JSON.parse(storedUser));
      } catch (error) {
        console.error("Invalid user data in localStorage:", error);

        localStorage.removeItem("user");

        setUser(null);
      }
    };

    loadUser();
  }, [isAuthenticated]);

  // ==========================================================
  // Close Dropdown When Clicking Outside
  // ==========================================================

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setDropdownOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  // ==========================================================
  // Close Dropdown With Escape
  // ==========================================================

  useEffect(() => {
    const handleEscape = (event) => {
      if (event.key === "Escape") {
        setDropdownOpen(false);
      }
    };

    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  // ==========================================================
  // Navigation
  // ==========================================================

  const handleNavigation = (path) => {
    setDropdownOpen(false);

    navigate(path);
  };

  // ==========================================================
  // Logout
  // ==========================================================

  const handleLogout = async () => {
    setDropdownOpen(false);

    await dispatch(logoutUser());

    setUser(null);

    navigate("/login", {
      replace: true,
    });
  };

  // ==========================================================
  // User Information
  // ==========================================================

  const displayName =
    user?.full_name || user?.username || user?.email || "User";

  const email = user?.email || "";

  return (
    <header className="navbar">
      {/* ==================================================
                BRAND
            ================================================== */}

      <div
        className="navbar-brand"
        onClick={() => handleNavigation(isAuthenticated ? "/dashboard" : "/")}
      >
        <div className="navbar-brand__mark">AQE</div>

        <div className="navbar-brand__text">
          <strong>Athena Quant Engine</strong>

          <span>Algorithmic Trading Infrastructure</span>
        </div>
      </div>

      {/* ==================================================
                RIGHT SIDE
            ================================================== */}

      <div className="navbar-actions">
        {isAuthenticated ? (
          <>
            {/* ==================================================
                            Notifications
                        ================================================== */}

            <button
              type="button"
              className="navbar-notification"
              aria-label="Notifications"
            >
              <FaBell />

              <span className="notification-indicator" />
            </button>

            {/* ==================================================
                            Profile
                        ================================================== */}

            <div className="profile-wrapper" ref={dropdownRef}>
              <button
                type="button"
                className={
                  dropdownOpen
                    ? "profile-trigger profile-trigger--active"
                    : "profile-trigger"
                }
                onClick={() => setDropdownOpen((previous) => !previous)}
                aria-expanded={dropdownOpen}
                aria-haspopup="menu"
              >
                <FaUserCircle className="profile-avatar" />

                <div className="profile-info">
                  <strong>{displayName}</strong>

                  <span>{email}</span>
                </div>

                <FaChevronDown
                  className={
                    dropdownOpen
                      ? "profile-chevron profile-chevron--open"
                      : "profile-chevron"
                  }
                />
              </button>

              {/* ==================================================
                                Dropdown
                            ================================================== */}

              {dropdownOpen && (
                <div className="profile-dropdown" role="menu">
                  {/* User */}

                  <div className="dropdown-user">
                    <div className="dropdown-user__avatar">
                      <FaUserCircle />
                    </div>

                    <div className="dropdown-user__details">
                      <strong>{displayName}</strong>

                      <span>{email}</span>
                    </div>
                  </div>

                  <div className="dropdown-divider" />

                  {/* Dashboard */}

                  <button
                    type="button"
                    className="dropdown-item"
                    onClick={() => handleNavigation("/dashboard")}
                  >
                    <span className="dropdown-item__icon">
                      <FaThLarge />
                    </span>

                    <span className="dropdown-item__content">
                      <strong>Dashboard</strong>

                      <small>Trading overview</small>
                    </span>
                  </button>

                  <div className="dropdown-divider" />

                  {/* Logout */}

                  <button
                    type="button"
                    className="dropdown-item dropdown-item--logout"
                    onClick={handleLogout}
                  >
                    <span className="dropdown-item__icon">
                      <FaSignOutAlt />
                    </span>

                    <span className="dropdown-item__content">
                      <strong>Logout</strong>

                      <small>Sign out of AQE</small>
                    </span>
                  </button>
                </div>
              )}
            </div>
          </>
        ) : (
          /* ==================================================
                       PUBLIC
                    ================================================== */

          <div className="navbar-auth">
            <button
              type="button"
              className="navbar-login"
              onClick={() => navigate("/login")}
            >
              Login
            </button>

            <button
              type="button"
              className="navbar-register"
              onClick={() => navigate("/register")}
            >
              Get Started
            </button>
          </div>
        )}
      </div>
    </header>
  );
};

export default Navbar;
