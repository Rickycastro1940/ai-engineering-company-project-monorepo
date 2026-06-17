# Brasaland - Contexto de empresa

## Resumen ejecutivo

Brasaland es una cadena de restaurantes de cocina a la brasa fundada en 2008 en Medellin, Colombia.
En 15 anos evoluciono de un local familiar a 14 restaurantes propios en dos paises: Colombia y Estados Unidos (Florida).

- Empleados: ~115
- Facturacion anual aproximada: USD 6M
- Mercados: Colombia + Florida
- Monedas operativas clave: COP + USD

La marca se construyo sobre tres promesas:

1. Sabor consistente en cualquier local.
2. Servicio calido y consistente.
3. Operacion de cocina rapida.

El reto actual es escalar esas promesas con sistemas modernos sin perder la identidad de la marca.

## Liderazgo y organizacion

- CEO: Mariana Restrepo (desde 2019)
- CTO: Nicolas Park (Medellin)

Areas principales:

- Operaciones de Restaurante - Felipe Guerrero
- Compras y Proveedores - Lucia Fernandez
- Marketing y Experiencia Digital - Camila Ospina
- Personas y Cultura - Ashley Turner (Miami)
- Formacion y Estandares de Calidad - Jake Morrison (Miami)
- Tecnologia - Nicolas Park
- Direccion Ejecutiva - Mariana Restrepo

## Estado actual del negocio

Brasaland es rentable y tiene base de clientes fiel en ambos mercados, pero opera con herramientas fragmentadas:

- Pedidos de materia prima por WhatsApp o telefono.
- Programa de fidelizacion fisico (tarjetas de sellos) sin datos explotables.
- Reportes por Excel/PDF y baja visibilidad en tiempo real.
- POS distintos por pais sin integracion.
- App desactualizada y web estatica.
- No hay API central ni plataforma de datos consolidada.

Existe una iniciativa interna, Brasaland Digital, para construir sistemas, automatizaciones y productos digitales de nueva generacion.

## Problemas por departamento y necesidades

### 1) Operaciones de restaurante

**Dolores actuales**

- Los 14 locales operan aislados entre si.
- No hay visibilidad en tiempo real de ventas y actividad por local.
- Pedidos manuales generan exceso de stock en algunos locales y roturas en otros.
- Reportes de turno en papel/Excel.

**Que necesitan**

- Dashboard de ventas en tiempo real por local (COP y USD).
- Sistema inteligente de pedidos basado en historico de ventas + stock actual.
- Alertas automaticas cuando un local no registra ventas en horario de apertura.

### 2) Compras y proveedores

**Dolores actuales**

- ~20 proveedores entre Colombia y Florida.
- Negociacion de precios por email y Excel.
- Cambios de precio detectados tarde (al recibir factura).
- Sin vision consolidada de compras de cadena.

**Que necesitan**

- Plataforma de gestion de proveedores con historial de precios y alertas.
- Consolidado de compras para negociacion centralizada en ambos mercados.

### 3) Marketing y experiencia digital

**Dolores actuales**

- Web de 2019 sin pedidos online.
- App con mala percepcion (2.8 en app store).
- Brasa Points fisico, baja adopcion y sin trazabilidad digital.
- Casi nulo conocimiento real del cliente.

**Que necesitan**

- App digital para fidelizacion y pedidos.
- CRM con historial de pedidos y preferencias.
- Motor de personalizacion de productos segun comportamiento.

### 4) Personas y cultura

**Dolores actuales**

- Gestion de 115 personas en 2 marcos laborales distintos.
- Procesos de RRHH manuales por email y Excel.
- Onboarding de cocina con alta rotacion y alta carga operativa.

**Que necesitan**

- Portal interno RRHH (vacaciones, ausencias, solicitudes).
- Flujo automatizado de onboarding.
- Dashboard de KPIs de RRHH (rotacion, absentismo, tiempo de cobertura) por pais.

### 5) Formacion y estandares de calidad

**Dolores actuales**

- Materiales en Google Drive dificil de navegar.
- Cambios de recetas/procedimientos tardan dias en distribuirse.
- Riesgo de inconsistencias entre locales y paises.

**Que necesitan**

- Plataforma de formacion con catalogo de recetas con busqueda.
- Itinerario de incorporacion estructurado para nuevo personal.
- Sistema de distribucion simultanea de actualizaciones a los 14 locales.
- Soporte multiidioma recomendado (espanol/ingles), iniciando por idioma base.

### 6) Tecnologia

**Dolores actuales**

- Stack minimo y fragmentado.
- Sin API interna ni modelo de datos unificado.
- Sin telemetria consolidada.

**Que necesitan**

- API central de Brasaland para locales, menus, ventas, clientes y proveedores.
- Telemetria en tiempo real desde cada local.
- Pipeline de datos para dashboards de operaciones, marketing y finanzas.

### 7) Direccion ejecutiva

**Dolores actuales**

- Toma de decisiones basada en llamadas, reportes PDF y experiencia personal.
- No puede responder preguntas clave en tiempo real.

**Que necesitan**

- Dashboard ejecutivo con ventas consolidadas en USD y COP.
- Asistente de IA para consultas en lenguaje natural.
- Informe semanal automatizado cada lunes a las 07:00.

## Objetivo del proyecto AI Engineering

Construir progresivamente una plataforma digital integrada para Brasaland, alineada a los hitos del programa:

- Interfaces y experiencias digitales para clientes y equipos internos.
- Backend y API central con entidades core del negocio.
- Captura de telemetria y datos transaccionales en tiempo real.
- Automatizaciones y workflows operativos.
- Capacidades de IA (prediccion, personalizacion, asistentes, agentes).

