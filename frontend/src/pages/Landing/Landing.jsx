import { useEffect, useState } from "react";
import {
  ArrowRight,
  BarChart3,
  BrainCircuit,
  ShieldCheck,
  Activity,
  Database,
  Zap,
  ChevronDown,
} from "lucide-react";

import "../../css/landing.css";

const Landing = () => {
  const [marketData, setMarketData] = useState({
    btc: 67284.42,
    eth: 3518.17,
    eur: 1.1742,
  });

  useEffect(() => {
    const interval = setInterval(() => {
      setMarketData((prev) => ({
        btc: prev.btc + (Math.random() - 0.5) * 80,
        eth: prev.eth + (Math.random() - 0.5) * 12,
        eur: prev.eur + (Math.random() - 0.5) * 0.002,
      }));
    }, 1800);

    return () => clearInterval(interval);
  }, []);

  return (
    <main className="landing">
      {/* =====================================================
                BACKGROUND
            ===================================================== */}

      <div className="landing-grid" />
      <div className="landing-glow landing-glow--one" />
      <div className="landing-glow landing-glow--two" />

      <div className="particles">
        {Array.from({ length: 25 }).map((_, index) => (
          <span
            key={index}
            className="particle"
            style={{
              "--i": index,
            }}
          />
        ))}
      </div>

      {/* =====================================================
                HERO
            ===================================================== */}

      <section className="hero">
        <div className="hero__content">
          <div className="status-pill">
            <span className="status-dot" />
            QUANT ENGINE ONLINE
          </div>

          <h1>
            Trade with
            <span> intelligence.</span>
          </h1>

          <p className="hero__description">
            Athena Quant Engine is an algorithmic trading infrastructure
            designed to combine strategy, risk management, execution and
            intelligence into one unified system.
          </p>

          <div className="hero__actions">
            <a href="/register" className="primary-btn">
              Get Started
              <ArrowRight size={18} />
            </a>

            <a href="#architecture" className="secondary-btn">
              Explore Engine
            </a>
          </div>

          <div className="hero__trust">
            <span>
              <ShieldCheck size={15} />
              Risk controlled
            </span>

            <span>
              <Activity size={15} />
              Real-time execution
            </span>

            <span>
              <BrainCircuit size={15} />
              AI ready
            </span>
          </div>
        </div>

        {/* =================================================
                    MARKET TERMINAL
                ================================================= */}

        <div className="terminal">
          <div className="terminal__header">
            <div className="terminal__title">
              <span className="terminal-dot" />
              ATHENA TERMINAL
            </div>

            <span className="terminal-live">LIVE</span>
          </div>

          <div className="terminal__chart">
            <div className="chart-label">BTCUSD</div>

            <div className="chart-price">
              $
              {marketData.btc.toLocaleString(undefined, {
                minimumFractionDigits: 2,
              })}
            </div>

            <div className="chart-change">+2.84%</div>

            <div className="chart">
              {[
                35, 43, 38, 49, 44, 57, 52, 61, 56, 67, 63, 72, 68, 79, 74, 86,
                81, 91, 88, 97,
              ].map((height, index) => (
                <div
                  key={index}
                  className="chart-bar"
                  style={{
                    height: `${height}%`,
                  }}
                />
              ))}
            </div>
          </div>

          <div className="market-list">
            <MarketRow
              symbol="BTCUSD"
              value={marketData.btc}
              change="+2.84%"
              positive
            />

            <MarketRow
              symbol="ETHUSD"
              value={marketData.eth}
              change="+1.73%"
              positive
            />

            <MarketRow symbol="EURUSD" value={marketData.eur} change="-0.24%" />
          </div>

          <div className="terminal-footer">
            <span>
              <span className="pulse" />
              Execution engine
            </span>

            <span>12ms</span>
          </div>
        </div>
      </section>

      {/* =====================================================
                METRICS
            ===================================================== */}

      <section className="metrics">
        <Metric value="24/7" label="Market monitoring" />

        <Metric value="<20ms" label="Execution architecture" />

        <Metric value="Multi" label="Strategy support" />

        <Metric value="AI" label="Intelligence layer" />
      </section>

      {/* =====================================================
                FEATURES
            ===================================================== */}

      <section className="features">
        <div className="section-heading">
          <span>THE ENGINE</span>

          <h2>
            Everything required to
            <strong> execute intelligently.</strong>
          </h2>

          <p>
            AQE separates strategy, risk, execution and intelligence into
            specialized components that work together as one trading system.
          </p>
        </div>

        <div className="feature-grid">
          <Feature
            icon={<BarChart3 />}
            title="Strategy Engine"
            text="Develop, test and deploy multiple algorithmic strategies without coupling them to execution."
          />

          <Feature
            icon={<ShieldCheck />}
            title="Risk Engine"
            text="Control exposure, position sizing, drawdown and portfolio-level risk before orders reach the market."
          />

          <Feature
            icon={<Zap />}
            title="Execution Engine"
            text="Translate validated trading decisions into broker-ready orders with reliable execution workflows."
          />

          <Feature
            icon={<BrainCircuit />}
            title="AI Intelligence"
            text="Add machine intelligence for signal evaluation, market regime detection and decision support."
          />

          <Feature
            icon={<Database />}
            title="Market Data"
            text="Centralize market data, historical information and real-time feeds for strategies and analytics."
          />

          <Feature
            icon={<Activity />}
            title="Analytics"
            text="Measure strategy performance, execution quality, risk and portfolio behaviour."
          />
        </div>
      </section>

      {/* =====================================================
                ARCHITECTURE
            ===================================================== */}

      <section className="architecture" id="architecture">
        <div className="architecture__content">
          <div className="section-heading">
            <span>ARCHITECTURE</span>

            <h2>
              Built as an
              <strong> intelligent pipeline.</strong>
            </h2>

            <p>
              Every trading decision moves through specialized layers before
              capital is put at risk.
            </p>
          </div>

          <div className="pipeline">
            <Pipeline number="01" title="Market Data" />

            <div className="pipeline-line" />

            <Pipeline number="02" title="Strategy" />

            <div className="pipeline-line" />

            <Pipeline number="03" title="AI Intelligence" />

            <div className="pipeline-line" />

            <Pipeline number="04" title="Risk Engine" />

            <div className="pipeline-line" />

            <Pipeline number="05" title="Execution" />
          </div>
        </div>
      </section>

      {/* =====================================================
                CTA
            ===================================================== */}

      <section className="cta">
        <div className="cta-glow" />

        <span>ATHENA QUANT ENGINE</span>

        <h2>
          Build the future of
          <strong> algorithmic trading.</strong>
        </h2>

        <p>
          Start building strategies, managing risk and executing trades from one
          intelligent platform.
        </p>

        <a href="/register" className="primary-btn">
          Create your account
          <ArrowRight size={18} />
        </a>
      </section>

      {/* =====================================================
                FOOTER
            ===================================================== */}

      <footer className="landing-footer">
        <div>
          <strong>AQE</strong>
          <span>Athena Quant Engine</span>
        </div>

        <p>Algorithmic trading infrastructure.</p>

        <span>© 2026 AQE</span>
      </footer>
    </main>
  );
};

/* ================================================================
   COMPONENTS
================================================================ */

const MarketRow = ({ symbol, value, change, positive }) => (
  <div className="market-row">
    <span className="market-symbol">{symbol}</span>

    <span className="market-value">{value.toFixed(2)}</span>

    <span className={positive ? "market-positive" : "market-negative"}>
      {change}
    </span>
  </div>
);

const Metric = ({ value, label }) => (
  <div className="metric">
    <strong>{value}</strong>

    <span>{label}</span>
  </div>
);

const Feature = ({ icon, title, text }) => (
  <div className="feature-card">
    <div className="feature-icon">{icon}</div>

    <h3>{title}</h3>

    <p>{text}</p>

    <div className="feature-arrow">
      <ArrowRight size={17} />
    </div>
  </div>
);

const Pipeline = ({ number, title }) => (
  <div className="pipeline-node">
    <span>{number}</span>

    <strong>{title}</strong>

    <ChevronDown size={15} />
  </div>
);

export default Landing;
