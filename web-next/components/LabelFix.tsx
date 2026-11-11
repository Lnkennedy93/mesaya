"use client";
// Los <label> del panel y de la carta van junto a su campo pero sin «for»: un lector de pantalla anuncia un campo sin nombre y tocar la
// etiqueta no enfoca el campo. Esto las enlaza (label + campo hermano) cada vez que cambia la página, sin tocar cada formulario.
import { useEffect } from "react";

let n = 0;

function link() {
  document.querySelectorAll("label:not([for])").forEach((l) => {
    if (l.querySelector("input,select,textarea")) return; // ya envuelve su campo
    const c = l.nextElementSibling;
    if (c && /^(INPUT|SELECT|TEXTAREA)$/.test(c.tagName)) {
      if (!c.id) c.id = "campo-" + ++n;
      l.setAttribute("for", c.id);
    }
  });
}

export default function LabelFix() {
  useEffect(() => {
    let raf = 0;
    const run = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(link); };
    run();
    const mo = new MutationObserver(run); // solo cambios de estructura: poner «for» e «id» no vuelve a dispararlo
    mo.observe(document.body, { childList: true, subtree: true });
    return () => { mo.disconnect(); cancelAnimationFrame(raf); };
  }, []);
  return null;
}
