# Flow FavManager

**Creador del proyecto:** RubénSDFA1labernt

**Colaboradores:** Enrigerano, hulena89, Silensama_Dev, JaviTech07, Andr...ma (Por ahora anónimo)

Para ver los créditos completos y contribuciones, visitar el repositorio de GitHub:
[https://github.com/fullstackcurso/](https://github.com/fullstackcurso/)
<br>
<br>
<br>

El desarrollo de este addon nace de la necesidad de mejorar la gestión y ordenación de los favoritos en Kodi, una tarea que a menudo resulta limitada en la interfaz nativa. Como fase previa al desarrollo, se analizaron las soluciones existentes en el ecosistema, identificando el addon "Insert-Swap-Kodi-Favourites" de doko-desuka (github.com/doko-desuka/plugin.program.orderfavourites). Este proyecto previo ha servido como inspiración para ver como se implementaban ciertas funcionalidades. Agradecimiento especial: doko-desuka, por el trabajo pionero en Insert-Swap-Kodi-Favourites.

Aclarar que, aunque ambos proyectos comparten un propósito similar y mecánicas básicas, no existe código compartido. Flow FavManager se ha construido desde cero con una arquitectura técnica propia, motivada, entre otros, por dos factores clave:
1. **Licenciamiento Open Source**: Al no constar una licencia de código abierto en el proyecto de referencia, se optó por una implementación independiente para garantizar que este nuevo proyecto pudiera ser libre y abierto.
2. **Escalabilidad Funcional**: Se requería una base técnica distinta para soportar todas las funcionalidades avanzadas (perfiles, seguridad, plantillas, etc.) que Flow FavManager ofrece.

Por tanto, las similitudes que se describen a continuación se refieren estrictamente a decisiones de diseño y experiencia de usuario, habiéndose implementado la lógica subyacente de forma diferente.

<br>

#### Similitudes entre Flow FavManager y Insert-Swap-Kodi-Favourites (2018 - junio de 2024)
**Fecha:** 12 Enero 2026

<br>

#### 1. Experiencia de Reordenamiento

*   **Acción de "Intercambiar" (Swap):** En ambos addons, el usuario puede seleccionar un favorito, luego seleccionar otro, y ver cómo intercambian sus posiciones. Aunque esta solución se había contemplado desde el inicio del proyecto, el addon anterior sirvió de referencia para su aplicación en Kodi.


#### 2. Opciones de Configuración Similares
Ambos addons presentan un menú de ajustes con opciones equivalentes para adaptar la visualización.

*   **Tamaño de Texto e iconos:** El usuario puede elegir entre ver los nombres de los favoritos en tamaño pequeño (por defecto) o más grande/legible y si prefiere ver miniaturas pequeñas para aprovechar el espacio o grandes para mayor claridad visual.
*   **Elección del Método:** El usuario debe elegir en la configuración si prefiere el comportamiento de "Intercambio" o de "Inserción" por defecto al hacer clic (la opción de mover con las flechas se ha añadido en Flow FavManager).

#### 3. Entorno Visual
*   **Ventana Emergente:** La forma de implementar la venta emergente y sus elementos para cambiar la posición de los favoritos.

<br>

**Nota de Reconocimiento:** Las decisiones de diseño descritas en los dos puntos anteriores están directamente inspiradas en el addon Insert-Swap-Kodi-Favourites de doko-desuka. Su trabajo previo sirvió como guía invaluable para definir estos aspectos de la experiencia de usuario. Gracias por allanar el camino.

<br>

#### El enfoque es ser un gestor integral de favoritos e ir más allá de un reorganizador de estos.
#### Estas son algunas de las funciones que Flow FavManager ofrece:

<br>

#### 1. Gestión Avanzada de Listas y Perfiles
*   **Sistema de Multi-Perfiles:** A diferencia de la gestión de una lista única, el usuario puede crear, guardar y cargar ilimitados "Perfiles" (archivos JSON independientes). Esto permite tener entornos separados para distintos usos (ej: "Perfil Niños", "Perfil Deportes", "Perfil Cine").
*   **Plantillas Predefinidas:** Integra un motor de plantillas que permite al usuario cargar listas de favoritos pre-diseñadas para configurar un Kodi nuevo en segundos.
*   **Guardado Rápido:** Función de `Quick Save` para actualizar el perfil activo sin pasar por menús de confirmación complejos.
*   **Importación y Exportación:** Herramientas para compartir perfiles o moverlos entre dispositivos mediante archivos XML.
*   **Widget Dinámico (Ruta de Vista Limpia):** Provee una ruta especializada (`/widget`) que expone los favoritos como carpetas limpias, diseñada específicamente para alimentar widgets en pantallas de inicio de skins avanzados (Aura, Arctic, Titan) sin mostrar botones de gestión.

#### 2. Seguridad y Privacidad
*   **Protección con PIN:** Sistema de seguridad robusto que permite bloquear el acceso al editor o a la carga de perfiles mediante un código numérico.
*   **Bloqueo de Sesión Inteligente:** El sistema recuerda si el usuario ya se ha autenticado durante la sesión actual de Kodi para no pedir el PIN repetidamente, mejorando la comodidad sin sacrificar seguridad.
*   **Pregunta de Seguridad:** Método de recuperación alternativo configurable por el usuario para restablecer el acceso en caso de olvido del PIN.
*   **Mecanismo de Rescate:** Implementa un `RESET_FILE` de emergencia para que el usuario pueda recuperar el acceso si olvida su contraseña, sin perder sus datos.
*   **Log de Auditoría:** Sistema de registro interno que traza acciones críticas (cambios de seguridad, borrado de perfiles, intentos de acceso fallidos) para que el usuario tenga control total sobre lo que ocurre en su gestor.

#### 3. Herramientas de Organización Masiva y Automatización
*   **Modo Multiselección:** Permite seleccionar múltiples favoritos simultáneamente (tipo Checkbox) para realizar acciones en lote.
*   **Operaciones en Grupo:**
    *   **Movimiento Masivo:** Mover un bloque de 20 canales de TV de la posición 100 a la 1 de golpe.
    *   **Borrado Masivo:** Limpiar listas extensas seleccionando y eliminando múltiples ítems a la vez.
    *   **Coloreado Masivo:** Aplicar un "estilo visual" (color de etiqueta) a todo un grupo de favoritos seleccionado.
*   **Agrupación Automática:** Algoritmo inteligente que escanea la lista y reagrupa automáticamente los favoritos según el Addon de origen (ej: pone todas las películas de Netflix juntas, todos los canales de YouTube juntos) con un solo clic.
*   **Ordenación Masiva:** Herramientas para ordenar toda la lista alfabéticamente (A-Z / Z-A) o invertir el orden completo instantáneamente.
*   **Búsqueda y Filtrado:** El usuario puede escribir texto para filtrar la lista en tiempo real y localizar rápidamente un favorito específico en listas extensas con cientos de elementos.

#### 4. Edición y Personalización Visual Profunda
*   **Estilización de Etiquetas:** El usuario puede cambiar el color del texto de cualquier favorito individualmente o aplicar formatos (negrita/cursiva) para destacar elementos importantes.
*   **Barras Separadoras:** Capacidad de insertar "Separadores Visuales" (líneas o textos divisorios sin acción) para organizar la lista en secciones legibles visualmente.
*   **Gestión de Iconos:**
    *   **Enriquecimiento Automático:** El sistema intenta buscar y asignar iconos automáticamente a los favoritos que no los tienen.
    *   **Cambio Manual:** El usuario puede seleccionar una imagen personalizada para cualquier favorito desde su almacenamiento local.
*   **Modo Accesibilidad:** Incluye ajustes específicos para mejorar la visibilidad, como modos de alto contraste o paletas adaptadas (ej: modo daltónico).

#### 5. Creación y Manipulación Avanzada
*   **Creación Manual de Ítems:** Permite crear un favorito "desde cero" escribiendo manualmente la etiqueta y la ruta (URL/Command), ideal para usuarios avanzados que conocen las rutas internas de Kodi.
*   **Duplicación de Entradas:** Función para clonar un favorito existente, útil para crear variaciones de un mismo canal o ruta.
*   **Edición de Rutas (Path):** Capacidad de editar el comando interno o URL de un favorito existente sin tener que borrarlo y volverlo a crear.
*   **Selector de Addons:** Un buscador integrado para localizar y añadir favoritos desde cualquier addon instalado en el sistema sin salir del editor.
*   **Menú Contextual Global:** Integración nativa que permite añadir contenido a los perfiles de Flow FavManager desde *cualquier* lista de Kodi (películas, canales, música) usando el menú contextual (clic derecho) sin necesidad de abrir el addon.
*   **Maximizador de Compatibilidad:** Lógica interna (`build_list_item`) que corrige automáticamente URLs problemáticas (scripts, comandos sin comillas) para asegurar que el 100% de los favoritos sean ejecutables, resolviendo limitaciones históricas del formato de favoritos de Kodi.

#### 6. Sistema de Backup Integral
*   **Copias de Seguridad (Backup/Restore):** Herramientas dedicadas para crear copias de seguridad completas del archivo `favourites.xml` y restaurarlas en cualquier momento.
