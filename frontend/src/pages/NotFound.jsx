import { Link } from "react-router-dom";

import {
    FaArrowLeft,
    FaChartLine,
    FaHome,
    FaExclamationTriangle,
} from "react-icons/fa";

import "../../css/notFound.css";


const NotFound = () => {
    return (
        <main className="not-found">

            {/* Animated background grid */}
            <div className="not-found__grid" />

            {/* Ambient glow */}
            <div className="not-found__glow not-found__glow--one" />
            <div className="not-found__glow not-found__glow--two" />


            <section className="not-found__content">

                {/* System label */}

                <div className="not-found__system">

                    <span className="not-found__status-dot" />

                    <span>
                        AQE // SYSTEM RESPONSE
                    </span>

                </div>


                {/* 404 */}

                <div className="not-found__code">

                    <span>4</span>

                    <div className="not-found__orb">
                        <FaChartLine />
                    </div>

                    <span>4</span>

                </div>


                {/* Main message */}

                <div className="not-found__message">

                    <div className="not-found__warning">
                        <FaExclamationTriangle />
                        ROUTE NOT FOUND
                    </div>

                    <h1>
                        Looks like you took
                        <span> the wrong position.</span>
                    </h1>

                    <p>
                        The page you're looking for doesn't exist,
                        was moved, or decided to disappear from the
                        market without warning.
                    </p>

                </div>


                {/* Fake market terminal */}

                <div className="not-found__terminal">

                    <div className="terminal__header">

                        <span>
                            ATHENA QUANT ENGINE
                        </span>

                        <span className="terminal__live">
                            ● SYSTEM ONLINE
                        </span>

                    </div>


                    <div className="terminal__body">

                        <div>
                            <span>ROUTE</span>
                            <strong>UNKNOWN</strong>
                        </div>

                        <div>
                            <span>POSITION</span>
                            <strong className="terminal__negative">
                                LOST
                            </strong>
                        </div>

                        <div>
                            <span>RISK</span>
                            <strong className="terminal__warning">
                                HIGH
                            </strong>
                        </div>

                    </div>


                    {/* Mini chart */}

                    <div className="terminal__chart">

                        <span className="candle candle--1" />
                        <span className="candle candle--2" />
                        <span className="candle candle--3" />
                        <span className="candle candle--4" />
                        <span className="candle candle--5" />
                        <span className="candle candle--6" />
                        <span className="candle candle--7" />
                        <span className="candle candle--8" />

                    </div>

                </div>


                {/* Actions */}

                <div className="not-found__actions">

                    <Link
                        to="/dashboard"
                        className="not-found__button not-found__button--primary"
                    >
                        <FaChartLine />

                        Back to Dashboard
                    </Link>


                    <Link
                        to="/"
                        className="not-found__button not-found__button--secondary"
                    >
                        <FaHome />

                        Take Me Home
                    </Link>

                </div>


                {/* Footer joke */}

                <div className="not-found__footer">

                    <FaArrowLeft />

                    <span>
                        Don't worry. No real money was lost on this trade.
                    </span>

                </div>

            </section>

        </main>
    );
};


export default NotFound;