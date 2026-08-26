import { useEffect, useState } from "react";
import "../../../css/accountsform.css"
import {
    FaTimes,
    FaWallet,
    FaServer,
    FaChartLine,
    FaCog,
} from "react-icons/fa";


const initialForm = {
    broker: "MT5",
    account_number: "",
    server: "",
    account_name: "",
    currency: "USD",
    leverage: "",
    balance: "",
    equity: "",
    margin: "",
    free_margin: "",
    margin_level: "",
    is_demo: true,
    status: "DISCONNECTED",
    active: true,
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
                account_number: account.account_number ?? "",
                server: account.server ?? "",
                account_name: account.account_name ?? "",
                currency: account.currency ?? "USD",
                leverage: account.leverage ?? "",
                balance: account.balance ?? "",
                equity: account.equity ?? "",
                margin: account.margin ?? "",
                free_margin: account.free_margin ?? "",
                margin_level: account.margin_level ?? "",
                is_demo: account.is_demo ?? true,
                status: account.status ?? "DISCONNECTED",
                active: account.active ?? true,
            });

        } else {

            setFormData(initialForm);

        }

        setErrors({});

    }, [account, isOpen]);


    /* ==========================================
       CHANGE HANDLER
    ========================================== */

    const handleChange = (event) => {

        const {
            name,
            value,
            type,
            checked,
        } = event.target;


        setFormData((previous) => ({
            ...previous,

            [name]:
                type === "checkbox"
                    ? checked
                    : value,
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


        if (!formData.account_number) {
            newErrors.account_number =
                "Account number is required.";
        }


        if (!formData.server.trim()) {
            newErrors.server =
                "Server is required.";
        }


        if (!formData.account_name.trim()) {
            newErrors.account_name =
                "Account name is required.";
        }


        if (!formData.currency.trim()) {
            newErrors.currency =
                "Currency is required.";
        }


        if (!formData.leverage) {
            newErrors.leverage =
                "Leverage is required.";
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
            ...formData,

            account_number:
                Number(formData.account_number),

            leverage:
                Number(formData.leverage),

            balance:
                Number(formData.balance || 0),

            equity:
                Number(formData.equity || 0),

            margin:
                Number(formData.margin || 0),

            free_margin:
                Number(formData.free_margin || 0),

            margin_level:
                Number(formData.margin_level || 0),

        };


        onSubmit(payload);

    };


    /* ==========================================
       CLOSE
    ========================================== */

    const handleOverlayClick = (event) => {

        if (
            event.target === event.currentTarget &&
            !loading
        ) {
            onClose();
        }

    };


    if (!isOpen) {
        return null;
    }


    return (
        <div
            className="account-modal-overlay"
            onMouseDown={handleOverlayClick}
        >

            <div className="account-modal">

                {/* ======================================
                    HEADER
                ====================================== */}

                <div className="account-modal__header">

                    <div>

                        <span className="account-modal__eyebrow">
                            {account
                                ? "ACCOUNT CONFIGURATION"
                                : "TRADING INFRASTRUCTURE"}
                        </span>

                        <h2>
                            {account
                                ? "Edit Trading Account"
                                : "Create Trading Account"}
                        </h2>

                        <p>
                            {account
                                ? "Update the configuration of this trading account."
                                : "Add a new broker account to the AQE trading infrastructure."}
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


                <form
                    className="account-form"
                    onSubmit={handleSubmit}
                >

                    {/* ==================================
                        BROKER INFORMATION
                    ================================== */}

                    <div className="account-form__section">

                        <div className="account-form__section-header">

                            <div className="account-form__section-icon">
                                <FaServer />
                            </div>

                            <div>

                                <h3>
                                    Broker Information
                                </h3>

                                <p>
                                    Connection and account identification.
                                </p>

                            </div>

                        </div>


                        <div className="account-form__grid">

                            {/* Broker */}

                            <div className="account-field">

                                <label>
                                    Broker
                                </label>

                                <select
                                    name="broker"
                                    value={formData.broker}
                                    onChange={handleChange}
                                >
                                    <option value="MT5">
                                        MetaTrader 5
                                    </option>

                                    <option value="MT4">
                                        MetaTrader 4
                                    </option>
                                    <option value="JM">
                                        JustMarkets
                                    </option>
                                </select>

                                {errors.broker && (
                                    <small>
                                        {errors.broker}
                                    </small>
                                )}

                            </div>


                            {/* Account Number */}

                            <div className="account-field">

                                <label>
                                    Account Number
                                </label>

                                <input
                                    type="number"
                                    name="account_number"
                                    value={formData.account_number}
                                    onChange={handleChange}
                                    placeholder="e.g. 1200122668"
                                />

                                {errors.account_number && (
                                    <small>
                                        {errors.account_number}
                                    </small>
                                )}

                            </div>


                            {/* Account Name */}

                            <div className="account-field">

                                <label>
                                    Account Name
                                </label>

                                <input
                                    type="text"
                                    name="account_name"
                                    value={formData.account_name}
                                    onChange={handleChange}
                                    placeholder="e.g. Main Trading Account"
                                />

                                {errors.account_name && (
                                    <small>
                                        {errors.account_name}
                                    </small>
                                )}

                            </div>


                            {/* Server */}

                            <div className="account-field">

                                <label>
                                    Server
                                </label>

                                <input
                                    type="text"
                                    name="server"
                                    value={formData.server}
                                    onChange={handleChange}
                                    placeholder="e.g. JustMarkets-Demo3"
                                />

                                {errors.server && (
                                    <small>
                                        {errors.server}
                                    </small>
                                )}

                            </div>


                            {/* Currency */}

                            <div className="account-field">

                                <label>
                                    Currency
                                </label>

                                <select
                                    name="currency"
                                    value={formData.currency}
                                    onChange={handleChange}
                                >

                                    <option value="USD">
                                        USD
                                    </option>

                                    <option value="EUR">
                                        EUR
                                    </option>

                                    <option value="GBP">
                                        GBP
                                    </option>

                                    <option value="KES">
                                        KES
                                    </option>

                                </select>

                                {errors.currency && (
                                    <small>
                                        {errors.currency}
                                    </small>
                                )}

                            </div>


                            {/* Leverage */}

                            <div className="account-field">

                                <label>
                                    Leverage
                                </label>

                                <input
                                    type="number"
                                    name="leverage"
                                    value={formData.leverage}
                                    onChange={handleChange}
                                    placeholder="e.g. 500"
                                    min="1"
                                />

                                {errors.leverage && (
                                    <small>
                                        {errors.leverage}
                                    </small>
                                )}

                            </div>

                        </div>

                    </div>


                    {/* ==================================
                        ACCOUNT METRICS
                    ================================== */}

                    <div className="account-form__section">

                        <div className="account-form__section-header">

                            <div className="account-form__section-icon">
                                <FaChartLine />
                            </div>

                            <div>

                                <h3>
                                    Account Metrics
                                </h3>

                                <p>
                                    Current financial account values.
                                </p>

                            </div>

                        </div>


                        <div className="account-form__grid">

                            <div className="account-field">

                                <label>
                                    Balance
                                </label>

                                <input
                                    type="number"
                                    step="any"
                                    name="balance"
                                    value={formData.balance}
                                    onChange={handleChange}
                                    placeholder="0.00"
                                />

                            </div>


                            <div className="account-field">

                                <label>
                                    Equity
                                </label>

                                <input
                                    type="number"
                                    step="any"
                                    name="equity"
                                    value={formData.equity}
                                    onChange={handleChange}
                                    placeholder="0.00"
                                />

                            </div>


                            <div className="account-field">

                                <label>
                                    Margin
                                </label>

                                <input
                                    type="number"
                                    step="any"
                                    name="margin"
                                    value={formData.margin}
                                    onChange={handleChange}
                                    placeholder="0.00"
                                />

                            </div>


                            <div className="account-field">

                                <label>
                                    Free Margin
                                </label>

                                <input
                                    type="number"
                                    step="any"
                                    name="free_margin"
                                    value={formData.free_margin}
                                    onChange={handleChange}
                                    placeholder="0.00"
                                />

                            </div>


                            <div className="account-field account-field--full">

                                <label>
                                    Margin Level
                                </label>

                                <input
                                    type="number"
                                    step="any"
                                    name="margin_level"
                                    value={formData.margin_level}
                                    onChange={handleChange}
                                    placeholder="0.00"
                                />

                            </div>

                        </div>

                    </div>


                    {/* ==================================
                        CONFIGURATION
                    ================================== */}

                    <div className="account-form__section">

                        <div className="account-form__section-header">

                            <div className="account-form__section-icon">
                                <FaCog />
                            </div>

                            <div>

                                <h3>
                                    Configuration
                                </h3>

                                <p>
                                    Account environment and operational status.
                                </p>

                            </div>

                        </div>


                        <div className="account-form__grid">

                            {/* Environment */}

                            <div className="account-field">

                                <label>
                                    Environment
                                </label>

                                <select
                                    name="is_demo"
                                    value={
                                        formData.is_demo
                                            ? "DEMO"
                                            : "LIVE"
                                    }
                                    onChange={(event) => {

                                        setFormData((previous) => ({
                                            ...previous,
                                            is_demo:
                                                event.target.value === "DEMO",
                                        }));

                                    }}
                                >

                                    <option value="DEMO">
                                        Demo
                                    </option>

                                    <option value="LIVE">
                                        Live
                                    </option>

                                </select>

                            </div>


                            {/* Status */}

                            <div className="account-field">

                                <label>
                                    Status
                                </label>

                                <select
                                    name="status"
                                    value={formData.status}
                                    onChange={handleChange}
                                >

                                    <option value="DISCONNECTED">
                                        Disconnected
                                    </option>

                                    <option value="CONNECTED">
                                        Connected
                                    </option>

                                </select>

                            </div>


                            {/* Active */}

                            <div className="account-field account-field--toggle">

                                <label>
                                    Account Status
                                </label>

                                <label className="account-toggle">

                                    <input
                                        type="checkbox"
                                        name="active"
                                        checked={formData.active}
                                        onChange={handleChange}
                                    />

                                    <span />

                                    <strong>
                                        Account Active
                                    </strong>

                                </label>

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

                                    {account
                                        ? "Save Changes"
                                        : "Create Account"}
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