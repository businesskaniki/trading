import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";

import {
  Paper,
  TextInput,
  PasswordInput,
  Button,
  Title,
  Text,
  Stack,
  Alert,
  Checkbox,
} from "@mantine/core";

import { IconAlertCircle, IconCircleCheck } from "@tabler/icons-react";

import { loginUser } from "../../redux/auth/authThunks";

import "../../css/login.css";

const Login = () => {
  const dispatch = useDispatch();
  const navigate = useNavigate();

  const { loading, error, success, isAuthenticated } = useSelector(
    (state) => state.auth,
  );

  const [formData, setFormData] = useState({
    email: "",
    password: "",
    remember: false,
  });

  // ==========================================================
  // Handle authentication success
  // ==========================================================

  useEffect(() => {
    if (isAuthenticated && success) {
      navigate("/dashboard", { replace: true });
    }
  }, [isAuthenticated, success, navigate]);

  // ==========================================================
  // Clear messages when leaving page
  // ==========================================================

  // ==========================================================
  // Handle input
  // ==========================================================

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;

    setFormData((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
  };

  // ==========================================================
  // Login
  // ==========================================================

  const handleSubmit = (e) => {
    e.preventDefault();

    dispatch(
      loginUser({
        email: formData.email,
        password: formData.password,
      }),
    );
    console.log(error);
  };

  return (
    <div className="login-page">
      <Paper shadow="lg" radius="md" p="xl" className="login-card">
        <Title order={2} ta="center">
          Athena Quant Engine
        </Title>

        <Text c="dimmed" ta="center" mb="xl">
          Sign in to your account
        </Text>

        {/* ==================================================
            ERROR
        ================================================== */}

        {error && (
          <Alert
            color="red"
            icon={<IconAlertCircle size={18} />}
            title="Login failed"
            mb="md"
          >
            {typeof error === "string"
              ? error
              : error?.detail || error?.message || "Unable to login."}
          </Alert>
        )}

        {/* ==================================================
            SUCCESS
        ================================================== */}

        {success && (
          <Alert
            color="green"
            icon={<IconCircleCheck size={18} />}
            title="Success"
            mb="md"
          >
            {success}
          </Alert>
        )}

        <form onSubmit={handleSubmit}>
          <Stack>
            <TextInput
              label="Email"
              placeholder="you@example.com"
              name="email"
              type="email"
              value={formData.email}
              onChange={handleChange}
              required
            />

            <PasswordInput
              label="Password"
              placeholder="Enter your password"
              name="password"
              value={formData.password}
              onChange={handleChange}
              required
            />

            <div className="login-options">
              <Checkbox
                label="Remember me"
                name="remember"
                checked={formData.remember}
                onChange={handleChange}
              />

              <Link to="/forgot-password" className="forgot-password-link">
                Forgot Password?
              </Link>
            </div>

            <Button
              type="submit"
              loading={loading}
              disabled={loading}
              fullWidth
              mt="md"
            >
              {loading ? "Signing in..." : "Login"}
            </Button>
          </Stack>
        </form>

        <Text ta="center" mt="lg" size="sm">
          Don't have an account? <Link to="/register">Register</Link>
        </Text>
      </Paper>
    </div>
  );
};

export default Login;
