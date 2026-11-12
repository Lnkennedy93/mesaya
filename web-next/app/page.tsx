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
  ["🤖", "Asistente de IA para tu negocio", "Pregunta por ventas, mesas, carta u opiniones y responde con tus propios datos. En Pro y Cadena, o como complemento del plan Esencial."],
  ["📸", "Carta con foto de cada plato", "Fotos optimizadas, etiquetas (vegano, picante…) y alérgenos visibles."],
  ["⚡", "Importar con IA en minutos", "Foto, PDF o texto pegado → carta lista para revisar."],
  ["🍳", "Pantalla de cocina en vivo", "Nuevo → preparando → listo. Sonido, colores por demora y número de mesa."],
  ["🚫", "Apaga lo agotado", "Un toque y desaparece al instante de todos los celulares. Cocina también puede hacerlo."],
  ["🧩", "Opciones y adicionales", "Término, tamaño, salsas, extras con recargo. El precio lo calcula el servidor."],
  ["🙋", "Llamar al mesero / pedir cuenta", "Aviso en la pantalla de sala sin que el cliente tenga que gritar."],
  ["🔒", "QR seguro por mesa", "Cada mesa tiene su código secreto: si se filtra, lo renuevas con un toque."],
  ["⭐", "Opiniones → reseñas en Google", "Pedimos calificación al terminar la mesa; los de 4–5 ★ se envían a tu perfil de Google."],
  ["📊", "Reportes que sí sirven", "Ventas, ticket promedio, horas pico, platos estrella, tiempo de cocina y CSV."],
  ["🌎", "Carta en español e inglés", "Ideal para zonas turísticas. El cliente cambia el idioma con un toque."],
  ["⏸️", "Modo «solo carta»", "En hora pico o sin cocina, pausas pedidos y el QR sigue mostrando la carta."],
];

