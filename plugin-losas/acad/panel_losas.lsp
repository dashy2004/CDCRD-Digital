;;; panel_losas.lsp — asignación de Uso_Losa dentro de AutoCAD (plugin-losas).
;;;
;;; Flujo AutoCAD del plugin (convención de recuadros + numeración del flujo
;;; AutoCAD↔Excel/ETABS de la Ing. Arlette Ramírez):
;;;   1. El plano tiene los paños como polilíneas cerradas en la capa LOSAS y
;;;      la numeración como TEXT dentro de cada recuadro.
;;;   2. `plugin-losas usos --salida dir/` genera usos_tabla4.txt con los 45
;;;      usos de la Tabla 4 del CDCRD numerados (id estable por uso).
;;;   3. USOLOSA: se selecciona el TEXTO de numeración de una losa y se teclea
;;;      el número del uso de la lista; queda en memoria de la sesión.
;;;   4. GUARDAUSOS: escribe usos_marcados.json {mark: id-uso} para el CLI:
;;;        plugin-losas tabla --dxf plano.dxf --usos-marcados usos_marcados.json
;;;      (la geometría sale del DXF; este LISP solo captura la decisión de uso).
;;;
;;; ESTADO: escrito sobre AutoLISP estándar (entsel/entget/DXF 1) pero NO
;;; verificado en una sesión viva de AutoCAD; la extracción de geometría y la
;;; resolución de usos sí están testeadas en Python (plugin_losas, 54 tests).

(vl-load-com)

(setq *cdcrd-usos* nil)       ; lista de pares ("MARK" . "id-uso-tabla4")
(setq *cdcrd-opciones* nil)   ; lista de ids leída de usos_tabla4.txt

(defun cdcrd-leer-opciones (ruta / f linea ids)
  (setq f (open ruta "r") ids nil)
  (if (null f) (progn (prompt "\nNo se pudo abrir usos_tabla4.txt") (exit)))
  (while (setq linea (read-line f))
    ;; formato de cada línea: "NN<TAB>id-del-uso<TAB>etiqueta"
    (if (vl-string-search "\t" linea)
        (setq ids (cons (cadr (cdcrd-partir linea "\t")) ids))))
  (close f)
  (reverse ids))

(defun cdcrd-partir (cadena sep / pos partes)
  (setq partes nil)
  (while (setq pos (vl-string-search sep cadena))
    (setq partes (cons (substr cadena 1 pos) partes))
    (setq cadena (substr cadena (+ pos 1 (strlen sep)))))
  (reverse (cons cadena partes)))

(defun c:CARGAUSOS (/ ruta)
  "Carga usos_tabla4.txt (generado por: plugin-losas usos)."
  (setq ruta (getfiled "usos_tabla4.txt del plugin" "" "txt" 0))
  (if ruta
      (progn (setq *cdcrd-opciones* (cdcrd-leer-opciones ruta))
             (prompt (strcat "\n" (itoa (length *cdcrd-opciones*)) " usos cargados."))))
  (princ))

(defun c:USOLOSA (/ sel ent datos mark n uso)
  "Selecciona el TEXTO de numeración de una losa y asigna un uso de la Tabla 4."
  (if (null *cdcrd-opciones*) (progn (prompt "\nPrimero CARGAUSOS.") (exit)))
  (setq sel (entsel "\nTexto de numeración de la losa: "))
  (if (null sel) (exit))
  (setq ent (car sel) datos (entget ent))
  (if (/= (cdr (assoc 0 datos)) "TEXT")
      (progn (prompt "\nEso no es un TEXT.") (exit)))
  (setq mark (cdr (assoc 1 datos)))
  (setq n (getint (strcat "\nNúmero de uso (1-" (itoa (length *cdcrd-opciones*))
                          ", ver usos_tabla4.txt) para " mark ": ")))
  (if (or (null n) (< n 1) (> n (length *cdcrd-opciones*)))
      (progn (prompt "\nNúmero fuera de rango.") (exit)))
  (setq uso (nth (1- n) *cdcrd-opciones*))
  (setq *cdcrd-usos* (cons (cons mark uso)
                           (vl-remove-if '(lambda (p) (= (car p) mark)) *cdcrd-usos*)))
  (prompt (strcat "\n" mark " -> " uso "  (" (itoa (length *cdcrd-usos*)) " asignadas)"))
  (princ))

(defun c:GUARDAUSOS (/ ruta f primero)
  "Escribe usos_marcados.json con las asignaciones de la sesión."
  (if (null *cdcrd-usos*) (progn (prompt "\nNada asignado todavía.") (exit)))
  (setq ruta (getfiled "Guardar usos_marcados.json" "usos_marcados" "json" 1))
  (if (null ruta) (exit))
  (setq f (open ruta "w") primero T)
  (write-line "{" f)
  (foreach par (reverse *cdcrd-usos*)
    (write-line (strcat (if primero " " ",")
                        "\"" (car par) "\": \"" (cdr par) "\"") f)
    (setq primero nil))
  (write-line "}" f)
  (close f)
  (prompt (strcat "\nGuardado " ruta " — siguiente: plugin-losas tabla --dxf plano.dxf"
                  " --usos-marcados usos_marcados.json"))
  (princ))

(prompt "\nplugin-losas: CARGAUSOS, USOLOSA, GUARDAUSOS cargados.")
(princ)
