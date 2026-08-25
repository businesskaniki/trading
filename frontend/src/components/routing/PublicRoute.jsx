import { Navigate, Outlet } from "react-router-dom";
import { useSelector } from "react-redux";

const PublicRoute = () => {
    const {
        isAuthenticated,
        authInitialized,
    } = useSelector(
        (state) => state.auth
    );

    // ======================================================
    // Wait until authentication has been restored
    // ======================================================

    if (!authInitialized) {
        return (
            <div className="auth-loading">
                Restoring session...
            </div>
        );
    }

    // ======================================================
    // Already authenticated
    // ======================================================

    if (isAuthenticated) {
        return (
            <Navigate
                to="/dashboard"
                replace
            />
        );
    }

    return <Outlet />;
};

export default PublicRoute;