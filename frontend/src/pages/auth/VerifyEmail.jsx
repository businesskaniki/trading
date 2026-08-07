import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";

import {
    Alert,
    Button,
    Paper,
    PinInput,
    Stack,
    Text,
    TextInput,
    Title,
} from "@mantine/core";

import { IconAlertCircle } from "@tabler/icons-react";

import {
    verifyEmail,
    resendOTP,
} from "../../redux/auth/authThunks";

import {
    clearError,
    resetStatus,
} from "../../redux/auth/authSlice";

import "../../css/VerifyEmail.css";

const VerifyEmail = () => {
    const dispatch = useDispatch();
    const navigate = useNavigate();

    const {
        loading,
        error,
        success,
        pendingVerificationEmail,
    } = useSelector((state) => state.auth);

    const [otp, setOtp] = useState("");

    useEffect(() => {
        if (success) {
            dispatch(resetStatus());

            navigate("/", {
                replace: true,
            });
        }

        return () => {
            dispatch(clearError());
        };
    }, [success, dispatch, navigate]);

    const handleVerify = (e) => {
        e.preventDefault();

        if (otp.length !== 6) return;

        dispatch(
            verifyEmail({
                email: pendingVerificationEmail,
                otp,
            })
        );
    };

    const handleResend = () => {
        dispatch(
            resendOTP({
                email: pendingVerificationEmail,
            })
        );
    };

    return (
        <div className="verify-page">
            <Paper
                shadow="lg"
                radius="md"
                p="xl"
                className="verify-card"
            >
                <Title order={2} ta="center">
                    Verify Your Email
                </Title>

                <Text
                    ta="center"
                    c="dimmed"
                    mb="xs"
                >
                    We've sent a verification code to
                </Text>

                <Text
                    ta="center"
                    fw={600}
                    mb="xl"
                >
                    {pendingVerificationEmail || "No email available"}
                </Text>

                {error && (
                    <Alert
                        color="red"
                        mb="md"
                        icon={<IconAlertCircle size={18} />}
                    >
                        {typeof error === "string"
                            ? error
                            : JSON.stringify(error)}
                    </Alert>
                )}

                <form onSubmit={handleVerify}>
                    <Stack align="center">
                        <TextInput
                            label="Email"
                            value={pendingVerificationEmail || ""}
                            readOnly
                            w="100%"
                        />

                        <PinInput
                            length={6}
                            oneTimeCode
                            type="number"
                            value={otp}
                            onChange={setOtp}
                            size="lg"
                        />

                        <Button
                            type="submit"
                            loading={loading}
                            fullWidth
                        >
                            Verify Email
                        </Button>

                        <Button
                            variant="light"
                            onClick={handleResend}
                            loading={loading}
                            fullWidth
                        >
                            Resend Code
                        </Button>
                    </Stack>
                </form>

                <Text
                    ta="center"
                    mt="lg"
                    size="sm"
                >
                    Already verified?{" "}
                    <Link to="/login">
                        Login
                    </Link>
                </Text>
            </Paper>
        </div>
    );
};

export default VerifyEmail;