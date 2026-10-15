"""Aplanar un dibujo a elevacion 0 (equivalente controlado de FLATTEN).

Un solo LISP (via .lsp temporal + cmd.run) recorre el espacio modelo y las
definiciones de bloque, pone Z=0 en los puntos de cada entidad (codigos DXF
10-17), la elevacion de las LWPOLYLINE (38) y los vertices/atributos
anidados, y escribe un reporte JSON a archivo; la receta lo sondea porque la
carga del LISP es asincrona. No toca solidos/regiones/superficies/mallas
(ACIS): los cuenta como no_aplanables. Las capas bloqueadas hacen fallar
entmod: se cuentan como fallidas.

Uso directo:   aplanar(puente, dibujo, esperado='POLIDEPORTIVO')
Herramienta MCP: aplanar_dibujo (registrada por registrar()).
"""
import json
import os
import time

RUTA_REPORTE = r'C:\Users\emilg\AppData\Local\Temp\cdcrd_aplanar.json'


def lisp_aplanar(ruta_reporte, incluir_bloques=True):
    """Codigo AutoLISP del aplanado. Puro: no habla con el puente."""
    rep = ruta_reporte.replace('\\', '/')
    bloques = ''
    if incluir_bloques:
        bloques = '''
  (setq blk (tblnext "BLOCK" T))
  (while blk
    (setq bn (cdr (assoc 2 blk)))
    (if (and (zerop (logand 4 (cdr (assoc 70 blk))))
             (not (wcmatch (strcase bn) "`*D*,`*MODEL_SPACE*,`*PAPER_SPACE*")))
        (progn
          (setq e (cdr (assoc -2 blk)))
          (while e (cdcrd-ent e) (setq e (entnext e)))))
    (setq blk (tblnext "BLOCK")))'''
    return ('''(vl-load-com)
(setq cdcrd-mod 0 cdcrd-ya 0 cdcrd-no 0 cdcrd-fall 0)
(defun cdcrd-lista (ed tn / cambiado nuevo c v)
  ;; en MULTILEADER los codigos 11/12 son VECTORES de direccion (unitarios),
  ;; no puntos: tocarlos no aplana nada y AutoCAD los renormaliza
  (setq cambiado nil nuevo nil)
  (foreach par ed
    (setq c (car par) v (cdr par))
    (cond
      ((and (member c '(10 11 12 13 14 15 16 17))
            (not (and (= tn "MULTILEADER") (member c '(11 12))))
            (listp v) (= (length v) 3) (not (equal (caddr v) 0.0 1e-9)))
       (setq nuevo (cons (cons c (list (car v) (cadr v) 0.0)) nuevo) cambiado T))
      ((and (= c 38) (not (equal v 0.0 1e-9)))
       (setq nuevo (cons (cons c 0.0) nuevo) cambiado T))
      (T (setq nuevo (cons par nuevo)))))
  (cons cambiado (reverse nuevo)))
(defun cdcrd-mod1 (ed tn / r)
  (setq r (cdcrd-lista ed tn))
  (if (car r)
      (if (entmod (cdr r))
          (setq cdcrd-mod (1+ cdcrd-mod))
          (setq cdcrd-fall (1+ cdcrd-fall)))
      (setq cdcrd-ya (1+ cdcrd-ya))))
(defun cdcrd-ent (en / ed tn sub)
  (setq ed (entget en) tn (cdr (assoc 0 ed)))
  (if (member tn '("3DSOLID" "BODY" "REGION" "SURFACE" "PLANESURFACE" "MESH"))
      (setq cdcrd-no (1+ cdcrd-no))
      (progn
        (cdcrd-mod1 ed tn)
        (if (member tn '("POLYLINE" "INSERT"))
            (progn
              (setq sub (entnext en))
              (while (and sub (member (cdr (assoc 0 (entget sub)))
                                      '("VERTEX" "ATTRIB")))
                (cdcrd-mod1 (entget sub) (cdr (assoc 0 (entget sub))))
                (setq sub (entnext sub))))))))
(defun c:CDCRD-APLANAR (/ ss i en blk bn e f)
  (setq ss (ssget "_X" '((410 . "Model"))))
  (if ss
      (progn
        (setq i 0)
        (while (< i (sslength ss))
          (cdcrd-ent (ssname ss i))
          (setq i (1+ i)))))''' + bloques + '''
  (setvar "ELEVATION" 0.0)
  (setq f (open "''' + rep + '''" "w"))
  (write-line (strcat "{\\"modificadas\\": " (itoa cdcrd-mod)
                      ", \\"ya_planas\\": " (itoa cdcrd-ya)
                      ", \\"no_aplanables\\": " (itoa cdcrd-no)
                      ", \\"fallidas\\": " (itoa cdcrd-fall)
                      ", \\"dibujo\\": \\"" (getvar "DWGNAME") "\\"}") f)
  (close f)
  (princ))
(c:CDCRD-APLANAR)
''')


