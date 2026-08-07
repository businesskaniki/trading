import { useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Link, useNavigate } from "react-router-dom";

import {
    Alert,
    Button,
    Paper,
    Stack,
    Text,
    TextInput,
    Title,
} from "@mantine/core";

import { IconAlertCircle } from "@tabler/icons-react";

import { forgotPassword } from "../../redux/auth/authThunks";

import "../../css/ForgotPassword.css";

const ForgotPassword = () => {
    const dispatch = useDispatch();
    const navigate = useNavigate();

    const { loading, error } = useSelector(
        (state) => state.auth
    );

    const [email, setEmail] = useState("");

    const handleSubmit = async (e) => {
        e.preventDefault();

        const result = await dispatch(
            forgotPassword({
                email: email.trim().toLowerCase(),
            })
        );

        if (!result.error) {
            navigate("/reset-password", {
                state: {
                    email: email.trim().toLowerCase(),
                },
            });
        }
    };

    return (
        <div className="forgot-page">
            <Paper
                shadow="lg"
                radius="md"
                p="xl"
                className="forgot-card"
            >
                <Title order={2} ta="center">
                    Forgot Password
                </Title>

                <Text
                    ta="center"
                    c="dimmed"
                    mb="xl"
                >
                    Enter your email address and we'll send you a password
                    reset verification code.
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

                        <TextInput
                            label="Email Address"
                            placeholder="john@example.com"
                            type="email"
                            value={email}
                            onChange={(e) =>
                                setEmail(e.target.value)
                            }
                            required
                        />

                        <Button
                            type="submit"
                            loading={loading}
                            fullWidth
                        >
                            Send Reset Code
                        </Button>

                    </Stack>
                </form>

                <Text
                    ta="center"
                    mt="lg"
                    size="sm"
                >
                    Remember your password?{" "}
                    <Link to="/login">
                        Back to Login
                    </Link>
                </Text>
            </Paper>
        </div>
    );
};

export default ForgotPassword;