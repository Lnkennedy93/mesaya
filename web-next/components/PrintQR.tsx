"use client";
// Hoja imprimible con el QR de cada mesa (portada de web/print.html).
import { useEffect, useState } from "react";
import { api, setBrand } from "@/lib/api";

export default function PrintQR() {
  const [data, setData] = useState<{ me: any; tables: any[] } | null>(null);
  useEffect(() => {
    (async () => {
      try {
        const me = await api("/api/me");
        setBrand(me.restaurant.brand_color);
        const { tables } = await api("/api/tables");
        setData({ me, tables });
      } catch {
        location.href = "/login";
      }
    })();
  }, []);
  return (
    <div className="print-root">
      <div className="bar">
        <b className="grow">QR de mesas — imprime en papel adhesivo o acrílico</b>
        <button className="btn" onClick={() => window.print()}>Imprimir</button>
      </div>
      <div className="sheet">
        {data?.tables.map((t) => (
          <div className="tent" key={t.id}>
            <div className="name">{data.me.restaurant.name}</div>
            <div className="num">Mesa {t.label}</div>
            <img src={`/api/qr/${t.id}.svg`} alt={`QR mesa ${t.label}`} />
            <div className="how"><b>Escanea, pide y paga</b> desde tu celular.<br />Sin descargar nada.</div>
            <div className="foot">{String(data.me.public_url).replace(/^https?:\/\//, "")}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
