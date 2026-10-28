"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";

type ToastState = { message: string; onUndo: () => void } | null;

const ToastContext = createContext<{ showUndo: (message: string, onUndo: () => void) => void } | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toast, setToast] = useState<ToastState>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showUndo = useCallback((message: string, onUndo: () => void) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setToast({ message, onUndo });
    timerRef.current = setTimeout(() => setToast(null), 6000);
  }, []);

  function handleUndo() {
    if (timerRef.current) clearTimeout(timerRef.current);
    toast?.onUndo();
    setToast(null);
  }

  return (
    <ToastContext.Provider value={{ showUndo }}>
      {children}
      {toast && (
        <div
          className="fixed bottom-20 md:bottom-6 left-1/2 -translate-x-1/2 z-[200] flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg"
          style={{ background: "var(--panel-raised)", border: "1px solid var(--border-strong)" }}
          role="status"
        >
          <span className="text-sm text-main">{toast.message}</span>
          <button onClick={handleUndo} className="btn-ghost text-xs font-semibold shrink-0">
            Undo
          </button>
        </div>
      )}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
