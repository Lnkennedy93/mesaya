"use client";
import { createContext, useContext } from "react";

export type Any = any;

export type AdminCtxValue = {
  ME: Any;
  setME: (m: Any) => void;
  money: (v: number) => string;
  toMajor: (v: number) => number;
  toMinor: (v: Any) => number;
  toast: (text: string, err?: boolean) => void;
};

export const AdminCtx = createContext<AdminCtxValue>(null as unknown as AdminCtxValue);
export const useAdmin = () => useContext(AdminCtx);

export const CURRENCIES = ["COP", "USD", "MXN", "PEN", "CLP", "ARS", "EUR", "GTQ", "DOP"];
