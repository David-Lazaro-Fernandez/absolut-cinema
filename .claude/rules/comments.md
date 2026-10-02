# Comentarios y docstrings

Aplica a todo cambio de código. Antes de dar un cambio por terminado, relee cada comentario y docstring que agregaste o
tocaste, y corrígelo con estas reglas.

- **El código se explica solo.** Primero un buen nombre (función, variable, constante). Un comentario que repite lo
  que el código ya dice se borra. Ejemplo: renombra a `LOCAL_MIN_CHARS` en vez de escribir `# letras`.
- **Solo el porqué.** Un comentario dice por qué el código es así, sobre todo el porqué de una API ajena (una pausa, un
  lote de 30, un campo que falta). No describe el qué ni el historial.
- **Sin explicar de más.** Una idea por frase. Si el comentario es más largo que el código que explica, recórtalo.
- **Español Técnico Simplificado** (estilo ASD-STE100; en inglés, ASD-STE100):
  - frases cortas, de 20 palabras o menos;
  - presente y voz activa;
  - una palabra por concepto, siempre la misma;
  - sin cadenas de dos puntos ni paréntesis dentro de paréntesis.
- **Nunca al final de una línea de código.** El comentario va en su propia línea, arriba del código. Aplica también en
  pruebas.
- **Docstrings para quien usa la función.** Qué recibe, qué devuelve y un ejemplo corto (`'Digger SUB' → ('Digger',
  'subtitled')`). Lo que necesita quien edita va en un comentario.
- Mayúscula inicial y puntuación correcta. Las convenciones generales están en `AGENTS.md` §3.
