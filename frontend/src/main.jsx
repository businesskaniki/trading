import React from "react";
import { StrictMode } from "react";
import { BrowserRouter } from "react-router-dom";
import { Provider } from "react-redux";
import { MantineProvider } from "@mantine/core";

import "@mantine/core/styles.css";

import ReactDOM from "react-dom/client";

import App from "./App";
import store from "./redux/store";

import { refreshAccessToken } from "./redux/auth/authThunks";

import { setAuthInitialized } from "./redux/auth/authSlice";

import "./index.css";

// ==========================================================
// Restore authentication before rendering the application
// ==========================================================

const restoreAuthentication = async () => {
  const accessToken = localStorage.getItem("access_token");


  // --------------------------------------------------
  // No session exists
  // --------------------------------------------------

  if (!accessToken) {
    store.dispatch(setAuthInitialized());

    return;
  }

  // --------------------------------------------------
  // Try to refresh the access token
  //
  // This happens on EVERY browser reload.
  //
  // If the access token is still valid, the backend
  // may still issue a fresh one depending on your
  // backend implementation.
  //
  // If it is expired, the refresh token keeps the
  // user logged in.
  // --------------------------------------------------

  try {
    await store.dispatch(refreshAccessToken()).unwrap();
  } catch (error) {
    console.log("Session could not be restored:", error);

    store.dispatch(setAuthInitialized());
  }
};

// ==========================================================
// Bootstrap application
// ==========================================================

const bootstrap = async () => {
  await restoreAuthentication();

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
};

bootstrap();
