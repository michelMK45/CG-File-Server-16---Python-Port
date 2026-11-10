---
name: ce-check
description: Write step-by-step Cheat Engine instructions (in Spanish) for the maintainer to confirm a FIFA 16 memory address, offset or write footprint live before CGFS16 code relies on it. Use whenever a change would add an offset, a new write target, a longer write, or an address-suffix allowlist entry.
---

# Cheat Engine confirmation request

Hard rule (memory `live_memory_write_safety_protocol`, `.claude/rules/memory-writes.md`): a live write
past a proven-safe footprint, or to a new address, needs the user's own CE confirmation per address:
**(1) editing that address changes the intended thing on screen, and (2) a full match (or abandon) runs
afterwards without a crash.** "Readable" is not "unused" — two crashes came from that.

Never ask for a data breakpoint ("Find out what writes/accesses this address") on FIFA: it crashed the
game on the name buffer. Never propose patching code other than `Offsets.SUBHOOKRVA`.

## Produce for the user

1. **Qué buscamos y por qué** (1-2 frases).
2. **Preparación:** FIFA en ventana/sin pantalla completa exclusiva si hace falta, CE adjuntado a
   `fifa16.exe`, en qué pantalla/momento del juego parar.
3. **Búsqueda:** tipo de valor (String UTF-8 / 4 Bytes / Float), valor inicial, cómo cambiarlo en el
   juego para el "Next Scan", cuántas pasadas hasta quedar pocas direcciones.
4. **Prueba de edición:** qué valor escribir en la candidata y qué debería cambiar en pantalla.
5. **Prueba de estabilidad:** jugar/abandonar un partido completo con el valor cambiado; volver a
   Kick-Off; confirmar que no crashea.
6. **Qué mandarme:** dirección completa, los 4 dígitos hex finales (bits bajos estables con ASLR), bytes
   alrededor (vista Memory, ±64 bytes), si sobrevive a reiniciar FIFA (¿cambian solo los bits altos?),
   y el resultado de 4 y 5.
7. Si hace falta cadena de punteros: "Pointer scan for this address" (nivel máx 7, offset 0x10000) y
   re-validar tras reiniciar FIFA. Nota: para el nombre del estadio no existe cadena estática.

## After the answer

Only then wire the address/suffix into `offsets.py` (or `STDNAME_SAFE_EXTEND_*`) with a comment:
who confirmed it, date, what was verified. Record it in the area's doc. Without confirmation the code
may READ the value (diagnostics) but must not write it.
