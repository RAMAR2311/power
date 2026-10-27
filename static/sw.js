const CACHE_NAME = 'powerled-pwa-v2';

const PRECACHE_ASSETS = [
    '/',
    '/offline',
    '/manifest.json',
    '/static/manifest.json',
    '/static/favicon.ico',
    '/static/css/custom.css',
    '/static/img/favicon-pw.png',
    '/static/img/logo-power-led-dark.png',
    '/static/img/logo-power-led.png',
    '/static/img/power-led-square.png',
    '/static/img/pw-isotipo.png',
    '/static/img/icons/apple-touch-icon.png',
    '/static/img/icons/favicon-16x16.png',
    '/static/img/icons/favicon-32x32.png',
    '/static/img/icons/favicon-48x48.png',
    '/static/img/icons/favicon-64x64.png',
    '/static/img/icons/icon-72x72.png',
    '/static/img/icons/icon-96x96.png',
    '/static/img/icons/icon-128x128.png',
    '/static/img/icons/icon-144x144.png',
    '/static/img/icons/icon-152x152.png',
    '/static/img/icons/icon-180x180.png',
    '/static/img/icons/icon-192x192.png',
    '/static/img/icons/icon-256x256.png',
    '/static/img/icons/icon-384x384.png',
    '/static/img/icons/icon-512x512.png',
    '/static/img/icons/icon-maskable-192x192.png',
    '/static/img/icons/icon-maskable-512x512.png',
    'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Orbitron:wght@600;700;800;900&family=Rajdhani:wght@600;700&family=Roboto:wght@400;500;700&display=swap',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css'
];

// Instalación: Precarga de recursos clave de la marca POWER LED
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                return cache.addAll(PRECACHE_ASSETS).catch((err) => {
                    console.warn('[SW POWER LED] Aviso: Algunos recursos precacheados fallaron (continuando):', err);
                });
            })
            .then(() => self.skipWaiting())
    );
});

// Activación: Limpieza automática de cachés antiguos
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cache) => {
                    if (cache !== CACHE_NAME) {
                        console.log('[SW POWER LED] Eliminando caché antiguo:', cache);
                        return caches.delete(cache);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

// Permite forzar actualización inmediata del SW desde el cliente
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});

// Estrategia de Fetch híbrida (Network-First para páginas operativas ERP/POS y Stale-While-Revalidate para estáticos)
self.addEventListener('fetch', (event) => {
    // 1. Ignorar solicitudes que no sean GET (POST de ventas, ingresos de mercancía, arqueos, etc.)
    if (event.request.method !== 'GET') {
        return;
    }

    const url = new URL(event.request.url);

    // 2. Rutas dinámicas y APIs en tiempo real que NO deben servirse desde caché
    if (
        url.pathname.startsWith('/auth/') ||
        url.pathname.includes('logout') ||
        url.pathname.startsWith('/api/') ||
        url.pathname.includes('/api/')
    ) {
        event.respondWith(fetch(event.request));
        return;
    }

    // 3. Navegación de vistas HTML (Inventario, Ingresos, POS, Vehículos, Taller, Bodega): Network First con Fallback a Caché y Offline
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request)
                .then((networkResponse) => {
                    if (networkResponse && networkResponse.status === 200) {
                        const responseClone = networkResponse.clone();
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(event.request, responseClone);
                        });
                    }
                    return networkResponse;
                })
                .catch(async () => {
                    const cachedResponse = await caches.match(event.request);
                    if (cachedResponse) {
                        return cachedResponse;
                    }
                    const offlinePage = await caches.match('/offline');
                    if (offlinePage) {
                        return offlinePage;
                    }
                    return new Response('POWER LED: Sin conexión a internet', {
                        status: 503,
                        statusText: 'Service Unavailable',
                        headers: new Headers({ 'Content-Type': 'text/plain; charset=utf-8' })
                    });
                })
        );
        return;
    }

    // 4. Recursos Estáticos (Iconos PWA, Logos, Fuentes, CSS, JS): Stale While Revalidate
    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            const fetchPromise = fetch(event.request)
                .then((networkResponse) => {
                    if (networkResponse && networkResponse.status === 200) {
                        const responseClone = networkResponse.clone();
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(event.request, responseClone);
                        });
                    }
                    return networkResponse;
                })
                .catch(() => {});

            return cachedResponse || fetchPromise;
        })
    );
});
