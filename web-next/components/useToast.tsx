"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Icon from "@/components/Icon";

type Msg = { text: string; err: boolean } | null;

/** Aviso flotante. Va en la «capa superior» del navegador (popover): si no, un <dialog> abierto lo tapa y nadie ve el error. */
export function ToastView({ msg }: { msg: Msg }) {
  const ref = useRef<HTMLDivElement & { showPopover?: () => void; hidePopover?: () => void }>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el?.showPopover) return; // navegador sin popover: queda como un aviso normal
    try {
      const open = el.matches(":popover-open");
      if (msg && !open) el.showPopover();
      else if (!msg && open) el.hidePopover?.();
    } catch { /* sin soporte */ }
  }, [msg]);
  return <div ref={ref} popover="manual" role={msg?.err ? "alert" : "status"} aria-live={msg?.err ? "assertive" : "polite"} className={"toast" + (msg ? " show" : "") + (msg?.err ? " err" : "")}>{msg && <Icon n={msg.err ? "alert" : "checkc"} />} {msg?.text}</div>;
}

export function useToast(): [React.ReactNode, (text: string, err?: boolean) => void] {
  const [msg, setMsg] = useState<Msg>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const toast = useCallback((text: string, err = false) => {
    setMsg({ text, err });
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setMsg(null), 3200);
  }, []);
  return [<ToastView msg={msg} />, toast];
}
