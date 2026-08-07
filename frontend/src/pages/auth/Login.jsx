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

import { IconAlertCircle } from "@tabler/icons-react";

import { loginUser } from "../../redux/auth/authThunks";
import { clearError } from "../../redux/auth/authSlice";

import "../../css/login.css";

const Login = () => {
  const dispatch = useDispatch();
  const navigate = useNavigate();

  const { loading, error, isAuthenticated } = useSelector(
    (state) => state.auth,
  );

  const [formData, setFormData] = useState({
    email: "",
    password: "",
    remember: false,
  });

  useEffect(() => {
    if (isAuthenticated) {
      navigate("/dashboard");
    }

    return () => {
      dispatch(clearError());
    };
  }, [isAuthenticated, navigate, dispatch]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;

    setFormData((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    dispatch(
      loginUser({
        email: formData.email,
        password: formData.password,
      }),
    );
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

        {error && (
          <Alert color="red" icon={<IconAlertCircle size={18} />} mb="md">
            {typeof error === "string" ? error : JSON.stringify(error)}
          </Alert>
        )}

        <form onSubmit={handleSubmit}>
          <Stack>
            <TextInput
              label="Email"
              placeholder="you@example.com"
              name="email"
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

            <Button type="submit" loading={loading} fullWidth mt="md">
              Login
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
