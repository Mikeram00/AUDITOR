// Service worker mínimo del AUDITOR.
// Existe para que el teléfono pueda instalar la página como aplicación.
// No guarda nada en caché: cada pantalla y cada consulta van siempre al servidor,
// así nunca se ve una versión vieja de la central ni un stock atrasado.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
