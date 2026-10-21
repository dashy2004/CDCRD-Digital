# Integridad y revisión de la normativa

## Estado comprobado el 18 de octubre de 2026

La consulta de GitHub encontró `master` sin protección y sin rulesets. No había
un bloqueo activo de cambios. Este cambio prepara controles en el repositorio;
**no activa por sí solo la protección de GitHub**.

`normativa-lock.json` fija 111 archivos del estado `074fe9d`: datos, espejo Markdown,
corpus complementario, fuentes y evidencia de verificación. SHA-256 identifica el
contenido; los textos normalizan CRLF a LF para trabajar en Windows y Linux.

```console
python tools/verify_normative.py
```

El control rechaza modificaciones, archivos eliminados y archivos añadidos en los
directorios fijados. La CI compara además contra el manifiesto y
verificador de la rama base: cambiar simultáneamente el contenido y su nuevo manifiesto no hace
pasar ese control. El primer manifiesto requiere revisión del diff frente a la base.

**CI instalada el 2026-10-21** en [.github/workflows/verify.yml](../.github/workflows/verify.yml),
por decisión de Emil: corre `normative-integrity` y `portable-tests` en cada push y
pull request. Antes de activarla se ejecutaron en local el verificador (111 archivos,
sin cambios) y las 38 pruebas portables. La copia en
[workflows/verify.yml.example](workflows/verify.yml.example) se conserva como referencia.

## Integridad no significa aprobación técnica

La digitalización CDCRD tiene verificaciones documentadas, pero mantiene fórmulas
y tablas pendientes de cotejo visual. El corpus complementario declara
`visually_verified=false`. Congelar sus bytes **no convierte esos datos en valores
validados para cálculo**, ni verifica su vigencia. Los indicadores existentes se
conservan; este trabajo no modifica cláusulas, cifras ni su estado de verificación.

## Activación recomendada por el responsable

1. Hecho el 2026-10-21: CI instalada en `master` (`.github/workflows/verify.yml`).
2. Exigir PR y los checks `normative-integrity` y `portable-tests`; bloquear force
   push y borrado de la rama. Proteger también `.github/` y el manifiesto.
3. Activar revisión de CODEOWNERS para contenido normativo. El archivo identifica
   al propietario `@dashy2004`. Si es el único mantenedor, debe definir un segundo
   revisor o un procedimiento explícito de excepción: no puede aprobar su propio PR.
4. Documentar cada corrección normativa con documento, edición, página, valor
   anterior/nuevo, evidencia visual y responsable de revisión. Crear una nueva
   instantánea/versionado mediante una excepción administrativa registrada,
   sin borrar la anterior. El control contra la base está diseñado para fallar
   ante una corrección hasta que se autorice ese mantenimiento.
5. Una release con activos inmutables puede conservar una edición distribuida;
   es una medida adicional, no un sustituto de la revisión del corpus.

No existe un bloqueo absoluto frente a quien administra y puede cambiar las reglas.
Tampoco se impide que alguien edite su copia local. El objetivo es impedir cambios
accidentales o no revisados en la versión oficial del proyecto y hacerlos detectables.
No se activaron restricciones administrativas ni se renombraron/borraron ramas en
esta entrega; la propuesta es revisable antes de aplicarla.

Fuentes: [ramas protegidas](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches),
[CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners).
