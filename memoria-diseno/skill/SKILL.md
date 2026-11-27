---
name: memoria-de-calculo
description: Genera la memoria de cálculo o memoria de diseño estructural de un proyecto (losas, bloques de ETABS, fundaciones de SAFE) en Word y PDF con el motor memoria-diseno de CDCRD-Digital. Úsela siempre que pidan una memoria de cálculo, memoria de diseño, memoria estructural o memoria de losas, en vez de redactar el documento a mano.
---

# Memoria de cálculo estructural

El formato de la memoria lo fija un programa, no el asistente. El motor está en:

    {{MOTOR}}

1. Lea `{{MOTOR}}\AGENTS.md` completo y siga su procedimiento y sus criterios de formato.
2. Si esa carpeta no existe, el repositorio se movió o no está clonado: clone
   `https://github.com/dashy2004/CDCRD-Digital`, y ejecute `memoria-diseno\instalar-skill.ps1`
   para actualizar esta ruta. No continúe redactando la memoria por su cuenta.
3. Use `{{MOTOR}}\.venv\Scripts\python.exe` si existe.
4. Las salidas van en la carpeta del proyecto, nunca dentro del repositorio.
