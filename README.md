# Bitácora — panel de suscripciones de YouTube sin algoritmo

Página estática que agrupa tus suscripciones de YouTube por categoría y muestra
los videos más recientes en orden cronológico, sin ninguna recomendación
algorítmica de por medio. Se actualiza sola cada 4 horas mediante GitHub Actions.

## Cómo funciona

1. `data/suscripciones_categorizadas.csv` contiene tus 1852 canales con su categoría.
2. `scripts/build_feed.py` descarga el feed RSS público de cada canal
   (`youtube.com/feeds/videos.xml?channel_id=...`), sin usar la API de YouTube
   ni consumir ninguna cuota.
3. El script agrupa los videos por categoría y renderiza `docs/index.html`
   usando la plantilla en `templates/index.html.j2`.
4. GitHub Actions ejecuta este proceso automáticamente cada 4 horas y publica
   el resultado con GitHub Pages.

## Puesta en marcha (una sola vez)

1. **Crea un repositorio nuevo en GitHub** (puede ser público — así Actions
   corre gratis sin límite de minutos) y sube todo el contenido de esta carpeta.

2. **Activa GitHub Pages**:
   - Ve a Settings → Pages en tu repositorio.
   - En "Source", selecciona la rama `main` y la carpeta `/docs`.
   - Guarda. GitHub te dará una URL tipo `https://tuusuario.github.io/turepositorio/`.

3. **Verifica que Actions tenga permiso de escritura**:
   - Ve a Settings → Actions → General → Workflow permissions.
   - Selecciona "Read and write permissions".

4. **Lanza la primera ejecución manualmente** (no esperes las 4 horas):
   - Ve a la pestaña "Actions" en GitHub.
   - Selecciona el workflow "Actualizar bitácora de suscripciones".
   - Haz clic en "Run workflow".

5. Cuando termine (puede tardar varios minutos por la cantidad de canales),
   abre la URL de GitHub Pages. Ahí está tu bitácora.

## Actualizar la categorización más adelante

Si vuelves a categorizar canales o cambias tu lista de suscripciones, solo
reemplaza `data/suscripciones_categorizadas.csv` con la versión nueva y súbelo
al repositorio — la siguiente ejecución programada (o una manual) recogerá los
cambios automáticamente.

## Ajustar la frecuencia de actualización

En `.github/workflows/update.yml`, la línea `cron: "0 */4 * * *"` controla
cada cuánto corre. Por ejemplo, cambiarla a `"0 */6 * * *"` la haría correr
cada 6 horas en vez de 4.

## Ajustar cuántos videos se muestran por canal

En `scripts/build_feed.py`, la constante `VIDEOS_PER_CHANNEL` (por defecto 6)
controla cuántos videos recientes se conservan por canal antes de agruparlos
y ordenarlos cronológicamente entre todos.

## Notas

- Algunos canales pueden no tener feed disponible (cuentas suspendidas,
  configuraciones especiales) — el script los omite sin fallar y lo reporta
  en el log de la ejecución de Actions.
- Todo el proceso es gratuito: GitHub Actions no tiene límite de minutos en
  repositorios públicos, GitHub Pages es gratis, y los feeds RSS de YouTube
  son públicos y no requieren API key.
