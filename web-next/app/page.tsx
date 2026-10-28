import Link from "next/link";
import Powered from "@/components/Powered";
import "./landing.css";

const STEPS = [
  ["Sube tu carta", "Pega el texto o sube una foto/PDF y la IA arma tu carta. Agrega la foto de cada plato."],
  ["Pega el QR en la mesa", "Imprime los QR listos, uno por mesa y con código secreto propio."],
  ["El cliente pide", "Escanea, elige, personaliza y envía. Sin app, sin registro."],
  ["Llega a cocina", "Pantalla en vivo con el número de mesa, alertas y cronómetro por pedido."],
  ["Termina la mesa", "Pide la cuenta desde el celular; tu equipo cobra en caja y cierra la mesa."],
];

const FEATURES = [
  ["📸", "Carta con foto de cada plato", "Fotos optimizadas, etiquetas (vegano, picante…) y alérgenos visibles."],
  ["⚡", "Importar con IA en minutos", "Foto, PDF o texto pegado → carta lista para revisar."],
  ["🍳", "Pantalla de cocina en vivo", "Nuevo → preparando → listo. Sonido, colores por demora y número de mesa."],
  ["🚫", "Apaga lo agotado", "Un toque y desaparece al instante de todos los celulares. Cocina también puede hacerlo."],
  ["🧩", "Opciones y adicionales", "Término, tamaño, salsas, extras con recargo. El precio lo calcula el servidor."],
  ["🙋", "Llamar al mesero / pedir cuenta", "Aviso en la pantalla de sala sin que el cliente tenga que gritar."],
  ["🔒", "QR seguro por mesa", "Código secreto renovable: nadie manda pedidos falsos desde su casa."],
  ["⭐", "Opiniones → reseñas en Google", "Pedimos calificación al terminar la mesa; los de 4–5 ★ se envían a tu perfil de Google."],
  ["📊", "Reportes que sí sirven", "Ventas, ticket promedio, horas pico, platos estrella, tiempo de cocina y CSV."],
  ["🌎", "Carta en español e inglés", "Ideal para zonas turísticas. El cliente cambia el idioma con un toque."],
  ["⏸️", "Modo «solo carta»", "En hora pico o sin cocina, pausas pedidos y el QR sigue mostrando la carta."],
];

const COMPARE = [
  ["El cliente puede pedir", "✗ Espera al mesero", "✓ Desde su celular"],
  ["Pedido llega a cocina con mesa", "✗", "✓ En vivo"],
  ["Plato agotado", "✗ Se entera al pedir", "✓ Se apaga en 1 toque"],
  ["Pedir la cuenta / terminar mesa", "✗ Hay que llamar al mesero", "✓ Desde el celular"],
  ["Fotos y alérgenos", "✗ Texto plano", "✓"],
  ["Comisión por pedido", "—", "0 %"],
];

const FAQ = [
  ["¿Mis clientes tienen que descargar algo?", "No. Escanean el QR y se abre la carta en el navegador del celular."],
  ["¿Necesito tarjeta para probar?", "No. Son 14 días completos sin tarjeta; al terminar eliges un plan o tu QR queda solo como carta."],
  ["¿Cobran comisión por cada venta?", "No. Pagas una mensualidad fija. No cobramos nada por cada pedido."],
  ["¿Cómo se cobra la cuenta?", "Como siempre, en caja. El cliente toca «Terminar mesa» en su celular, tu equipo recibe el aviso, cobra y cierra la mesa en la pantalla de sala."],
  ["¿Funciona con mi caja o sistema de facturación?", "MesaYa no reemplaza tu caja: registra los pedidos y exporta CSV. Las integraciones con POS están en el plan Cadena."],
];

