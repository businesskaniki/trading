import React, { StrictMode } from "react";
import { BrowserRouter } from "react-router-dom";
import { Provider } from "react-redux";
import { MantineProvider } from "@mantine/core";
import "@mantine/core/styles.css";
import ReactDOM from "react-dom/client";

import App from "./App";
import store from "./redux/store";
import { refreshAccessToken } from "./redux/auth/authThunks";

import "./index.css";

// --------------------------------------------------
// START AUTH RESTORATION
// --------------------------------------------------
//
// Do not block React mounting on the refresh request.
//
// ProtectedRoute/PublicRoute already use authInitialized
// to wait for authentication state before deciding where
// the user should go.
//
// This allows the application shell to mount immediately
// while authentication is restored in the background.
// --------------------------------------------------

store
  .dispatch(refreshAccessToken())
  .unwrap()
  .catch((error) => {
    console.info("No active session could be restored.", error);
  });

// --------------------------------------------------
// MOUNT APPLICATION
// --------------------------------------------------

ReactDOM.createRoot(document.getElementById("root")).render(
  <StrictMode>
    <Provider store={store}>
      <MantineProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </MantineProvider>
    </Provider>
  </StrictMode>,
);