## Restricciones y condiciones de diseno

- Operacion multipais: Colombia y Estados Unidos (Florida).
- Multimoneda: COP y USD.
- Potencial soporte bilingue: espanol e ingles.
- Integraciones con POS heterogeneos por pais.
- Mantener consistencia de marca y operacion entre locales.

## Modelo de proveedores

El directorio de proveedores de Brasaland usa estos campos exactos para el modelo `Supplier`:

| Campo | Tipo | Reglas |
| --- | --- | --- |
| `name` | string | Nombre del proveedor. Requerido y no vacio. |
| `country` | string | Pais operativo del proveedor. Requerido y no vacio. Los datos iniciales usan `Colombia` y `United States`. |
| `product_categories` | list[string] | Una o mas categorias validas de producto. |
| `rate` | number | Tarifa actual del proveedor. Debe ser mayor que `0`. |
| `last_rate_update_date` | date | Fecha de la ultima actualizacion de tarifa en formato `YYYY-MM-DD`. |
| `status` | string | Estado operativo del proveedor. Debe ser uno de los estados permitidos. |
| `id` | integer | Generado por TinyDB al insertar. No lo envia el cliente. |
| `updated_at` | datetime | Generado por el sistema al crear o modificar. No lo envia el cliente. |

### Categorias validas de proveedores

Los valores permitidos para `product_categories` son exactamente:

- `proteins`
- `produce`
- `pantry`
- `beverages`
- `packaging`
- `cleaning`

### Estados permitidos de proveedores

Los valores permitidos para `status` son exactamente:

- `active`
- `suspended`

### Proveedores iniciales del seeder

El seeder debe cargar estos 20 proveedores iniciales. La combinacion `name` + `country` identifica duplicados para evitar insertar el mismo proveedor mas de una vez.

| name | country | product_categories | rate | last_rate_update_date | status |
| --- | --- | --- | ---: | --- | --- |
| Carnes Antioquia | Colombia | `proteins` | 4.65 | 2026-05-20 | active |
| Avicola Las Palmas | Colombia | `proteins` | 3.90 | 2026-05-18 | active |
| Pescados del Caribe | Colombia | `proteins` | 5.20 | 2026-04-30 | suspended |
| Verduras Oriente | Colombia | `produce` | 1.45 | 2026-06-01 | active |
| Frutas Medellin | Colombia | `produce` | 1.30 | 2026-05-29 | active |
| Granos Andinos | Colombia | `pantry` | 2.10 | 2026-05-10 | active |
| Salsas La Brasa | Colombia | `pantry` | 1.90 | 2026-05-24 | active |
| Bebidas Tropicales | Colombia | `beverages` | 1.75 | 2026-05-21 | active |
| Empaques EcoBogota | Colombia | `packaging` | 0.28 | 2026-06-02 | active |
| Limpieza Profesional | Colombia | `cleaning` | 0.55 | 2026-05-17 | active |
| Florida Prime Meats | United States | `proteins` | 5.80 | 2026-05-22 | active |
| Sunshine Poultry | United States | `proteins` | 4.40 | 2026-05-26 | active |
| Gulf Seafood Supply | United States | `proteins` | 6.30 | 2026-04-28 | suspended |
| Miami Fresh Produce | United States | `produce` | 1.85 | 2026-06-03 | active |
| Orlando Citrus Farms | United States | `produce` | 1.60 | 2026-05-31 | active |
| Latin Pantry Imports | United States | `pantry` | 2.75 | 2026-05-13 | active |
| Brasa Sauce Co. | United States | `pantry` | 2.20 | 2026-05-27 | active |
| Florida Beverage Partners | United States | `beverages` | 1.95 | 2026-05-19 | active |
| Gulf Coast Packaging | United States | `packaging` | 0.32 | 2026-06-04 | active |
| Clean Kitchen Supply | United States | `cleaning` | 0.70 | 2026-05-15 | active |

## Oportunidades de IA prioritarias

- Prediccion de demanda de ingredientes por local y franja horaria.
- Recomendacion/personalizacion de menu por perfil de cliente.
- Deteccion temprana de anomalias operativas (ej. local abierto sin ventas).
- Asistentes internos para direccion y soporte operativo.
- Agentes de soporte y formacion para equipos distribuidos.

## Preguntas de negocio que el sistema debe responder

- Cuanto vendimos esta semana en Florida vs Colombia?
- Que local tiene el ticket promedio mas alto del mes?
- Donde hay riesgo de rotura de stock esta semana?
- Que segmentos de clientes tienen mayor recurrencia?
- Que proveedores estan incrementando precios por categoria?

## KPI iniciales sugeridos

- Ventas diarias/semanales por local, pais y moneda.
- Ticket promedio y margen estimado por local.
- Quiebres y sobrestock por categoria de insumo.
- Tiempo medio de cobertura de vacantes.
- Rotacion y absentismo por pais/local.
- Frecuencia de compra y retencion de clientes (cohortes).
- Tiempo de despliegue de cambios de recetas y nivel de adopcion.

## Alcance recomendado para primeras iteraciones

1. Modelo de datos comun para locales, ventas, menus, inventario y clientes.
2. API base con endpoints de lectura/escritura para operacion diaria.
3. Ingestion inicial de ventas y stock desde fuentes disponibles.
4. Dashboard operativo minimo con alertas criticas.
5. Base para CRM y fidelizacion digital (MVP).

## Criterio de exito

Brasaland debe poder pasar de decisiones por intuicion/reportes tardios a decisiones asistidas por datos en tiempo cercano al real, con capacidad de escalar operaciones en dos paises sin perder consistencia de producto ni experiencia de cliente.
