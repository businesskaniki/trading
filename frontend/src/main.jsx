import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Provider } from "react-redux";
import { MantineProvider } from "@mantine/core";

import App from "./App";
import store from "./redux/store";

import "@mantine/core/styles.css";
import "./index.css";

createRoot(document.getElementById("root")).render(
    <StrictMode>
        <Provider store={store}>
            <MantineProvider>
                <BrowserRouter>
                    <App />
                </BrowserRouter>
            </MantineProvider>
        </Provider>
    </StrictMode>
);