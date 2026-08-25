import { Navigate, Outlet } from "react-router-dom";
import { useSelector } from "react-redux";

const ProtectedRoute = () => {
    const {
        isAuthenticated,
        authInitialized,
    } = useSelector(
        (state) => state.auth
    );

    // ======================================================
    // Authentication is still being restored.
    //
    // DO NOT redirect yet.
    // ======================================================

    if (!authInitialized) {
        return (
            <div className="auth-loading">
                Restoring session...
            </div>
        );
    }

    // ======================================================
    // No valid authentication
    // ======================================================

    if (!isAuthenticated) {
        return (
            <Navigate
                to="/login"
                replace
            />
        );
    }

    // ======================================================
    // Authenticated
    // ======================================================

    return <Outlet />;
};

export default ProtectedRoute;