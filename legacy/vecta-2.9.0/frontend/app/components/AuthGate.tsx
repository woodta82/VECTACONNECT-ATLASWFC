"use client";

import { useEffect, useState } from "react";
import { registerUnauthorizedHandler } from "@/lib/api";
import LoginScreen from "./LoginScreen";

export default function AuthGate({ children }: { children: React.ReactNode }) {
  // Deliberately plain useState with no persistence read on mount — a
  // page reload always starts unauthenticated, which is the whole point
  // of this gate ("log in every time the page is accessed").
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    registerUnauthorizedHandler(() => setAuthenticated(false));
    return () => registerUnauthorizedHandler(null);
  }, []);

  if (!authenticated) {
    return <LoginScreen onSuccess={() => setAuthenticated(true)} />;
  }

  return <>{children}</>;
}
