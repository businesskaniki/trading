import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";

import {
    Alert,
    Button,
    Paper,
    PasswordInput,
    PinInput,
    Stack,
    Text,
    Title,
} from "@mantine/core";

import { IconAlertCircle } from "@tabler/icons-react";

import { resetPassword } from "../../redux/auth/authThunks";
import {
    clearError,
    resetStatus,
} from "../../redux/auth/authSlice";

import "../../css/ResetPassword.css";

const ResetPassword = () => {
    const dispatch = useDispatch();
    const navigate = useNavigate();
    const location = useLocation();

    const { loading, error, success } = useSelector(
        (state) => state.auth
    );

    // Email is hidden from the UI but still available
    const email = location.state?.email || "";

    const [formData, setFormData] = useState({
        otp: "",
        new_password: "",
        confirmPassword: "",
    });

    useEffect(() => {
        if (success) {
            dispatch(resetStatus());

            navigate("/login", {
                replace: true,
            });
        }

        return () => {
            dispatch(clearError());
        };
    }, [success, dispatch, navigate]);

    const handleChange = (e) => {
        const { name, value } = e.target;

        setFormData((prev) => ({
            ...prev,
            [name]: value,
        }));
    };

    const handleSubmit = (e) => {
        e.preventDefault();

        if (formData.otp.length !== 6) {
            alert("Please enter the 6-digit verification code.");
            return;
        }

        if (formData.new_password !== formData.confirmPassword) {
            alert("Passwords do not match.");
            return;
        }

        dispatch(
            resetPassword({
                email, // Still sent to the backend
                otp: formData.otp,
                new_password: formData.new_password,
            })
        );
    };

    return (
        <div className="reset-page">
            <Paper
                shadow="lg"
                radius="md"
                p="xl"
                className="reset-card"
            >
                <Title order={2} ta="center">
                    Reset Password
                </Title>

                <Text
                    ta="center"
                    c="dimmed"
                    mb="xl"
                >
                    Enter the verification code and choose a new password.
                </Text>

                {error && (
                    <Alert
                        color="red"
                        icon={<IconAlertCircle size={18} />}
                        mb="md"
                    >
                        {typeof error === "string"
                            ? error
                            : JSON.stringify(error)}
                    </Alert>
                )}

                <form onSubmit={handleSubmit}>
                    <Stack>

                        <div>
                            <Text fw={500} mb={8}>
                                Verification Code
                            </Text>

                            <PinInput
                                length={6}
                                oneTimeCode
                                type="number"
                                value={formData.otp}
                                onChange={(value) =>
                                    setFormData((prev) => ({
                                        ...prev,
                                        otp: value,
                                    }))
                                }
                                size="lg"
                            />
                        </div>

                        <PasswordInput
                            label="New Password"
                            placeholder="Enter your new password"
                            name="new_password"
                            value={formData.new_password}
                            onChange={handleChange}
                            required
                        />

                        <PasswordInput
                            label="Confirm Password"
                            placeholder="Confirm your new password"
                            name="confirmPassword"
                            value={formData.confirmPassword}
                            onChange={handleChange}
                            required
                        />

                        <Button
                            type="submit"
                            loading={loading}
                            fullWidth
                        >
                            Reset Password
                        </Button>

                    </Stack>
                </form>

                <Text
                    ta="center"
                    mt="lg"
                    size="sm"
                >
                    <Link to="/login">
                        Back to Login
                    </Link>
                </Text>
            </Paper>
        </div>
    );
};

export default ResetPassword;