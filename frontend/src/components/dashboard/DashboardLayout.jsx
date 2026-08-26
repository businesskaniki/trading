import { Outlet } from "react-router-dom";

import DashboardNav from "./DashboardNav";

import "../../css/dashboardLayout.css";


const DashboardLayout = () => {
    return (
        <div className="dashboard-layout">

            <DashboardNav />

            <main className="dashboard-layout__content">
                <Outlet />
            </main>

        </div>
    );
};


export default DashboardLayout;