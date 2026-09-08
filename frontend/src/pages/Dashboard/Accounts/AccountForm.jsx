import { useEffect, useState } from "react";
import "../../../css/accountsform.css";

import { FaTimes, FaWallet, FaServer, FaCog } from "react-icons/fa";

const initialForm = {
  broker: "MT5",
  login: "",
  server: "",
  account_name: "",
  password: "",
  bridge_url: "",
  is_demo: true,
};

const AccountForm = ({
  isOpen,
  onClose,
  onSubmit,
  account = null,
  loading = false,
}) => {
  const [formData, setFormData] = useState(initialForm);

  const [errors, setErrors] = useState({});

  /* ==========================================
       INITIALIZE FORM
    ========================================== */

  useEffect(() => {
    if (account) {
      setFormData({
        broker: account.broker ?? "MT5",
        login: account.login ?? "",
        server: account.server ?? "",
        account_name: account.account_name ?? "",
        password: "",
        bridge_url: account.bridge_url ?? "",
        is_demo: account.is_demo ?? true,
      });
    } else {
      setFormData({
        ...initialForm,
      });
    }

    setErrors({});
  }, [account, isOpen]);

  /* ==========================================
       CHANGE HANDLER
    ========================================== */

  const handleChange = (event) => {
    const { name, value, type, checked } = event.target;

    setFormData((previous) => ({
      ...previous,

      [name]: type === "checkbox" ? checked : value,
    }));

    if (errors[name]) {
      setErrors((previous) => ({
        ...previous,
        [name]: "",
      }));
    }
  };

  /* ==========================================
       VALIDATION
    ========================================== */

  const validate = () => {
    const newErrors = {};

    if (!formData.broker.trim()) {
      newErrors.broker = "Broker is required.";
    }

    if (!formData.login) {
      newErrors.login = "Account login is required.";
    } else if (Number(formData.login) <= 0) {
      newErrors.login = "Account login must be greater than zero.";
    }

    if (!formData.server.trim()) {
      newErrors.server = "Server is required.";
    }

    if (!formData.account_name.trim()) {
      newErrors.account_name = "Account name is required.";
    }

    /*
     * Password is required when creating
     * a new trading account.
     *
     * When editing an existing account,
     * leaving it empty means:
     * "keep the existing password".
     */

    if (!account && !formData.password.trim()) {
      newErrors.password = "Password is required.";
    }

    return newErrors;
  };

  /* ==========================================
       SUBMIT
    ========================================== */

  const handleSubmit = (event) => {
    event.preventDefault();

    const validationErrors = validate();

    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);

      return;
    }

    const payload = {
      broker: formData.broker,

      login: Number(formData.login),

      server: formData.server.trim(),

      account_name: formData.account_name.trim(),

      is_demo: Boolean(formData.is_demo),

      bridge_url: formData.bridge_url.trim() || null,
    };

    /*
     * Only send password when:
     *
     * 1. Creating an account, or
     * 2. The user explicitly entered a
     *    new password while editing.
     */

    if (formData.password.trim()) {
      payload.password = formData.password;
    }

    onSubmit(payload);
  };

  /* ==========================================
       CLOSE
    ========================================== */

  const handleOverlayClick = (event) => {
    if (event.target === event.currentTarget && !loading) {
      onClose();
    }
  };

  /* ==========================================
       RENDER
    ========================================== */

  if (!isOpen) {
    return null;
  }

  return (
    <div className="account-modal-overlay" onMouseDown={handleOverlayClick}>
      <div className="account-modal">
        {/* ======================================
                    HEADER
                ====================================== */}

        <div className="account-modal__header">
          <div>
            <span className="account-modal__eyebrow">
              {account ? "ACCOUNT CONFIGURATION" : "TRADING INFRASTRUCTURE"}
            </span>

            <h2>
              {account ? "Edit Trading Account" : "Create Trading Account"}
            </h2>

            <p>
              {account
                ? "Update the connection details for this trading account."
                : "Connect a MetaTrader 5 trading account to the AQE trading infrastructure."}
            </p>
          </div>

          <button
            type="button"
            className="account-modal__close"
            onClick={onClose}
            disabled={loading}
            aria-label="Close"
          >
            <FaTimes />
          </button>
        </div>

        <form className="account-form" onSubmit={handleSubmit}>
          {/* ==================================
                        BROKER INFORMATION
                    ================================== */}

          <div className="account-form__section">
            <div className="account-form__section-header">
              <div className="account-form__section-icon">
                <FaServer />
              </div>

              <div>
                <h3>Broker Information</h3>

                <p>Connection and account identification.</p>
              </div>
            </div>

            <div className="account-form__grid">
              {/* Broker */}

              <div className="account-field">
                <label htmlFor="broker">Broker / Platform</label>

                <select
                  id="broker"
                  name="broker"
                  value={formData.broker}
                  onChange={handleChange}
                  disabled={loading}
                >
                  <option value="MT5">MetaTrader 5</option>

                  <option value="BINANCE">Binance</option>

                  <option value="FIX">FIX</option>
                </select>

                {errors.broker && <small>{errors.broker}</small>}
              </div>

              {/* Login */}

              <div className="account-field">
                <label htmlFor="login">Account Login</label>

                <input
                  id="login"
                  type="number"
                  name="login"
                  value={formData.login}
                  onChange={handleChange}
                  placeholder="e.g. 1200122668"
                  min="1"
                  disabled={loading}
                />

                {errors.login && <small>{errors.login}</small>}
              </div>

              {/* Account Name */}

              <div className="account-field">
                <label htmlFor="account_name">Account Name</label>

                <input
                  id="account_name"
                  type="text"
                  name="account_name"
                  value={formData.account_name}
                  onChange={handleChange}
                  placeholder="e.g. Main Trading Account"
                  maxLength={100}
                  disabled={loading}
                />

                {errors.account_name && <small>{errors.account_name}</small>}
              </div>

              {/* Server */}

              <div className="account-field">
                <label htmlFor="server">Trading Server</label>

                <input
                  id="server"
                  type="text"
                  name="server"
                  value={formData.server}
                  onChange={handleChange}
                  placeholder="e.g. JustMarkets-Demo3"
                  maxLength={100}
                  disabled={loading}
                />

                {errors.server && <small>{errors.server}</small>}
              </div>

              {/* Password */}

              <div className="account-field">
                <label htmlFor="password">
                  {account ? "Trading Password" : "Trading Password"}
                </label>

                <input
                  id="password"
                  type="password"
                  name="password"
                  value={formData.password}
                  onChange={handleChange}
                  placeholder={
                    account
                      ? "Leave blank to keep current password"
                      : "Enter trading account password"
                  }
                  autoComplete="new-password"
                  disabled={loading}
                />

                {errors.password && <small>{errors.password}</small>}
              </div>

              {/* Bridge URL */}

              <div className="account-field">
                <label htmlFor="bridge_url">MT5 Bridge URL</label>

                <input
                  id="bridge_url"
                  type="url"
                  name="bridge_url"
                  value={formData.bridge_url}
                  onChange={handleChange}
                  placeholder="http://127.0.0.1:9000"
                  disabled={loading}
                />

                <small>Address of the AQE MT5 bridge.</small>
              </div>
            </div>
          </div>

          {/* ==================================
                        ENVIRONMENT
                    ================================== */}

          <div className="account-form__section">
            <div className="account-form__section-header">
              <div className="account-form__section-icon">
                <FaCog />
              </div>

              <div>
                <h3>Environment</h3>

                <p>Choose whether this account is a demo or live account.</p>
              </div>
            </div>

            <div className="account-form__grid">
              <div className="account-field">
                <label htmlFor="is_demo">Environment</label>

                <select
                  id="is_demo"
                  name="is_demo"
                  value={formData.is_demo ? "DEMO" : "LIVE"}
                  onChange={(event) => {
                    setFormData((previous) => ({
                      ...previous,

                      is_demo: event.target.value === "DEMO",
                    }));
                  }}
                  disabled={loading}
                >
                  <option value="DEMO">Demo</option>

                  <option value="LIVE">Live</option>
                </select>
              </div>

              <div className="account-field account-field--toggle">
                <label>Account Status</label>

                <label className="account-toggle">
                  <input
                    type="checkbox"
                    name="active"
                    checked={true}
                    readOnly
                  />

                  <span />

                  <strong>Account Active</strong>
                </label>
              </div>
            </div>
          </div>

          {/* ==================================
                        INFORMATION
                    ================================== */}

          <div className="account-form__section">
            <div className="account-form__section-header">
              <div className="account-form__section-icon">
                <FaWallet />
              </div>

              <div>
                <h3>Account Information</h3>

                <p>Account financial metrics are synchronized from MT5.</p>
              </div>
            </div>

            <div className="account-form__grid">
              <div className="account-field account-field--full">
                <div className="account-info-message">
                  <strong>Automatic account synchronization</strong>

                  <p>
                    Balance, equity, margin, free margin, margin level,
                    currency, leverage and connection status are obtained from
                    the connected trading account. They should not be manually
                    entered here.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* ==================================
                        FOOTER
                    ================================== */}

          <div className="account-modal__footer">
            <button
              type="button"
              className="account-modal__cancel"
              onClick={onClose}
              disabled={loading}
            >
              Cancel
            </button>

            <button
              type="submit"
              className="account-modal__submit"
              disabled={loading}
            >
              {loading ? (
                <>
                  <span className="account-form-spinner" />
                  Saving...
                </>
              ) : (
                <>
                  <FaWallet />

                  {account ? "Save Changes" : "Create Account"}
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default AccountForm;
