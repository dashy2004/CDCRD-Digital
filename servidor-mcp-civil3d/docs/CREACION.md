# Creacion nativa de objetos (puente 0.2.0)

Once herramientas nuevas que eliminan el hueco principal del puente: crear
objetos Civil 3D y entidades de dibujo 100% por API .NET, sin interfaz, sin
LISP y sin dialogos modales. Todas las escrituras exigen `confirmar=True`
(token de un solo uso); todas son idempotentes por nombre: si el objeto ya
existe devuelven su handle con `ya_existia=true`.

## Perfiles y vistas de perfil

| Herramienta | Hace | Metodo .NET |
|---|---|---|
| `crear_perfil_desde_superficie` | perfil de superficie sobre un alineamiento | `Profile.CreateFromSurface` |
| `crear_perfil_constante` | perfil de elevacion constante (2 PVIs) | `Profile.CreateByLayout` + `PVIs.AddPVI` |
| `crear_vista_perfil` | vista de perfil con rangos y origen exactos | `ProfileView.Create` + propiedades |
| `agregar_hatch_vista_perfil` | relleno nativo entre dos perfiles (Cut Area) | `ProfileView.HatchAreas.Add` |

Notas:
- `crear_vista_perfil` compensa el desplazamiento conocido: fijar
  `StationStart` mueve el `Location`, asi que el origen se reescribe al final
  y la respuesta trae el `Location` real.
- Relleno hasta cota fija (p. ej. caliza competente hasta el fondo de la
  vista): cree un perfil constante a esa cota y uselo como `inferior`. El
  relleno es nativo y se regenera si cambian las superficies.
- `alineamiento`, `superficie`, `vista` y los perfiles aceptan nombre o handle.

Ejemplo (receta minima del perfil estratigrafico):

```
crear_perfil_desde_superficie(alineamiento="Corte A-A'", superficie="GM - Stratum - RELLENO.1",
                              nombre="EST-RELLENO", estilo="GEO - RELLENO", confirmar=True)
crear_perfil_constante(alineamiento="Corte A-A'", nombre="EST-FONDO", elevacion=18, confirmar=True)
crear_vista_perfil(alineamiento="Corte A-A'", origen="409000,2044000", nombre="VP ESTRATIGRAFICO",
                   est_inicio=0, est_fin=520, elev_min=18, elev_max=44, confirmar=True)
agregar_hatch_vista_perfil(vista="VP ESTRATIGRAFICO", nombre="CAL-COMP",
                           superior="EST-CALIZA-COMP", inferior="EST-FONDO",
                           estilo_forma="GEO - Cal comp", confirmar=True)
```

## Estilos

| Herramienta | Hace |
|---|---|
| `listar_estilos` | nombre + handle por familia (lo que `Name` no dejaba leer via API) |
| `crear_estilo` | `Add(nombre)` o clon con `CopyAsSibling` (`base`) |
| `editar_estilo_display` | color/capa/tipo de linea/grosor/visible de un componente (`GetDisplayStyle*`) |
| `purgar_estilos` | borra por regex (huerfanos `.1` de GM); lo en uso queda en `fallidos` |

El color de una linea de perfil lo manda el estilo (no la entidad):
`editar_estilo_display(familia='ProfileStyles', estilo='GEO - RELLENO',
vista='Profile', componente='Line', color_aci=34, confirmar=True)`.

## Entidades y utilidades

| Herramienta | Hace |
|---|---|
| `crear_entidad` | capa, linea, polilinea, polilinea3d, texto, mtexto, circulo, solido, punto, hatch, bloque — nativo, devuelve handles |
| `borrar_objeto` | borra por handles (entidades, perfiles, vistas, estilos) |
| `orden_dibujo` | arriba/abajo/encima/debajo (rellenos al fondo, etiquetas encima) |

`crear_entidad` reemplaza a `crear_entidades`/`ejecutar_lisp` para dibujo:
no pasa por la linea de comandos, no abre el dialogo de seguridad de .lsp y
devuelve los handles en la misma respuesta (sincrono).

## Mejoras de lectura que acompanan

- `leer_ruta` ahora admite metodos con argumentos y claves por nombre:
  `GetDisplayStyleProfile(Line).Color`, `Styles.ProfileStyles["GEO - TERRENO"].Name`.
- `inspeccionar_objeto` admite `patron` (regex), `solo_escribibles` e
  `incluir='props'|'metodos'` para no recibir 55 kB por un ProfileView.

## Pendiente conocido

- Patron/escala del hatch de un ShapeStyle nuevo creado con `Add` (sin base):
  clone con `base` un estilo con SOLID mientras tanto.
- Bandas: `crear_vista_perfil(banda=...)` usa `Bands.ImportBandSetStyle` por
  reflexion; si la firma difiere en otra version queda en `fallidos`.
