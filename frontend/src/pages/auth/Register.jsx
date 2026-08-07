import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";

import {
  Alert,
  Button,
  Paper,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";

import { IconAlertCircle } from "@tabler/icons-react";

import { registerUser } from "../../redux/auth/authThunks";
import { clearError, resetStatus } from "../../redux/auth/authSlice";

import "../../css/Register.css";

const Register = () => {
  const dispatch = useDispatch();
  const navigate = useNavigate();

  const { loading, error } = useSelector((state) => state.auth);

  const [formData, setFormData] = useState({
    full_name: "",
    email: "",
    password: "",
    confirmPassword: "",
  });

  // ONLY use useEffect to clean up old errors when leaving the page
  useEffect(() => {
    return () => {
      dispatch(clearError());
    };
  }, [dispatch]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (formData.password !== formData.confirmPassword) {
      return;
    }

    const result = await dispatch(
      registerUser({
        full_name: formData.full_name.trim(),
        email: formData.email.trim().toLowerCase(),
        password: formData.password,
      }),
    );

    // This handles the redirect perfectly upon a verified API success
    if (registerUser.fulfilled.match(result)) {
      dispatch(resetStatus()); // Clean up status safely right before moving
      navigate("/verify-email");
    }
  };

  return (
    <div className="register-page">
      <Paper shadow="lg" radius="md" p="xl" className="register-card">
        <Title order={2} ta="center">
          Create Account
        </Title>

        <Text ta="center" c="dimmed" mb="xl">
          Create your Athena Quant Engine account
        </Text>

        {error && (
          <Alert color="red" mb="md" icon={<IconAlertCircle size={18} />}>
            {typeof error === "string" ? error : JSON.stringify(error)}
          </Alert>
        )}

        <form onSubmit={handleSubmit}>
          <Stack>
            <TextInput
              label="Full Name"
              placeholder="John Doe"
              name="full_name"
              value={formData.full_name}
              onChange={handleChange}
              required
            />

            <TextInput
              label="Email Address"
              placeholder="john@example.com"
              type="email"
              name="email"
              value={formData.email}
              onChange={handleChange}
              required
            />

            <PasswordInput
              label="Password"
              placeholder="Enter a strong password"
              name="password"
              value={formData.password}
              onChange={handleChange}
              required
            />

            <PasswordInput
              label="Confirm Password"
              placeholder="Confirm your password"
              name="confirmPassword"
              value={formData.confirmPassword}
              onChange={handleChange}
              required
            />

            <Button type="submit" loading={loading} fullWidth mt="md">
              Create Account
            </Button>
          </Stack>
        </form>

        <Text ta="center" mt="lg" size="sm">
          Already have an account? <Link to="/login">Login</Link>
        </Text>
      </Paper>
    </div>
  );
};

export default Register;
