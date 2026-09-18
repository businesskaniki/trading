import { lazy, Suspense, useEffect } from "react";
import { Routes, Route, useNavigate } from "react-router-dom";
import { useDispatch } from "react-redux";

import Navbar from "./components/Navbar";

import ProtectedRoute from "./components/routing/ProtectedRoute";
import PublicRoute from "./components/routing/PublicRoute";

import DashboardLayout from "./components/dashboard/DashboardLayout";

const Login = lazy(() => import("./pages/auth/Login"));
const Register = lazy(() => import("./pages/auth/Register"));
const VerifyEmail = lazy(() => import("./pages/auth/VerifyEmail"));
const ForgotPassword = lazy(() => import("./pages/auth/ForgotPassword"));
const ResetPassword = lazy(() => import("./pages/auth/ResetPassword"));

const Dashboard = lazy(() => import("./pages/Dashboard/Dashboard"));
const Landing = lazy(() => import("./pages/Landing/Landing"));

const Accounts = lazy(() => import("./pages/Dashboard/Accounts/Accounts"));
const Symbols = lazy(() => import("./pages/Dashboard/Symbols/SymbolsPage"));
const Orders = lazy(() => import("./pages/Dashboard/Orders/Orders"));
const Positions = lazy(() => import("./pages/Dashboard/Positions/Positions"));
const Trades = lazy(() => import("./pages/Dashboard/Trades/Trades"));
import NotFound from "./pages/NotFound";
const RiskManagement = lazy(() => import("./pages/Dashboard/Risk/RiskManagement"));
const Analytics = lazy(() => import("./pages/Dashboard/Analytics/Analytics"));
const StrategyRuns = lazy(() => import("./pages/Dashboard/Strategies/StrategyRuns"));
import { clearAuthentication } from "./redux/auth/authSlice";

import "./App.css";

const App = () => {
  const dispatch = useDispatch();
  const navigate = useNavigate();

  useEffect(() => {
    const handleAuthenticationLoss = () => {
      dispatch(clearAuthentication());
      navigate("/login", { replace: true });
    };

    window.addEventListener("auth:logout", handleAuthenticationLoss);

    return () => {
      window.removeEventListener("auth:logout", handleAuthenticationLoss);
    };
  }, [dispatch, navigate]);

  return (
    <Suspense fallback={<div className="auth-loading">Loading...</div>}>
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

          <Route path="orders" element={<Orders />} />

          <Route path="positions" element={<Positions />} />

          <Route path="trades" element={<Trades />} />
          <Route path="risk" element={<RiskManagement />} />
          <Route path="strategies" element={<StrategyRuns />} />
          <Route path="performance" element={<Analytics />} />

          <Route index element={<Dashboard />} />
        </Route>
      </Route>
      <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  );
};

export default App;
