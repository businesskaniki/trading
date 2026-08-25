import {
    Routes,
    Route,
} from "react-router-dom";

import Navbar from "./components/Navbar";

import ProtectedRoute from "./components/routing/ProtectedRoute";
import PublicRoute from "./components/routing/PublicRoute";

import Login from "./pages/auth/Login";
import Register from "./pages/auth/Register";
import VerifyEmail from "./pages/auth/VerifyEmail";
import ForgotPassword from "./pages/auth/ForgotPassword";
import ResetPassword from "./pages/auth/ResetPassword";

import Dashboard from "./pages/Dashboard/Dashboard";
import Landing from "./pages/Landing/Landing";

import "./App.css";

const App = () => {
    return (
        <>
            <Navbar />

            <Routes>

                {/* ==========================================
                    PUBLIC ROUTES
                ========================================== */}

                <Route
                    element={
                        <PublicRoute />
                    }
                >
                    <Route
                        path="/login"
                        element={<Login />}
                    />

                     <Route
                        path="/"
                        element={<Landing />}
                    />


                    <Route
                        path="/register"
                        element={<Register />}
                    />

                    <Route
                        path="/verify-email"
                        element={
                            <VerifyEmail />
                        }
                    />

                    <Route
                        path="/forgot-password"
                        element={
                            <ForgotPassword />
                        }
                    />

                    <Route
                        path="/reset-password"
                        element={
                            <ResetPassword />
                        }
                    />
                </Route>


                {/* ==========================================
                    PROTECTED ROUTES
                ========================================== */}

                <Route
                    element={
                        <ProtectedRoute />
                    }
                >
                    <Route
                        path="/dashboard"
                        element={
                            <Dashboard />
                        }
                    />
                </Route>

            </Routes>
        </>
    );
};

export default App;