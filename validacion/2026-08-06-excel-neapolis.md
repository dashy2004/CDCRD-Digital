# Validacion cruzada: plantilla de practica profesional vs capa machine CDCRD

**Fuente**: `ARCHIVO ESTRUCTURAL 2025.xls` — plantilla de cuantificacion de cargas y espesores
de losas (Ing. Oliver Guillen Rosa, CODIA 18139), proyecto Neapolis IV. 15 hojas.

## Metodo de la plantilla (descifrado de las formulas)

1. **Clasificacion de losa**: `Cond = SI(max(Lx,Ly)/min(Lx,Ly) > 2, "1D", "2D")`.
2. **Espesor bidireccional (2D)**: `h = Ln*(0.8 + fy/14000) / (36 + 9*beta)` con fy en kgf/cm2
   y beta = lado largo/lado corto — es la ecuacion de espesor minimo de ACI 318 §9.5.3
   (la hoja lo declara: "Segun ACI-318-08 Art. 9.5.3").
3. **Espesor unidireccional (1D)**: `h = Ln/K` (tabla ACI 9.5(a); K segun condicion de apoyo).
4. **Minimo absoluto**: `h >= 0.12 m`.
5. **Combinacion**: `qu = 1.2*qd + 1.6*ql` (declarado ACI-318-05).
6. Losa aligerada con bovedilla S=0.15, B=0.50, L=0.50, h=0.15 (hoja Espesor Equivalente).

**Nota**: la tabla de ~72 casos de momentos por condicion de apoyo que menciona Emil NO esta
en este archivo (es de espesores y cargas). Hipotesis pendiente de confirmar: es el metodo de
coeficientes clasico (9 casos de apoyo x relaciones de lado). Falta el archivo/documento que
la contiene.

## Resultados de la validacion

| Concepto | Plantilla | CDCRD 2026 (capa machine) | Veredicto |
|---|---|---|---|
| Hormigon armado | 2.4 t/m3 (23.5 kN/m3) | consistente con practica | OK |
| CV entrepiso residencial | 0.20 t/m2 = 1.96 kN/m2 | 1.92 kN/m2 (T4, "todas las demas areas", cl. 2.7.2) | OK (redondeo en unidades tecnicas) |
| CV balcones | 0.40 t/m2 = 3.92 kN/m2 | 1.5 x area servida = 1.5x1.92 = 2.88 kN/m2 | OK (queda del lado seguro) |
| **CV escaleras** | 0.40 t/m2 = 3.92 kN/m2 | **4.79 kN/m2** (corredores y escaleras, cl. 2.7.2) | **DEFICIT: la plantilla queda 18% por debajo del CDCRD nuevo** |
| Combinacion LRFD | 1.2qd + 1.6ql | 1.2(D+F)+1.6L+... (cl. 2.4.2.1.1, combo 2) | OK |
| Espesores | ACI 318 §9.5.2/9.5.3 | Titulo 5 CDCRD remite a ACI 318-25 | OK (verificar cambios 318-08 -> 318-25) |

## Conclusion

La validacion funciona en ambos sentidos: la plantilla confirma la capa machine (cargas,
combinaciones), y la capa machine **detecto un valor de la practica anterior que el codigo
nuevo supero** (escaleras: 3.92 vs 4.79 kN/m2). Este es exactamente el caso de uso del
proyecto: auditar automaticamente hojas de calculo existentes contra el CDCRD vigente.

**Accion recomendada para las plantillas del estudio**: actualizar la carga de escaleras
a 4.79 kN/m2 (0.49 t/m2) y revisar espesores contra ACI 318-25 (la plantilla cita 318-05/318-08).