const ASK_TOPICS = [
  ["📊", "Resumen", "Ventas, ticket promedio, horas pico, mesas que más venden y propinas."],
  ["🍽️", "Carta", "Cuántos platos tienes, el más barato y el más caro, y cuáles están apagados."],
  ["🔳", "Mesas y QR", "Cuáles están libres u ocupadas, la cuenta de cada una y los llamados al mesero."],
  ["⭐", "Opiniones", "Promedio de estrellas, cuántas de cada nota y los últimos comentarios."],
  ["⚙️", "Ajustes", "Tu plan, la propina, los impuestos y si estás recibiendo pedidos por QR."],
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
  ["¿Necesito tarjeta para probar?", "No. Son 14 días completos sin tarjeta; al terminar eliges un plan o sigues gratis con 3 mesas."],
  ["¿Cobran comisión por cada venta?", "No. Pagas una mensualidad fija. No cobramos nada por cada pedido."],
  ["¿Cómo se cobra la cuenta?", "Como siempre, en caja. El cliente toca «Terminar mesa» en su celular, tu equipo recibe el aviso, cobra y cierra la mesa en la pantalla de sala."],
  ["¿Qué puede responder el asistente de IA?", "Preguntas sobre tu propio negocio: ventas, platos más y menos vendidos, tiempos de cocina, clientes por mesa, mesas libres, carta y precios, opiniones y ajustes. Si le pides apagar un plato, lo propone y tú lo confirmas con un botón."],
  ["¿Qué pasa con mis datos cuando le pregunto algo?", "El asistente consulta solo los datos de tu restaurante y los procesa con Gemini, de Google, para redactar la respuesta. Nunca muestra tus claves ni el PIN del equipo, y no cambia nada sin tu confirmación."],
  ["¿Funciona con mi caja o sistema de facturación?", "MesaYa no reemplaza tu caja: registra los pedidos y exporta CSV. Las integraciones con POS están en preparación (plan Cadena)."],
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
            <span className="pill brand">Para restaurantes, cafés y bares</span>{" "}
            <a className="pill ok" href="#asistente" style={{ textDecoration: "none" }}>✨ Nuevo: Asistente de IA</a>
            <h1 style={{ marginTop: ".6rem" }}>
              Tu QR ya no solo muestra la carta: <em>tus clientes piden desde la mesa y la cocina lo recibe al instante</em>
            </h1>
            <p className="lead">
              Sin descargar ninguna app. El pedido llega a cocina con el número de mesa, apagas lo agotado con un toque y el cliente termina su mesa y pide la cuenta desde el celular. Vendes 100 % tuyo, sin comisiones por pedido.
            </p>
            <div className="cta">
              <a className="btn" href="/signup">Crear mi carta gratis · 14 días</a>
            </div>
            <div className="muted small">Sin tarjeta de crédito · Lista en 5 minutos · Cancela cuando quieras · <a href="/catalogo-mesaya.pdf" download>Descargar catálogo (PDF)</a></div>
          </div>
          <div className="stage">
            <div className="card dash" aria-label="Ejemplo del panel del restaurante">
              <div className="top"><b>Resumen de hoy</b><div className="seg" aria-hidden="true"><span className="on">Hoy</span><span>7 días</span><span>30 días</span></div></div>
              <div className="kp">
                <div><div className="l">Ventas</div><div className="v">$1.860.000</div><div className="spark" aria-hidden="true">{[40, 62, 35, 70, 55, 88, 64].map((h, i) => <i key={i} className={i === 6 ? "" : "m"} style={{ height: h + "%" }}></i>)}</div></div>
                <div><div className="l">Pedidos</div><div className="v">42</div><div className="spark" aria-hidden="true">{[30, 45, 60, 38, 72, 50, 80].map((h, i) => <i key={i} className={i === 6 ? "" : "m"} style={{ height: h + "%" }}></i>)}</div></div>
                <div><div className="l">Ticket promedio</div><div className="v">$44.300</div><div className="spark" aria-hidden="true">{[55, 50, 66, 48, 60, 58, 70].map((h, i) => <i key={i} className={i === 6 ? "" : "m"} style={{ height: h + "%" }}></i>)}</div></div>
              </div>
              <div className="dash2">
                <div className="gz">
                  <svg viewBox="0 0 120 72" role="img" aria-label="7 de 10 mesas activas">
                    <path d="M10 62 A50 50 0 0 1 110 62" fill="none" stroke="currentColor" strokeOpacity=".14" strokeWidth="11" strokeLinecap="round" />
                    <path d="M10 62 A50 50 0 0 1 110 62" fill="none" stroke="#3ddc61" strokeWidth="11" strokeLinecap="round" strokeDasharray="110 157" />
                    <text x="60" y="56" textAnchor="middle" fontSize="22" fontWeight="800" fill="currentColor">70%</text>
                  </svg>
                  <div className="l">Mesas activas · 7 de 10</div>
                </div>
                <div className="tbl">
                  <div className="tt">Pedidos en curso</div>
                  <div className="r"><b>Mesa 4</b><span className="muted">Preparando</span><div className="meter"><i style={{ width: "60%" }}></i></div></div>
                  <div className="r"><b>Mesa 7</b><span className="muted">Nuevo</span><div className="meter"><i style={{ width: "12%" }}></i></div></div>
                  <div className="r"><b>Para llevar</b><span><span className="dot"></span> Listo</span><div className="meter g"><i style={{ width: "100%" }}></i></div></div>
                </div>
              </div>
              <div className="note">Vista de ejemplo con datos ilustrativos.</div>
            </div>
            <div className="phone" aria-hidden="true">
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

        <section id="asistente">
          <h2 className="t">Pregúntale a tu negocio</h2>
          <p className="sub">El Asistente de IA responde con los datos reales de tu restaurante, en lenguaje normal. Incluido en Pro y Cadena; en Esencial se activa por $12.000 al mes (120 preguntas).</p>
          <div className="ask">
            <div className="feat" style={{ gridTemplateColumns: "1fr" }}>
              {ASK_TOPICS.map(([ico, h, p]) => (
                <div className="card" key={h}><div className="ico">{ico}</div><h3>{h}</h3><p className="muted">{p}</p></div>
              ))}
            </div>
            <div className="card chat" aria-label="Ejemplo de conversación con el asistente">
              <span className="pill brand">Ejemplo</span>
              <div className="bub me">¿Cuánto vendí esta semana y cuál fue el plato más pedido?</div>
              <div className="bub ai">Esta semana vendiste $3.912.000 en 50 pedidos. El plato más pedido fue la Limonada de coco, con 24 unidades.</div>
              <div className="bub me">¿Qué mesas tengo libres ahora?</div>
              <div className="bub ai">Están libres las mesas 2, 5 y 7. La mesa 3 tiene una cuenta por cobrar de $68.000.</div>
              <div className="bub me">Apaga la sopa wantán, se acabó.</div>
              <div className="bub ai">Listo para apagar «Sopa wantán». Confírmalo con el botón.</div>
              <div className="go">Apagar «Sopa wantán»</div>
            </div>
          </div>
          <p className="muted small" style={{ textAlign: "center", marginTop: "1rem" }}>Nunca muestra tus claves ni el PIN del equipo, y no cambia nada sin tu confirmación.</p>
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
          <p className="sub">14 días gratis sin tarjeta. Si no pagas, te quedas gratis con 3 mesas. Sin permanencia. Sin letra pequeña.</p>
          <div className="plans">
            <div className="card plan">
              <h3>Esencial</h3>
              <div className="p">$75.000<small className="muted"> /mes</small></div>
              <ul><li>Mesas 1 a 7 incluidas</li><li>Mesa adicional: $5.000 al mes</li><li>Carta con fotos y QR por mesa</li><li>Pantalla de cocina</li><li>Cuenta y cierre de mesa desde el celular</li><li>Reportes básicos</li><li>Opcional: <b>Asistente de IA</b>, 120 preguntas al mes por $12.000</li></ul>
              <a className="btn ghost block" href="/signup">Empezar gratis</a>
            </div>
            <div className="card plan hot">
              <span className="pill brand" style={{ alignSelf: "flex-start" }}>Más elegido</span>
              <h3>Pro</h3>
              <div className="p">$139.000<small className="muted"> /mes</small></div>
              <ul><li>Mesas 1 a 13 incluidas</li><li>Mesa adicional: $5.000 al mes</li><li>Importación de carta con IA</li><li><b>Asistente de IA</b>: 300 preguntas al mes</li><li>Opiniones y reseñas en Google</li><li>Reportes completos + CSV</li><li>Soporte prioritario</li></ul>
              <a className="btn block" href="/signup">Empezar gratis</a>
            </div>
            <div className="card plan">
              <h3>Cadena</h3>
              <div className="p">A tu medida</div>
              <ul><li><b>Asistente de IA</b>: 1.500 preguntas al mes</li><li>Hasta 500 mesas</li><li>Onboarding con tu equipo</li><li>Próximamente: varias sedes, marca propia y dominio, integraciones (POS, facturación)</li></ul>
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
