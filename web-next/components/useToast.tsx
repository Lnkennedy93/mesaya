"use client";
import { useCallback, useRef, useState } from "react";

/** Aviso flotante (misma apariencia que el .toast de web/assets/app.css). */
export function useToast(): [React.ReactNode, (text: string, err?: boolean) => void] {
  const [msg, setMsg] = useState<{ text: string; err: boolean } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const toast = useCallback((text: string, err = false) => {
    setMsg({ text, err });
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setMsg(null), 3200);
  }, []);
  const node = <div className={"toast" + (msg ? " show" : "") + (msg?.err ? " err" : "")}>{msg?.text}</div>;
  return [node, toast];
}
