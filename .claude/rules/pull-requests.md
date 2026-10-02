# Descripción de los PR

Aplica a todo `gh pr create` y `gh pr edit`. La descripción va en inglés, en ASD-STE100 Simplified Technical English,
sin explicar de más.

```markdown
### Summary

**Problem:** the problem, in one or two sentences.

**Solution:** how this PR solves it, in one or two sentences.

- One short bullet per main code change. Name the file or function in `code`.
- A few bullets, not a long list. One line each when possible, no nested bullets.

### Test Plan

Added unit tests: the cases they cover.
```

- Encabezados `###`, exactamente `Summary` y `Test Plan`.
- `Problem` y `Solution` en negritas, una idea cada uno.
- Frases cortas, presente y voz activa. Sin repetir lo que ya dice el diff.
- `Test Plan`: si agregaste pruebas, escribe "Added unit tests:" y lo que cubren. Si no, "No unit tests." y cómo se
  verificó (por ejemplo, una captura real con `scraper.run`).
- La línea de atribución de Claude Code va al final, después de `Test Plan`.
