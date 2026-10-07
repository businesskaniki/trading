import { lazy, Suspense, useEffect } from "react";
import { Routes, Route, useNavigate } from "react-router-dom";
import { useDispatch } from "react-redux";

import Navbar from "./components/Navbar";

import ProtectedRoute from "./components/routing/ProtectedRoute";
import PublicRoute from "./components/routing/PublicRoute";

import DashboardLayout from "./components/dashboard/DashboardLayout";

import NotFound from "./pages/NotFound";

import { clearAuthentication } from "./redux/auth/authSlice";

import "./App.css";

/* =========================================================
   PUBLIC PAGES
   ========================================================= */

const Login = lazy(() => import("./pages/auth/Login"));
const Register = lazy(() => import("./pages/auth/Register"));
const VerifyEmail = lazy(() => import("./pages/auth/VerifyEmail"));
const ForgotPassword = lazy(() => import("./pages/auth/ForgotPassword"));
const ResetPassword = lazy(() => import("./pages/auth/ResetPassword"));

const Landing = lazy(() => import("./pages/Landing/Landing"));

/* =========================================================
   DASHBOARD PAGES
   ========================================================= */

const Dashboard = lazy(() => import("./pages/Dashboard/Dashboard"));

const Accounts = lazy(() => import("./pages/Dashboard/Accounts/Accounts"));

const Symbols = lazy(() => import("./pages/Dashboard/Symbols/SymbolsPage"));

const Orders = lazy(() => import("./pages/Dashboard/Orders/Orders"));

const Positions = lazy(() => import("./pages/Dashboard/Positions/Positions"));

const Trades = lazy(() => import("./pages/Dashboard/Trades/Trades"));

const RiskManagement = lazy(
  () => import("./pages/Dashboard/Risk/RiskManagement"),
);

const Analytics = lazy(() => import("./pages/Dashboard/Analytics/Analytics"));

const StrategyRuns = lazy(
  () => import("./pages/Dashboard/Strategies/StrategyRuns"),
);

const Backtesting = lazy(
  () => import("./pages/Dashboard/Backtesting/Backtesting"),
);

/* =========================================================
   APPLICATION
   ========================================================= */

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
        {/* =================================================
            PUBLIC ROUTES
            ================================================= */}

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

        {/* =================================================
            PROTECTED ROUTES
            ================================================= */}

        <Route element={<ProtectedRoute />}>
          {/* ===============================================
              DASHBOARD LAYOUT
              =============================================== */}

          <Route path="/dashboard" element={<DashboardLayout />}>
            {/* ---------------------------------------------
                Overview
                --------------------------------------------- */}

            <Route index element={<Dashboard />} />

            {/* ---------------------------------------------
                Trading
                --------------------------------------------- */}

            <Route path="accounts" element={<Accounts />} />

            <Route path="symbols" element={<Symbols />} />

            <Route path="orders" element={<Orders />} />

            <Route path="positions" element={<Positions />} />

            <Route path="trades" element={<Trades />} />

            {/* ---------------------------------------------
                Strategies
                --------------------------------------------- */}

            <Route path="strategies" element={<StrategyRuns />} />

            {/* ---------------------------------------------
                Analytics
                --------------------------------------------- */}

            <Route path="performance" element={<Analytics />} />

            <Route path="backtesting" element={<Backtesting />} />

            {/* ---------------------------------------------
                Risk
                --------------------------------------------- */}

            <Route path="risk" element={<RiskManagement />} />
          </Route>
        </Route>

        {/* =================================================
            404
            ================================================= */}

        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  );
};

export default App;
