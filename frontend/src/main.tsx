import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import "./index.css";
import App from "./App.tsx";
import { ensureSession, retryUnlessClientError } from "./api/client";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: retryUnlessClientError } } });

// Establish the session before anything fetches. Otherwise, on a first visit the plan query,
// the chat history and the EventSource all start with a 401 (which the browser logs as console
// errors) and only then recover through ensureSession. POST /api/session is a no-op while the
// cookie is valid; if it fails here, the per-request 401 handling still takes over.
void ensureSession()
  .catch(() => undefined)
  .finally(() => {
    createRoot(document.getElementById("root")!).render(
      <StrictMode>
        <QueryClientProvider client={queryClient}>
          <App />
          <Toaster richColors position="top-right" />
        </QueryClientProvider>
      </StrictMode>,
    );
  });