def aplanar(puente, dibujo, esperado='', incluir_bloques=True, timeout=180,
            ruta_reporte=RUTA_REPORTE, log=print):
    """Aplana el dibujo ACTIVO. `esperado`: subcadena que debe estar en la ruta
    del dwg activo (seguro contra aplanar el dibujo equivocado). `dibujo` es el
    modulo src/dibujo.py (escribir_lisp_temporal / ruta_load)."""
    info = puente.llamar('doc.info', {})
    activo = str(info.get('dibujo', ''))
    if esperado and esperado.lower() not in activo.lower():
        raise ValueError('el dibujo activo es %r, no contiene %r: abra el dwg '
                         'a aplanar y repita' % (activo, esperado))
    try:
        os.remove(ruta_reporte)
    except OSError:
        pass
    ruta = dibujo.escribir_lisp_temporal(lisp_aplanar(ruta_reporte, incluir_bloques))
    puente.llamar_con_aprobacion('cmd.run', {'linea': dibujo.ruta_load(ruta)})
    log('LISP cargado (%s); esperando el reporte...' % ruta)
    fin = time.time() + timeout
    while time.time() < fin:
        if os.path.isfile(ruta_reporte):
            time.sleep(1.0)                       # deja terminar la escritura
            with open(ruta_reporte, encoding='ascii', errors='replace') as f:
                r = json.load(f)
            r['dibujo_activo'] = activo
            r['aviso'] = ('solidos/regiones/superficies/mallas no se aplanan; '
                          'capas bloqueadas cuentan como fallidas')
            return r
    raise TimeoutError('el aplanado no escribio %s en %ds (dibujo grande, '
                       'dialogo modal, o comandos deshabilitados)' % (ruta_reporte, timeout))


def registrar(mcp, llamar, ok):
    """Registra aplanar_dibujo en el servidor MCP."""
    import dibujo as _dibujo
    import puente_cliente as _p

    @mcp.tool()
    def aplanar_dibujo(esperado: str = '', incluir_bloques: bool = True,
                       confirmar: bool = False) -> str:
        """Pone TODO el dibujo activo en elevacion 0 (puntos, polilineas,
        vertices, textos, cotas, bloques y sus definiciones; no solidos ACIS).

        esperado: subcadena que debe aparecer en la ruta del dwg activo, como
        seguro contra aplanar el dibujo equivocado. El dibujo NO se guarda:
        revisar y guardar con guardar_dibujo. Asincrono por dentro (LISP), la
        respuesta vuelve con el conteo cuando el reporte aparece.
        """
        if not confirmar:
            return ok({'error': 'operacion de escritura: repita con confirmar=True',
                       'esperado': esperado})
        try:
            return ok(aplanar(_p, _dibujo, esperado=esperado,
                              incluir_bloques=incluir_bloques, log=lambda m: None))
        except Exception as exc:                    # noqa: BLE001
            return ok({'error': '%s: %s' % (type(exc).__name__, exc)})