// Las páginas que aún no están en Next.js las sirve el backend actual (ver next.config.mjs), por eso estos enlaces son <a>.
export default function Landing() {
  return (
    <div className="landing">
      <div className="w">
        <header>
          <a className="logo" href="/">
            Mesa<b>Ya</b>
          </a>
          <span className="grow"></span>
          <a href="/login" className="btn ghost sm">Entrar</a>
          <a href="/signup" className="btn sm">Prueba gratis</a>
        </header>

        <div className="hero">
          <div>
            <span className="pill brand">Para restaurantes, cafés y bares</span>
            <h1 style={{ marginTop: ".6rem" }}>
              Tu QR ya no solo muestra la carta: <em>tus clientes piden desde la mesa y la cocina lo recibe al instante</em>
            </h1>
            <p className="lead">
              Sin descargar ninguna app. El pedido llega a cocina con el número de mesa, apagas lo agotado con un toque y el cliente termina su mesa y pide la cuenta desde el celular. Vendes 100 % tuyo, sin comisiones por pedido.
            </p>
            <div className="cta">
              <a className="btn" href="/signup">Crear mi carta gratis · 14 días</a>
              <Link className="btn ghost" href="/r/dragon-dorado?t=1&k=demo1">Ver demo en vivo</Link>
            </div>
            <div className="muted small">Sin tarjeta de crédito · Lista en 5 minutos · Cancela cuando quieras</div>
          </div>
          <div className="phone">
            <div className="screen">
              <div className="top">
                <b style={{ fontSize: "1.1rem" }}>Dragón Dorado</b>
                <div style={{ opacity: 0.85 }}>Mesa 5 · Cocina china de barrio</div>
              </div>
              <div className="it"><div className="th"></div><div className="grow"><b>Arroz especial</b><div className="muted">Cerdo, pollo, camarón y huevo</div></div><b>$24.000</b></div>
              <div className="it"><div className="th"></div><div className="grow"><b>Lumpias</b><div className="muted">6 rollitos crujientes</div></div><b>$16.000</b></div>
              <div className="it"><div className="th"></div><div className="grow"><b>Chop suey</b><div className="muted">Pollo y verduras al wok</div></div><b>$28.000</b></div>
              <div className="it"><div className="th" style={{ opacity: 0.4 }}></div><div className="grow" style={{ opacity: 0.5 }}><b>Sopa wantán</b></div><span className="pill bad">Agotado</span></div>
              <div className="go">Ver pedido · 3 · $68.000</div>
            </div>
          </div>
        </div>

        <section id="como">
          <h2 className="t">Del QR a la cocina en 5 pasos</h2>
          <p className="sub">Así funciona para tu restaurante y para tu cliente.</p>
          <div className="steps">
            {STEPS.map(([h, p]) => (
              <div className="card" key={h}><h3>{h}</h3><p className="muted">{p}</p></div>
            ))}
          </div>
        </section>

        <section>
          <h2 className="t">Todo lo que necesitas para vender más rápido</h2>
          <p className="sub">Lo esencial de un menú QR, más lo que normalmente solo ofrecen los sistemas caros.</p>
          <div className="feat">
            {FEATURES.map(([ico, h, p]) => (
              <div className="card" key={h}><div className="ico">{ico}</div><h3>{h}</h3><p className="muted">{p}</p></div>
            ))}
          </div>
        </section>

        <section>
          <h2 className="t">El QR de siempre vs. MesaYa</h2>
          <p className="sub">&nbsp;</p>
          <table className="cmp">
            <tbody>
              <tr><th></th><th>QR que solo muestra PDF</th><th>MesaYa</th></tr>
              {COMPARE.map(([a, b, c]) => (
                <tr key={a}><td>{a}</td><td>{b}</td><td>{c}</td></tr>
              ))}
            </tbody>
          </table>
        </section>

        <section id="precios">
          <h2 className="t">Precios simples</h2>
          <p className="sub">14 días gratis sin tarjeta. Sin permanencia. Sin letra pequeña.</p>
          <div className="plans">
            <div className="card plan">
              <h3>Esencial</h3>
              <div className="p">$59.000<small className="muted"> /mes</small></div>
              <ul><li>Hasta 15 mesas</li><li>Carta con fotos y QR por mesa</li><li>Pantalla de cocina</li><li>Cuenta y cierre de mesa desde el celular</li><li>Reportes básicos</li></ul>
              <a className="btn ghost block" href="/signup">Empezar gratis</a>
            </div>
            <div className="card plan hot">
              <span className="pill brand" style={{ alignSelf: "flex-start" }}>Más elegido</span>
              <h3>Pro</h3>
              <div className="p">$119.000<small className="muted"> /mes</small></div>
              <ul><li>Hasta 60 mesas</li><li>Importación de carta con IA</li><li>Opiniones y reseñas en Google</li><li>Reportes completos + CSV</li><li>Soporte prioritario</li></ul>
              <a className="btn block" href="/signup">Empezar gratis</a>
            </div>
            <div className="card plan">
              <h3>Cadena</h3>
              <div className="p">A tu medida</div>
              <ul><li>Varias sedes</li><li>Marca propia y dominio</li><li>Integraciones (POS, facturación)</li><li>Onboarding con tu equipo</li></ul>
              <a className="btn ghost block" href="mailto:ventas@mesaya.app">Hablar con ventas</a>
            </div>
          </div>
        </section>

        <section>
          <h2 className="t">Preguntas frecuentes</h2>
          <p className="sub">&nbsp;</p>
          <div style={{ maxWidth: 720, margin: "auto" }}>
            {FAQ.map(([q, a]) => (
              <details key={q}><summary>{q}</summary><p className="muted">{a}</p></details>
            ))}
          </div>
        </section>

        <section>
          <div className="band">
            <h2 style={{ fontSize: "1.8rem" }}>Tu cocina recibiendo pedidos hoy mismo</h2>
            <p style={{ opacity: 0.8 }}>Crea tu carta, imprime los QR y listo.</p>
            <a className="btn" href="/signup">Crear mi carta gratis</a>
          </div>
        </section>

        <footer>
          © MesaYa · Hecho para restaurantes · <a href="/terminos">Términos</a> · <a href="/privacidad">Política de datos</a> · <a href="/kitchen">Entrada del equipo</a>
          <Powered style={{ padding: ".8rem 0 0" }} />
        </footer>
      </div>
    </div>
  );
}
