import { Routes, Route } from "react-router-dom";

import Navbar from "./components/Navbar";

import ProtectedRoute from "./components/routing/ProtectedRoute";
import PublicRoute from "./components/routing/PublicRoute";

import DashboardLayout from "./components/dashboard/DashboardLayout";

import Login from "./pages/auth/Login";
import Register from "./pages/auth/Register";
import VerifyEmail from "./pages/auth/VerifyEmail";
import ForgotPassword from "./pages/auth/ForgotPassword";
import ResetPassword from "./pages/auth/ResetPassword";

import Dashboard from "./pages/Dashboard/Dashboard";
import Landing from "./pages/Landing/Landing";

import Accounts from "./pages/Dashboard/Accounts/Accounts";
import Symbols from "./pages/Dashboard/Symbols/SymbolsPage";
import NotFound from "./pages/NotFound";

import "./App.css";

const App = () => {
  return (
    <Routes>
      {/* ==========================================
                PUBLIC ROUTES
            ========================================== */}

      <Route element={<PublicRoute />}>
        <Route
          path="/"
          element={
            <>
              <Navbar />
              <Landing />
            </>
          }
        />

        <Route
          path="/login"
          element={
            <>
              <Navbar />
              <Login />
            </>
          }
        />

        <Route
          path="/register"
          element={
            <>
              <Navbar />
              <Register />
            </>
          }
        />

        <Route
          path="/verify-email"
          element={
            <>
              <Navbar />
              <VerifyEmail />
            </>
          }
        />

        <Route
          path="/forgot-password"
          element={
            <>
              <Navbar />
              <ForgotPassword />
            </>
          }
        />

        <Route
          path="/reset-password"
          element={
            <>
              <Navbar />
              <ResetPassword />
            </>
          }
        />
      </Route>

      {/* ==========================================
                PROTECTED ROUTES
            ========================================== */}

      <Route element={<ProtectedRoute />}>
        {/* ======================================
                    DASHBOARD LAYOUT
                ====================================== */}

        <Route path="/dashboard" element={<DashboardLayout />}>
          {/* /dashboard */}
          <Route path="accounts" element={<Accounts />} />

          <Route path="symbols" element={<Symbols />} />

          <Route index element={<Dashboard />} />
        </Route>
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
};

export default App;
