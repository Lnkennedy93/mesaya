"use client";
// Carta del comensal: portada de web/menu.html a React. Mismos endpoints /api/public/<slug>/..., mismas reglas.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, liveStream, ls, makeMoney, setBrand } from "@/lib/api";
import { I18N } from "@/lib/i18n";
import Powered from "@/components/Powered";

type Any = any;
type CartLine = { item_id: number; name: string; qty: number; unit: number; options: { group: string; name: string }[]; note: string };
type Dlg =
  | null
  | { t: "item"; id: number }
  | { t: "cart" }
  | { t: "nequi"; res: Any; phase: "wait" | "fail"; timeout?: boolean }
  | { t: "breb"; res: Any; phase: "ask" | "check" | "fail" }
  | { t: "thanks"; paymentId?: number; invoice?: Any };

const STATUS_IDX: Record<string, number> = { new: 0, preparing: 1, ready: 2, served: 3 };
const initial = (n: string) => n.trim().charAt(0).toUpperCase();

export default function MenuApp({ slug, table: TABLE, tableKey: KEY, initialView, justPaid }: { slug: string; table: string; tableKey: string; initialView: "menu" | "bill"; justPaid: boolean }) {
  const [lang, setLang] = useState("es");
  const [M, setM] = useState<Any>(null);
  const [error, setError] = useState("");
  const [bill, setBill] = useState<Any>({ lines: [], calls: [] });
  const [cart, setCart] = useState<CartLine[]>([]);
  const [view, setView] = useState<"menu" | "bill">(initialView);
  const [activeCat, setActiveCat] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [tipPct, setTipPct] = useState<number | null>(null);
  const [dlg, setDlg] = useState<Dlg>(null);
  const [toastMsg, setToastMsg] = useState<{ text: string; err: boolean } | null>(null);
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [rated, setRated] = useState(false);
  const [reviewUrl, setReviewUrl] = useState("");
  const [phone, setPhone] = useState("");
  const [inv, setInv] = useState<Any>({ doc_type: "CC", doc_number: "", name: "", email: "", open: undefined });
  const [dinerName, setDinerName] = useState("");

  const dinerId = useRef("");
  const billRef = useRef<Any>(bill);
  const billInit = useRef(false);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  billRef.current = bill;

  const T = useCallback((k: string): Any => (I18N[lang] || I18N.es)[k], [lang]);
  const money = useMemo(() => (M ? makeMoney(M.restaurant.decimals, M.restaurant.currency) : (v: number) => String(v)), [M]);
  const q = (s: string) => encodeURIComponent(s);

  const toast = useCallback((text: string, err = false) => {
    setToastMsg({ text, err });
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToastMsg(null), 3200);
  }, []);

  const refreshBill = useCallback(async () => {
    try {
      setBill(await api(`/api/public/${slug}/bill?table=${q(TABLE)}&k=${q(KEY)}`));
    } catch {
      /* mantener lo que había */
    }
  }, [slug, TABLE, KEY]);

  // ---- arranque
  useEffect(() => {
    let l = ls("mesaya_lang") || (navigator.language || "es").slice(0, 2);
    if (!I18N[l]) l = "es";
    setLang(l);
    dinerId.current = ls("mesaya_diner") || (() => { const v = crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2); ls("mesaya_diner", v); return v; })();
    setDinerName(ls("mesaya_name") || "");
    setPhone(ls("mesaya_phone") || "");
    try { setInv((i: Any) => ({ ...i, ...JSON.parse(ls("mesaya_inv") || "{}") })); } catch { /* sin datos */ }
    try { setCart(JSON.parse(ls("mesaya_cart_" + slug) || "[]")); } catch { setCart([]); }

    let stop: (() => void) | undefined;
    let dead = false;
    (async () => {
      let data: Any;
      try {
        data = await api(`/api/public/${slug}/menu?t=${q(TABLE)}&k=${q(KEY)}`);
      } catch (e: Any) {
        if (!dead) setError(e.message);
        return;
      }
      if (dead) return;
      setM(data);
      setBrand(data.restaurant.brand_color);
      setTipPct(data.restaurant.tip_pct);
      document.title = data.restaurant.name + " · " + (I18N[l] || I18N.es).menu;
      const meta = document.querySelector("meta[name=theme-color]");
      if (meta) meta.setAttribute("content", data.restaurant.brand_color);
      if (data.table_ok) {
        await refreshBill();
        stop = liveStream(`/api/public/${slug}/stream?table=${q(TABLE)}&k=${q(KEY)}`, { update: onLive });
      }
      if (justPaid) {
        history.replaceState(null, "", location.pathname + `?t=${TABLE}&k=${KEY}`);
        setDlg({ t: "thanks" });
      }
    })();
    return () => { dead = true; stop?.(); if (pollTimer.current) clearInterval(pollTimer.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug, TABLE, KEY]);

  const saveCart = (c: CartLine[]) => { setCart(c); ls("mesaya_cart_" + slug, JSON.stringify(c)); };

  async function onLive() {
    const before = new Map<number, string>((billRef.current.lines || []).map((l: Any) => [l.order_id, l.order_status]));
    let fresh: Any;
    try { fresh = await api(`/api/public/${slug}/bill?table=${q(TABLE)}&k=${q(KEY)}`); } catch { return; }
    setBill(fresh);
    const mineReady = fresh.lines.some((l: Any) => l.diner_id === dinerId.current && l.order_status === "ready" && before.get(l.order_id) !== "ready");
    if (mineReady) {
      toast("🍽️ " + T("ready"));
      if (navigator.vibrate) navigator.vibrate([120, 60, 120]);
    }
  }

  // al abrir la cuenta por primera vez, marca lo mío para pagar
  const unpaid: Any[] = bill.lines.filter((l: Any) => l.state === "unpaid");
  useEffect(() => {
    if (view === "bill" && !billInit.current && unpaid.length) {
      billInit.current = true;
      const mine = unpaid.filter((l) => l.diner_id === dinerId.current).map((l) => l.id);
      if (mine.length) setSel(new Set(mine));
    }
  }, [view, unpaid.length]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setSel((s) => {
      const n = new Set([...s].filter((id) => unpaid.some((l) => l.id === id)));
      return n.size === s.size ? s : n;
    });
  }, [bill]); // eslint-disable-line react-hooks/exhaustive-deps

  const cartTotal = cart.reduce((s, l) => s + l.unit * l.qty, 0);
  const cartCount = cart.reduce((s, l) => s + l.qty, 0);

  function findItem(id: number): Any {
    for (const c of M.categories) for (const i of c.items) if (i.id === id) return i;
  }

  function changeLang(l: string) { setLang(l); ls("mesaya_lang", l); }

  // ---- pagos
  const statusUrl = (id: number) => `/api/public/${slug}/pay/${id}?table=${q(TABLE)}&k=${q(KEY)}`;
  const payAction = (id: number, act: string) => api(`/api/public/${slug}/pay/${id}/${act}`, { method: "POST", body: { table: TABLE, key: KEY } });

  function pollPayment(id: number, onPaid: (s: Any) => void, onFail: (timeout?: boolean) => void) {
    if (pollTimer.current) clearInterval(pollTimer.current);
    const started = Date.now();
    pollTimer.current = setInterval(async () => {
      try {
        const s = await api(statusUrl(id));
        if (s.status === "paid") { clearInterval(pollTimer.current!); onPaid(s); }
        else if (s.status === "failed") { clearInterval(pollTimer.current!); onFail(); }
        else if (Date.now() - started > 6 * 60 * 1000) { clearInterval(pollTimer.current!); onFail(true); }
      } catch { /* reintenta */ }
    }, 3000);
  }

  async function closePay() { setDlg(null); await refreshBill(); }

  async function pay(provider: string) {
    const ids = [...sel].filter((id) => unpaid.some((l) => l.id === id));
    if (!ids.length) return;
    if (provider === "nequi") ls("mesaya_phone", phone);
    let invoice: Any = null;
    if (inv.doc_number?.trim() && inv.name?.trim() && M.restaurant.invoicing) {
      invoice = { doc_type: inv.doc_type, doc_number: inv.doc_number.trim(), name: inv.name.trim(), email: (inv.email || "").trim() };
      ls("mesaya_inv", JSON.stringify(invoice));
    }
    try {
      const res = await api(`/api/public/${slug}/pay`, { method: "POST", body: { table: TABLE, key: KEY, item_ids: ids, tip_pct: tipPct || 0, payer: dinerName, provider, phone: document.getElementById("nph") ? phone : "", invoice } });
      if (res.mode === "redirect") { location.href = res.url; return; }
      setSel(new Set());
      if (res.mode === "cashier") toast("🧾 " + T("askBill"));
      else if (res.mode === "push") {
        setDlg({ t: "nequi", res, phase: "wait" });
        pollPayment(res.payment_id, (s) => setDlg({ t: "thanks", paymentId: res.payment_id, invoice: s.invoice }), (timeout) => setDlg({ t: "nequi", res, phase: "fail", timeout }));
      } else if (res.mode === "breb") setDlg({ t: "breb", res, phase: "ask" });
      else setDlg({ t: "thanks", paymentId: res.payment_id });
    } catch (e: Any) { toast(e.message, true); }
    await refreshBill();
  }

  async function cancelPayment(res: Any) {
    if (pollTimer.current) clearInterval(pollTimer.current);
    try { await payAction(res.payment_id, "cancel"); } catch { /* ya no estaba */ }
    await closePay();
  }

  async function claimBreb(res: Any) {
    try { await payAction(res.payment_id, "claim"); } catch (e: Any) { toast(e.message, true); return; }
    setDlg({ t: "breb", res, phase: "check" });
    pollPayment(res.payment_id, (s) => setDlg({ t: "thanks", paymentId: res.payment_id, invoice: s.invoice }), () => setDlg({ t: "breb", res, phase: "fail" }));
  }

  async function sendCall(type: "bill" | "waiter") {
    try {
      await api(`/api/public/${slug}/call`, { method: "POST", body: { table: TABLE, key: KEY, type } });
      await refreshBill();
      toast(type === "bill" ? "🧾 " + T("billAsked") : "🙋 " + T("waiterCalled"));
    } catch (e: Any) { toast(e.message, true); }
  }

  async function sendFeedback() {
    try {
      const r = await api(`/api/public/${slug}/feedback`, { method: "POST", body: { table: TABLE, rating, comment } });
      setRated(true);
      if (r.review_url) setReviewUrl(r.review_url);
    } catch (e: Any) { toast(e.message, true); }
  }

  if (error) return <div className="menu-root"><div className="notice">{error}</div></div>;
  if (!M) return <div className="menu-root" />;

  const R = M.restaurant;

  function taxRow(subtotal: number) {
    if (!R.tax_pct || R.tax_label.startsWith("No ")) return null;
    const tax = R.tax_included ? subtotal - subtotal / (1 + R.tax_pct / 100) : (subtotal * R.tax_pct) / 100;
    return (
      <div className="row spread small muted">
        <span>{R.tax_label} {R.tax_pct}%{R.tax_included ? " · " + T("taxIncl") : ""}</span>
        <span>{money(Math.round(tax))}</span>
      </div>
    );
  }

  // ---------------------------------------------------------------- vistas
  const cats: Any[] = M.categories;
  const s = search.trim().toLowerCase();
  const shown = cats
    .filter((c) => activeCat === null || c.id === activeCat)
    .map((c) => ({ ...c, items: c.items.filter((i: Any) => !s || (i.name + " " + i.description).toLowerCase().includes(s)) }))
    .filter((c) => c.items.length);

  const menuView = (
    <>
      <div className="tools">
        <input id="q" type="search" placeholder={T("search")} value={search} onChange={(e) => setSearch(e.target.value)} />
        <div className="chips">
          {[{ id: null, name: T("all") }, ...cats].map((c) => (
            <button key={String(c.id)} className={"chip " + (activeCat === c.id ? "on" : "")} onClick={() => setActiveCat(c.id)}>{c.name}</button>
          ))}
        </div>
      </div>
      <main>
        {shown.map((c) => (
          <section className="cat" key={c.id}>
            <h2>{c.name}</h2>
            {c.items.map((i: Any) => (
              <article key={i.id} className={"card item " + (i.available ? "" : "off")} onClick={() => setDlg({ t: "item", id: i.id })}>
                <div className="thumb">{i.image ? <img loading="lazy" src={i.image} alt="" /> : initial(i.name)}</div>
                <div className="grow">
                  <h3>{i.featured && <span className="tag star">★</span>}{i.name}</h3>
                  <p>{i.description}</p>
                  <div>{i.tags.map((t: string) => <span key={t} className={"tag " + (t === "picante" ? "hot" : "")}>{t}</span>)}</div>
                  <div className="price">{i.available ? money(i.price) : <span className="pill bad">{T("soldout")}</span>}</div>
                </div>
                {i.available && M.can_order && <button className="add" aria-label={T("add")}>+</button>}
              </article>
            ))}
          </section>
        ))}
      </main>
    </>
  );

  const callButtons = (() => {
    const called = bill.calls.includes("waiter");
    return (
      <div className="row" style={{ margin: "1rem 0" }}>
        <button className="btn ghost grow" disabled={called} onClick={() => sendCall("waiter")}>🙋 {called ? T("waiterCalled") : T("callWaiter")}</button>
      </div>
    );
  })();

  const feedbackBox = rated ? (
    <div className="card" style={{ marginTop: ".8rem", textAlign: "center" }}>{T("rated")}</div>
  ) : (
    <div className="card" style={{ marginTop: ".8rem", textAlign: "center" }}>
      <h3>{T("rate")}</h3>
      <div className="stars">
        {[1, 2, 3, 4, 5].map((n) => <button key={n} className={rating >= n ? "on" : ""} onClick={() => setRating(n)}>★</button>)}
      </div>
      <input placeholder={T("comment")} maxLength={400} style={{ margin: ".6rem 0" }} value={comment} onChange={(e) => setComment(e.target.value)} />
      <button className="btn block" disabled={!rating} onClick={sendFeedback}>{T("sendRate")}</button>
    </div>
  );

  function simpleBill() {
    if (!unpaid.length)
      return (
        <>
          <div className="card" style={{ marginTop: ".8rem", textAlign: "center" }}><div style={{ fontSize: "2rem" }}>✅</div><b>{T("tableClosed")}</b></div>
          {feedbackBox}
        </>
      );
    const subtotal = unpaid.reduce((a, l) => a + l.line_total, 0);
    const tipS = Math.round((subtotal * (R.tip_pct || 0)) / 100);
    const total = subtotal + (R.tax_included ? 0 : Math.round((subtotal * R.tax_pct) / 100));
    const asked = bill.calls.includes("bill");
    return (
      <div className="card" style={{ marginTop: ".8rem" }}>
        {taxRow(subtotal)}
        <div className="row spread" style={{ margin: ".3rem 0" }}><span className="big">{T("totalConsumption")}</span><span className="big">{money(total)}</span></div>
        {R.tip_pct ? <div className="muted small">{T("tipSuggested")} ({R.tip_pct}%): {money(tipS)}</div> : null}
        <button className="btn block" style={{ marginTop: ".9rem" }} disabled={asked} onClick={() => sendCall("bill")}>{asked ? T("billAsked") : "🧾 " + T("finishTable")}</button>
      </div>
    );
  }

  function invoiceForm() {
    const open = inv.open !== undefined ? inv.open : !!(inv.doc_number && inv.name);
    return (
      <details style={{ marginTop: ".8rem" }} open={open} onToggle={(e) => setInv((i: Any) => ({ ...i, open: (e.target as HTMLDetailsElement).open }))}>
        <summary style={{ cursor: "pointer", fontWeight: 700 }}>🧾 {T("wantInvoice")}</summary>
        <p className="muted small" style={{ margin: ".4rem 0" }}>{T("invoiceHint")}</p>
        <div className="row">
          <select style={{ width: "42%" }} value={inv.doc_type} onChange={(e) => setInv({ ...inv, doc_type: e.target.value })}>
            {[["CC", "CC"], ["NIT", "NIT"], ["CE", "CE"], ["PP", "Pasaporte"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <input inputMode="numeric" placeholder={T("docNumber")} value={inv.doc_number} onChange={(e) => setInv({ ...inv, doc_number: e.target.value })} />
        </div>
        <input placeholder={T("fullName")} style={{ marginTop: ".4rem" }} value={inv.name} autoComplete="name" onChange={(e) => setInv({ ...inv, name: e.target.value })} />
        <input type="email" placeholder={T("emailInv")} style={{ marginTop: ".4rem" }} value={inv.email} autoComplete="email" onChange={(e) => setInv({ ...inv, email: e.target.value })} />
      </details>
    );
  }

  const payLabel = (p: Any) => (p.id === "cashier" ? T("askBill") : p.id === "nequi" ? T("payNequi") : p.id === "breb" ? T("payBreb") : T("payOnline") + (p.id === "mock" ? " · demo" : ""));

  function billView() {
    const L: Any[] = bill.lines;
    if (!L.length)
      return (
        <main>
          <div className="card" style={{ marginTop: "1rem", textAlign: "center" }}>
            <p className="muted">{T("empty")}</p>
            <button className="btn" onClick={() => setView("menu")}>{T("menu")}</button>
          </div>
          {callButtons}
        </main>
      );
    const orders = [...new Set(L.map((l) => l.order_id))].map((id) => L.find((l) => l.order_id === id));
    const active = orders.filter((o) => o.order_status !== "served" || L.some((l) => l.order_id === o.order_id && l.state !== "paid"));
    const list = (
      <>
        {reviewUrl && <a className="btn block" style={{ margin: ".6rem 0" }} href={reviewUrl} target="_blank" rel="noopener">⭐ {T("google")}</a>}
        {active.map((o) => {
          const idx = STATUS_IDX[o.order_status] ?? 0;
          return (
            <div className="card" style={{ marginTop: ".8rem" }} key={o.order_id}>
              <div className="row spread"><b>#{o.seq} {o.diner_name ? "· " + o.diner_name : ""}</b><span className={"pill " + (idx >= 2 ? "ok" : "warn")}>{T("status")[idx]}</span></div>
              <div className="steps">{[0, 1, 2, 3].map((i) => <i key={i} className={i <= idx ? "on" : ""} />)}</div>
            </div>
          );
        })}
        <h2 style={{ margin: "1.2rem 0 .3rem" }}>{T("myBill")}</h2>
        <div className="card">
          {L.map((l) => {
            const can = l.state === "unpaid";
            return (
              <div className={"line " + (l.state === "paid" ? "paid" : "")} key={l.id}>
                {can && M.features.payments ? (
                  <input type="checkbox" checked={sel.has(l.id)} onChange={(e) => setSel((p) => { const n = new Set(p); e.target.checked ? n.add(l.id) : n.delete(l.id); return n; })} />
                ) : <span style={{ width: 22 }} />}
                <div className="grow">
                  <b>{l.qty}× {l.name}</b>{" "}
                  {l.state === "paid" ? <span className="pill ok">{T("paid")}</span> : l.state === "reserved" ? <span className="pill warn">{T("reserved")}</span> : null}
                  <div className="muted small">{l.options_text} {l.diner_name ? "· " + l.diner_name : ""}{l.diner_id === dinerId.current ? " ✦" : ""}</div>
                </div>
                <b>{money(l.line_total)}</b>
              </div>
            );
          })}
        </div>
      </>
    );
    if (!M.features.payments) return <main>{list}{simpleBill()}{callButtons}</main>;
    if (!unpaid.length)
      return <main>{list}<div className="card" style={{ marginTop: ".8rem", textAlign: "center" }}>{T("nothingToPay")}</div>{feedbackBox}{callButtons}</main>;
    const chosen = unpaid.filter((l) => sel.has(l.id));
    const subtotal = chosen.reduce((a, l) => a + l.line_total, 0);
    const tip = Math.round((subtotal * (tipPct || 0)) / 100);
    return (
      <main>
        {list}
        <div className="card" style={{ marginTop: ".8rem" }}>
          <div className="row wrap" style={{ marginBottom: ".6rem" }}>
            <button className="btn sm soft" onClick={() => setSel(new Set(unpaid.filter((l) => l.diner_id === dinerId.current).map((l) => l.id)))}>{T("mine")}</button>
            <button className="btn sm soft" onClick={() => setSel(new Set(unpaid.map((l) => l.id)))}>{T("everything")}</button>
          </div>
          <label style={{ marginTop: 0 }}>{T("tip")}</label>
          <div className="tips">{[0, 5, 10, 15].map((p) => <button key={p} className={tipPct === p ? "on" : ""} onClick={() => setTipPct(p)}>{p}%</button>)}</div>
          <div className="row spread" style={{ marginTop: ".8rem" }}><span className="muted">{T("subtotal")}</span><b>{money(subtotal)}</b></div>
          {taxRow(subtotal)}
          <div className="row spread"><span className="muted">{T("tip")}</span><b>{money(tip)}</b></div>
          <div className="row spread" style={{ margin: ".4rem 0 .8rem" }}><span className="big">{T("total")}</span><span className="big">{money(subtotal + tip + (R.tax_included ? 0 : Math.round((subtotal * R.tax_pct) / 100)))}</span></div>
          {R.invoicing && invoiceForm()}
          {M.providers.some((p: Any) => p.id === "nequi") && (
            <>
              <label>{T("nequiPhone")}</label>
              <input id="nph" inputMode="tel" maxLength={14} placeholder="300 123 4567" value={phone} onChange={(e) => setPhone(e.target.value)} />
            </>
          )}
          {M.providers.map((p: Any) => (
            <button key={p.id} className={"btn block " + (p.id === "cashier" ? "ghost" : p.id === "nequi" ? "nequi" : "")} style={{ marginTop: ".5rem" }} disabled={!chosen.length} onClick={() => pay(p.id)}>{payLabel(p)}</button>
          ))}
        </div>
        {callButtons}
      </main>
    );
  }

  const unpaidMine = unpaid.length;

  return (
    <div className="menu-root">
      <div className="hero">
        <div className="thumb logo">{R.logo ? <img src={R.logo} alt="" /> : initial(R.name)}</div>
        <div className="grow"><h1>{R.name}</h1><div className="muted small">{R.tagline || ""}</div></div>
        {M.table_ok && <div className="tablebadge">{T("table")} {M.table}</div>}
        <div className="langs">
          {["es", "en"].map((l) => (
            <button key={l} onClick={() => changeLang(l)} style={l === lang ? { background: "var(--ink)", color: "var(--bg)" } : undefined}>{l.toUpperCase()}</button>
          ))}
        </div>
      </div>
      {!M.subscription_ok ? <div className="notice">{T("menuOnly")}</div>
        : M.paused ? <div className="notice">{T("paused")}</div>
        : !M.table_ok ? <div className="notice">{TABLE ? T("badQr") : T("scan")}</div> : null}

      {view === "menu" ? menuView : billView()}

      {M.table_ok && (
        <div className="bar">
          <button className={"btn " + (view === "menu" ? "dark" : "ghost")} onClick={() => setView("menu")}>{T("menu")}</button>
          {cartCount && M.can_order ? (
            <button className="btn" onClick={() => setDlg({ t: "cart" })}>{T("viewOrder")} · {cartCount} · {money(cartTotal)}</button>
          ) : (
            <button className={"btn " + (view === "bill" ? "dark" : "ghost")} onClick={async () => { await refreshBill(); setView("bill"); window.scrollTo(0, 0); }}>
              {T("myBill")}{unpaidMine ? ` · ${unpaidMine}` : ""}
            </button>
          )}
        </div>
      )}

      <Modal open={!!dlg} onClose={() => { if (dlg?.t === "nequi" || dlg?.t === "breb") { if (pollTimer.current) clearInterval(pollTimer.current); } setDlg(null); refreshBill(); }}>
        {dlg?.t === "item" && (
          <ItemDialog it={findItem(dlg.id)} money={money} T={T} canOrder={M.can_order} onClose={() => setDlg(null)} toast={toast}
            onAdd={(line) => { saveCart([...cart, line]); setDlg(null); }} />
        )}
        {dlg?.t === "cart" && (
          <CartDialog cart={cart} T={T} money={money} table={M.table} dinerName={dinerName} onClose={() => setDlg(null)}
            onChange={saveCart}
            onSend={async (name, note) => {
              setDinerName(name); ls("mesaya_name", name);
              try {
                await api(`/api/public/${slug}/orders`, { method: "POST", body: { table: TABLE, key: KEY, diner_id: dinerId.current, diner_name: name, note, items: cart.map((l) => ({ item_id: l.item_id, qty: l.qty, options: l.options, note: l.note })) } });
                saveCart([]); setDlg(null); await refreshBill(); setView("bill"); toast("✅ " + T("sent") + " " + T("sentSub"));
                return true;
              } catch (e: Any) { toast(e.message, true); return false; }
            }} />
        )}
        {dlg?.t === "nequi" && (dlg.phase === "wait" ? (
          <div style={{ textAlign: "center", padding: ".6rem 0" }}>
            <div style={{ fontSize: "2.6rem" }}>📲</div><h2>{T("openNequi")}</h2>
            <p className="muted">{T("nequiWait")}</p><div className="big">{money(dlg.res.total)}</div>
            <p className="small muted">{T("waiting")}</p>
            <button className="btn ghost" onClick={() => cancelPayment(dlg.res)}>{T("cancel")}</button>
          </div>
        ) : (
          <div style={{ textAlign: "center", padding: "1rem 0" }}>
            <div style={{ fontSize: "2.6rem" }}>⚠️</div><h2>{dlg.timeout ? T("payTimeout") : T("payDeclined")}</h2>
            <button className="btn" onClick={closePay}>OK</button>
          </div>
        ))}
        {dlg?.t === "breb" && (dlg.phase === "ask" ? (
          <div style={{ textAlign: "center" }}>
            <h2>Bre-B</h2><p className="muted">{T("brebIntro")}</p>
            <div className="card" style={{ background: "var(--bg)" }}>
              <div className="muted small">{T("brebKey")} ({dlg.res.breb.type})</div>
              <div className="big">{dlg.res.breb.key}</div>
              {dlg.res.breb.holder && <div className="muted small">{dlg.res.breb.holder}</div>}
              <button className="btn sm soft" style={{ marginTop: ".4rem" }} onClick={() => { navigator.clipboard?.writeText(dlg.res.breb.key); toast("✓"); }}>{T("copyKey")}</button>
            </div>
            <p style={{ margin: ".8rem 0 .2rem" }}>{T("exactAmount")}</p><div className="big">{money(dlg.res.total)}</div>
            <p className="muted small">{T("brebRef")}: <b>{dlg.res.reference}</b> · {T("mesaLbl")} {M.table}</p>
            <button className="btn block" onClick={() => claimBreb(dlg.res)}>{T("iPaid")}</button>
            <button className="btn ghost block" style={{ marginTop: ".4rem" }} onClick={() => cancelPayment(dlg.res)}>{T("cancel")}</button>
          </div>
        ) : dlg.phase === "check" ? (
          <div style={{ textAlign: "center", padding: "1rem 0" }}><div style={{ fontSize: "2.6rem" }}>⏳</div><h2>{T("brebCheck")}</h2><p className="muted">{T("brebCheckSub")}</p></div>
        ) : (
          <div style={{ textAlign: "center", padding: "1rem 0" }}><div style={{ fontSize: "2.6rem" }}>⚠️</div><h2>{T("brebNo")}</h2><button className="btn" onClick={closePay}>OK</button></div>
        ))}
        {dlg?.t === "thanks" && <ThanksDialog T={T} invoicing={!!R.invoicing} paymentId={dlg.paymentId} first={dlg.invoice} statusUrl={statusUrl} onClose={closePay} />}
      </Modal>

      <div id="toast" className={"toast" + (toastMsg ? " show" : "") + (toastMsg?.err ? " err" : "")}>{toastMsg?.text}</div>
      <Powered />
    </div>
  );
}

// ------------------------------------------------------------------ piezas
function Modal({ open, onClose, children }: { open: boolean; onClose: () => void; children: React.ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog ref={ref} onClose={onClose}>
      <div className="dlg">{open ? children : null}</div>
    </dialog>
  );
}

function ItemDialog({ it, money, T, canOrder, onClose, onAdd, toast }: { it: Any; money: (v: number) => string; T: (k: string) => Any; canOrder: boolean; onClose: () => void; onAdd: (l: CartLine) => void; toast: (t: string, e?: boolean) => void }) {
  const [qty, setQty] = useState(1);
  const [note, setNote] = useState("");
  const [chosen, setChosen] = useState<Record<string, string[]>>(() => {
    const c: Record<string, string[]> = {};
    it.options.forEach((g: Any) => { c[g.name] = g.required && !g.multi ? [g.options[0].name] : []; });
    return c;
  });
  let extra = 0;
  it.options.forEach((g: Any) => (chosen[g.name] || []).forEach((n) => { extra += (g.options.find((o: Any) => o.name === n) || { price: 0 }).price; }));
  const unit = it.price + extra;

  const toggle = (g: Any, o: string, on: boolean) =>
    setChosen((c) => ({ ...c, [g.name]: g.multi ? (on ? [...c[g.name], o] : c[g.name].filter((x) => x !== o)) : [o] }));

  function add() {
    for (const g of it.options) if (g.required && !(chosen[g.name] || []).length) { toast(`${T("choose")}: ${g.name}`, true); return; }
    const options: { group: string; name: string }[] = [];
    it.options.forEach((g: Any) => (chosen[g.name] || []).forEach((n) => options.push({ group: g.name, name: n })));
    onAdd({ item_id: it.id, name: it.name, qty, unit, options, note: note.trim() });
  }

  return (
    <>
      <div className="sheet-h"><h2 style={{ margin: 0 }}>{it.name}</h2><button className="x" onClick={onClose}>×</button></div>
      {it.image && <div className="thumb" style={{ height: 200, borderRadius: 14, marginBottom: ".6rem" }}><img src={it.image} alt="" /></div>}
      <p className="muted" style={{ marginTop: 0 }}>{it.description}</p>
      {it.allergens.length > 0 && <p className="small muted">⚠️ {T("allergens")}: {it.allergens.join(", ")}</p>}
      {it.options.map((g: Any) => (
        <div key={g.name}>
          <h3 style={{ margin: "1rem 0 .2rem", fontSize: "1rem" }}>{g.name} {g.required && <span className="pill brand">{T("required")}</span>}</h3>
          {g.options.map((o: Any) => (
            <label className="opt" style={{ margin: 0, fontSize: "1rem", color: "var(--ink)" }} key={o.name}>
              <input type={g.multi ? "checkbox" : "radio"} name={"g_" + g.name} checked={(chosen[g.name] || []).includes(o.name)} onChange={(e) => toggle(g, o.name, e.target.checked)} />
              <span className="grow">{o.name}</span><span className="muted">{o.price ? "+" + money(o.price) : ""}</span>
            </label>
          ))}
        </div>
      ))}
      {canOrder && (
        <>
          <label>{T("notes")}</label>
          <input maxLength={140} value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="row spread" style={{ margin: "1rem 0 .4rem" }}>
            <div className="qty"><button onClick={() => setQty(Math.max(1, qty - 1))}>−</button><b>{qty}</b><button onClick={() => setQty(Math.min(20, qty + 1))}>+</button></div>
            <button className="btn grow" onClick={add}>{T("addToOrder")} · {money(unit * qty)}</button>
          </div>
        </>
      )}
    </>
  );
}

function CartDialog({ cart, T, money, table, dinerName, onClose, onChange, onSend }: { cart: CartLine[]; T: (k: string) => Any; money: (v: number) => string; table: string; dinerName: string; onClose: () => void; onChange: (c: CartLine[]) => void; onSend: (name: string, note: string) => Promise<boolean> }) {
  const [name, setName] = useState(dinerName);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!cart.length) onClose(); }, [cart.length]); // eslint-disable-line react-hooks/exhaustive-deps
  const total = cart.reduce((s, l) => s + l.unit * l.qty, 0);
  const step = (i: number, d: number) => onChange(cart.map((l, j) => (j === i ? { ...l, qty: Math.min(Math.max(1, l.qty + d), 20) } : l)));
  return (
    <>
      <div className="sheet-h"><h2 style={{ margin: 0 }}>{T("viewOrder")} · {T("table")} {table}</h2><button className="x" onClick={onClose}>×</button></div>
      {cart.map((l, i) => (
        <div className="line" key={i}>
          <div className="grow"><b>{l.name}</b><div className="muted small">{l.options.map((o) => o.name).join(", ")}{l.note ? ` · “${l.note}”` : ""}</div></div>
          <div className="qty">
            {l.qty > 1 ? <button aria-label={T("less")} onClick={() => step(i, -1)}>−</button> : <span className="qgap"></span>}
            <b>{l.qty}</b>
            <button aria-label={T("more")} onClick={() => step(i, 1)}>+</button>
          </div>
          <b style={{ minWidth: 76, textAlign: "right" }}>{money(l.unit * l.qty)}</b>
          <button className="rm" aria-label={T("remove")} title={T("remove")} onClick={() => onChange(cart.filter((_, j) => j !== i))}>×</button>
        </div>
      ))}
      <label>{T("yourName")}</label>
      <input maxLength={40} value={name} autoComplete="given-name" onChange={(e) => setName(e.target.value)} />
      <label>{T("notes")}</label>
      <input maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} />
      <div className="row spread" style={{ margin: "1rem 0" }}><span className="big">{T("total")}</span><span className="big">{money(total)}</span></div>
      <p className="muted small" style={{ margin: ".6rem 0 0", textAlign: "center" }}>{T("privacyNote")} <a href="/privacidad" target="_blank" rel="noopener">{T("privacyLink")}</a></p>
      <button className="btn block" style={{ marginTop: ".6rem" }} disabled={busy} onClick={async () => { setBusy(true); const ok = await onSend(name.trim(), note); if (!ok) setBusy(false); }}>{T("send")}</button>
    </>
  );
}

