import type { PoliticaDatos } from "@/lib/types"

function fechaLarga(iso: string): string {
  // Mediodía para que la zona horaria no corra la fecha un día.
  return new Date(`${iso}T12:00:00`).toLocaleDateString("es-CO", {
    day: "numeric",
    month: "long",
    year: "numeric",
  })
}

function Seccion({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-base font-bold text-foreground">{titulo}</h2>
      <div className="space-y-2 text-sm leading-relaxed text-muted-foreground">{children}</div>
    </section>
  )
}

export function PoliticaTexto({ datos }: { datos: PoliticaDatos }) {
  const correo = (
    <a href={`mailto:${datos.correo}`} className="font-medium text-foreground underline">
      {datos.correo}
    </a>
  )

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Versión {datos.version}, vigente desde el {fechaLarga(datos.vigente_desde)}. Esta política
        cumple con la Ley 1581 de 2012 y el Decreto 1377 de 2013, que regulan la protección de datos
        personales en Colombia.
      </p>

      <Seccion titulo="1. Responsable del tratamiento">
        <p>
          {datos.responsable}, con domicilio en {datos.domicilio}. Correo de contacto: {correo}
          {datos.telefono ? <>. Teléfono: {datos.telefono}</> : null}. FinSmart se desarrolló como
          trabajo de grado en la Universidad de San Buenaventura Cali.
        </p>
      </Seccion>

      <Seccion titulo="2. Datos que se recolectan">
        <ul className="list-disc space-y-1 pl-5">
          <li>Datos de la cuenta: nombre, correo electrónico y contraseña, que se guarda cifrada con bcrypt y nunca en texto plano.</li>
          <li>La información financiera que registras: ingresos, gastos, categorías, presupuestos, metas de ahorro y abonos.</li>
          <li>Los gastos compartidos: grupos, gastos y el nombre y correo de los integrantes que agregas.</li>
          <li>Los servicios que registras: proveedor, número de contrato y, si el portal del proveedor los exige, los datos del pagador (tipo y número de identificación, teléfono y correo).</li>
          <li>El resultado de las consultas de facturas: valor, fecha de vencimiento y referencia de pago.</li>
        </ul>
        <p>
          FinSmart no te pide datos sensibles. Si decides registrar un gasto que revele información
          sensible, por ejemplo de salud, lo haces de forma voluntaria.
        </p>
      </Seccion>

      <Seccion titulo="3. Para qué se usan">
        <ul className="list-disc space-y-1 pl-5">
          <li>Prestarte el servicio: guardar y mostrar tu información financiera, y calcular presupuestos, metas y deudas de grupo.</li>
          <li>Entrenar con tu historial los modelos de aprendizaje automático que te sugieren categorías, detectan gastos inusuales y encuentran pagos recurrentes. Cada modelo se entrena solo con tus datos y no se comparte con otros usuarios.</li>
          <li>Consultar la factura de un servicio en el portal del proveedor cuando tú lo pides. Para eso se envían al portal el número de contrato y los datos del pagador que exija.</li>
          <li>Enviarte correos relacionados con tu cuenta: invitaciones a grupos, solicitudes de pago y alertas de presupuesto.</li>
          <li>Fines académicos: usar resultados agregados o seudonimizados en el trabajo de grado del que hace parte FinSmart, sin publicar tu nombre, tu correo ni tus movimientos individuales.</li>
        </ul>
      </Seccion>

      <Seccion titulo="4. Tus derechos">
        <p>Como titular de los datos puedes, en cualquier momento y de forma gratuita:</p>
        <ul className="list-disc space-y-1 pl-5">
          <li>Conocer, actualizar y rectificar tus datos.</li>
          <li>Pedir prueba de la autorización que otorgaste.</li>
          <li>Saber cómo se han usado tus datos.</li>
          <li>Revocar la autorización y pedir que se borren tus datos.</li>
          <li>Presentar quejas ante la Superintendencia de Industria y Comercio.</li>
        </ul>
      </Seccion>

      <Seccion titulo="5. Cómo ejercerlos">
        <p>
          Desde la plataforma puedes consultar y editar tus datos, y en Configuración puedes eliminar
          tu cuenta, lo que borra todos tus registros y los modelos entrenados con ellos. También
          puedes escribir a {correo}. Las consultas se responden en un máximo de diez días hábiles y
          los reclamos en un máximo de quince días hábiles, como lo establecen los artículos 14 y 15
          de la Ley 1581 de 2012.
        </p>
      </Seccion>

      <Seccion titulo="6. Seguridad">
        <p>
          Las contraseñas se guardan con bcrypt, la base de datos se cifra en reposo, cada usuario
          solo puede ver sus propios datos y el inicio de sesión se bloquea temporalmente tras varios
          intentos fallidos.
        </p>
      </Seccion>

      <Seccion titulo="7. Con quién se comparten">
        <p>
          FinSmart no vende ni cede tus datos. Solo comparte lo indispensable con el portal del
          proveedor cuando consultas una factura y con el servicio de correo que envía las
          notificaciones.
        </p>
      </Seccion>

      <Seccion titulo="8. Conservación">
        <p>Tus datos se conservan mientras tu cuenta exista. Al eliminarla, se borran.</p>
      </Seccion>

      <Seccion titulo="9. Autorización y cambios">
        <p>
          Al crear tu cuenta y marcar la casilla de aceptación autorizas el tratamiento descrito
          aquí; la plataforma guarda la versión que aceptaste y la fecha. Si esta política cambia,
          se te pedirá aceptar la nueva versión antes de seguir usando FinSmart.
        </p>
      </Seccion>
    </div>
  )
}
