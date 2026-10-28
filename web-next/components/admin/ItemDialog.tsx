"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { Any, useAdmin } from "./ctx";

const TAGS = ["vegano", "vegetariano", "picante", "sin gluten", "popular"];
const ALLERGENS = ["gluten", "lácteos", "huevo", "maní", "frutos secos", "soya", "mariscos", "pescado"];

export default function ItemDialog({ item, catId, menu, onClose, onChanged }: { item: Any | null; catId?: number; menu: Any[]; onClose: () => void; onChanged: () => void }) {
  const { ME, toMajor, toMinor, toast } = useAdmin();
  const isNew = !item;
  const it: Any = item || { name: "", description: "", price: 0, featured: false, tags: [], allergens: [], options: [], category_id: catId, image: "" };

  const optsText0 = it.options
    .map((g: Any) => `${g.name}${g.required ? "*" : ""}${g.multi ? "+" : ""}\n${g.options.map((o: Any) => `- ${o.name}${o.price ? " | " + toMajor(o.price) : ""}`).join("\n")}`)
    .join("\n\n");

  const [name, setName] = useState<string>(it.name);
  const [desc, setDesc] = useState<string>(it.description);
  const [price, setPrice] = useState<string>(String(toMajor(it.price)));
  const [cat, setCat] = useState<number>(it.category_id);
  const [tags, setTags] = useState<string[]>(it.tags);
  const [allergens, setAllergens] = useState<string[]>(it.allergens);
  const [featured, setFeatured] = useState<boolean>(!!it.featured);
  const [optsText, setOptsText] = useState(optsText0);
  const [image, setImage] = useState<string>(it.image || "");
  const [id, setId] = useState<number | undefined>(it.id);

  const toggle = (list: string[], set: (v: string[]) => void, v: string) => set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  async function upload(file: File | undefined) {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await api(`/api/items/${id}/image`, { method: "POST", body: fd });
      setImage(r.image);
      toast("Foto actualizada");
      onChanged();
    } catch (e: Any) { toast(e.message, true); }
  }

  async function save() {
    const body = { category_id: cat, name, description: desc, price: toMinor(price), featured, tags, allergens, options: parseOpts(optsText, toMinor) };
    try {
      if (isNew) { const r = await api("/api/items", { method: "POST", body }); setId(r.id); } else await api("/api/items/" + id, { method: "PUT", body });
      toast("Plato guardado");
      onClose();
      onChanged();
    } catch (e: Any) { toast(e.message, true); }
  }

  async function remove() {
    if (!confirm("¿Eliminar este plato?")) return;
    try { await api("/api/items/" + id, { method: "DELETE" }); onClose(); onChanged(); } catch (e: Any) { toast(e.message, true); }
  }

  return (
    <>
      <div className="row spread"><h2 style={{ margin: 0 }}>{isNew ? "Nuevo plato" : "Editar plato"}</h2><button className="btn sm ghost" onClick={onClose}>✕</button></div>
      <label>Nombre</label>
      <input value={name} maxLength={90} onChange={(e) => setName(e.target.value)} />
      <label>Descripción</label>
      <textarea style={{ minHeight: 70, fontFamily: "inherit" }} maxLength={400} value={desc} onChange={(e) => setDesc(e.target.value)} />
      <div className="grid2">
        <div><label>Precio ({ME.restaurant.currency})</label><input type="number" min={0} step={ME.restaurant.decimals ? "0.01" : "1"} value={price} onChange={(e) => setPrice(e.target.value)} /></div>
        <div><label>Categoría</label><select value={cat} onChange={(e) => setCat(+e.target.value)}>{menu.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
      </div>
      <label>Etiquetas</label>
      <div className="tgl">{TAGS.map((t) => <label key={t}><input type="checkbox" checked={tags.includes(t)} onChange={() => toggle(tags, setTags, t)} />{t}</label>)}</div>
      <label>Alérgenos</label>
      <div className="tgl">{ALLERGENS.map((t) => <label key={t}><input type="checkbox" checked={allergens.includes(t)} onChange={() => toggle(allergens, setAllergens, t)} />{t}</label>)}</div>
      <label className="chk"><input type="checkbox" checked={featured} onChange={(e) => setFeatured(e.target.checked)} /> Destacar con ★</label>
      <label>Opciones y adicionales <span className="small">(grupo en una línea · * obligatorio · + varias · luego «- opción | recargo»)</span></label>
      <textarea placeholder={"Término*\n- Medio\n- Bien cocido\n\nAdicionales+\n- Queso extra | 3000"} value={optsText} onChange={(e) => setOptsText(e.target.value)} />
      {isNew || id === undefined ? (
        <p className="muted small">Guarda el plato primero para poder subirle una foto.</p>
      ) : (
        <>
          <label>Foto del plato</label>
          <div className="row">
            <div className="thumb" style={{ width: 70, height: 70, borderRadius: 12 }}>{image ? <img src={image} alt="" /> : <span>📷</span>}</div>
            <input type="file" accept="image/*" onChange={(e) => upload(e.target.files?.[0])} />
          </div>
        </>
      )}
      <div className="row spread" style={{ marginTop: "1.2rem" }}>
        {isNew ? <span></span> : <button className="btn bad sm" onClick={remove}>Eliminar</button>}
        <button className="btn" onClick={save}>Guardar</button>
      </div>
    </>
  );
}

/** «Grupo*+» en una línea y «- opción | recargo» debajo → [{name, required, multi, options:[{name, price}]}] */
function parseOpts(text: string, toMinor: (v: Any) => number) {
  const groups: Any[] = [];
  let g: Any = null;
  text.split("\n").forEach((raw) => {
    const l = raw.trim();
    if (!l) return;
    if (l.startsWith("-")) {
      if (!g) return;
      const [name, price] = l.slice(1).split("|").map((s) => s.trim());
      g.options.push({ name, price: toMinor(price) });
    } else {
      g = { name: l.replace(/[*+]+$/, "").trim(), required: /\*/.test(l.slice(-2)), multi: /\+/.test(l.slice(-2)), options: [] };
      groups.push(g);
    }
  });
  return groups.filter((x) => x.options.length);
}