function ThanksDialog({ T, invoicing, paymentId, first, statusUrl, onClose }: { T: (k: string) => Any; invoicing: boolean; paymentId?: number; first?: Any; statusUrl: (id: number) => string; onClose: () => void }) {
  const [inv, setInv] = useState<Any>(first);
  useEffect(() => {
    if (!paymentId || !invoicing) return;
    let dead = false;
    (async () => {  // la factura se emite en segundo plano: consultar unos segundos
      for (let i = 0; i < 8 && !dead; i++) {
        await new Promise((r) => setTimeout(r, 2500));
        try {
          const s = await api(statusUrl(paymentId));
          if (s.invoice && ["issued", "error"].includes(s.invoice.status)) { if (!dead) setInv(s.invoice.status === "issued" ? s.invoice : { status: "pending" }); break; }
        } catch { /* ok */ }
      }
    })();
    return () => { dead = true; };
  }, [paymentId, invoicing]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div style={{ textAlign: "center", padding: "1rem 0" }}>
      <div style={{ fontSize: "3rem" }}>✅</div><h2>{T("thanks")}</h2>
      {inv && inv.status === "issued" ? (
        <>
          <p>🧾 {T("invoiceNo")} <b>{inv.number}</b></p>
          {inv.public_url && <a className="btn sm soft" target="_blank" rel="noopener" href={inv.public_url}>{T("viewInvoice")}</a>}
        </>
      ) : inv ? <p className="muted small">{T("invoiceSoon")}</p> : null}
      <p><button className="btn" onClick={onClose}>OK</button></p>
    </div>
  );
}
