"use client";
import { useEffect, useRef } from "react";

/** <dialog> nativo. El contenido solo existe mientras está abierto (cada apertura empieza limpia).
 *  locked: no se puede cerrar con Esc (p. ej. aceptar términos). */
export default function Modal({ open, onClose, locked, children }: { open: boolean; onClose: () => void; locked?: boolean; children: React.ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog ref={ref} onClose={onClose} onCancel={(e) => locked && e.preventDefault()}>
      <div className="dlg">{open ? children : null}</div>
    </dialog>
  );
}
