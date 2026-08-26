import { NavLink } from "react-router-dom";

import {
    FaChartPie,
    FaWallet,
    FaCoins,
    FaClipboardList,
    FaExchangeAlt,
    FaHistory,
    FaRobot,
    FaChartLine,
    FaShieldAlt,
    FaBolt,
    FaDatabase,
} from "react-icons/fa";

import "../../css/dashboardNav.css";


const DashboardNav = () => {

    const navigation = [
        {
            title: "Overview",
            items: [
                {
                    label: "Dashboard",
                    path: "/dashboard",
                    icon: <FaChartPie />,
                    end: true,
                },
            ],
        },

        {
            title: "Trading",
            items: [
                {
                    label: "Accounts",
                    path: "/dashboard/accounts",
                    icon: <FaWallet />,
                },
                {
                    label: "Symbols",
                    path: "/dashboard/symbols",
                    icon: <FaCoins />,
                },
                {
                    label: "Orders",
                    path: "/dashboard/orders",
                    icon: <FaClipboardList />,
                },
                {
                    label: "Positions",
                    path: "/dashboard/positions",
                    icon: <FaExchangeAlt />,
                },
                {
                    label: "Trades",
                    path: "/dashboard/trades",
                    icon: <FaHistory />,
                },
            ],
        },

        {
            title: "Strategies",
            items: [
                {
                    label: "Strategy Runs",
                    path: "/dashboard/strategies",
                    icon: <FaRobot />,
                },
            ],
        },

        {
            title: "Analytics",
            items: [
                {
                    label: "Performance",
                    path: "/dashboard/performance",
                    icon: <FaChartLine />,
                },
            ],
        },

        {
            title: "Risk",
            items: [
                {
                    label: "Risk Management",
                    path: "/dashboard/risk",
                    icon: <FaShieldAlt />,
                },
                {
                    label: "Risk Snapshots",
                    path: "/dashboard/risk-snapshots",
                    icon: <FaDatabase />,
                },
            ],
        },

        {
            title: "Execution",
            items: [
                {
                    label: "Execution",
                    path: "/dashboard/execution",
                    icon: <FaBolt />,
                },
            ],
        },
    ];


    return (
        <aside className="dashboard-nav">

            {/* ==========================================
                HEADER
            ========================================== */}

            <div className="dashboard-nav__header">

                <div className="dashboard-nav__logo">
                    AQE
                </div>

                <div className="dashboard-nav__title">

                    <strong>
                        Trading Console
                    </strong>

                    <span>
                        Athena Quant Engine
                    </span>

                </div>

            </div>


            {/* ==========================================
                NAVIGATION
            ========================================== */}

            <nav className="dashboard-nav__menu">

                {navigation.map((section) => (

                    <div
                        className="dashboard-nav__section"
                        key={section.title}
                    >

                        <span className="dashboard-nav__section-title">
                            {section.title}
                        </span>


                        <div className="dashboard-nav__items">

                            {section.items.map((item) => (

                                <NavLink
                                    key={item.path}
                                    to={item.path}
                                    end={item.end}
                                    className={({ isActive }) =>
                                        isActive
                                            ? "dashboard-nav__item dashboard-nav__item--active"
                                            : "dashboard-nav__item"
                                    }
                                >

                                    <span className="dashboard-nav__icon">
                                        {item.icon}
                                    </span>

                                    <span className="dashboard-nav__label">
                                        {item.label}
                                    </span>

                                </NavLink>

                            ))}

                        </div>

                    </div>

                ))}

            </nav>


            {/* ==========================================
                FOOTER
            ========================================== */}

            <div className="dashboard-nav__footer">

                <div className="dashboard-nav__status">

                    <span className="dashboard-nav__status-dot" />

                    <div>
                        <strong>
                            System Online
                        </strong>

                        <span>
                            Trading infrastructure
                        </span>
                    </div>

                </div>

            </div>

        </aside>
    );
};


export default DashboardNav;