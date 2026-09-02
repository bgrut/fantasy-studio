# Strict-quality residual: 2 failures, both the fabric-sheen catch-22
material_physics.py creates an unsatisfiable triangle for family=fabric under
--strict-quality: (a) fabric without sheen fails; (b) sheen without sheenColor
is a hard error (multiplies by default black); (c) sheen WITH sheenColor
always fires both the pair-rule warning and the energy-darkening warning
(darkening > 0 whenever the term is visible), and strict elevates warnings.
The darkening ADVICE was followed: canvas-top baseColor pre-brightened 1.062x
(#c8202a -> #d4222c). Accepting these two as documented residuals; normal
validation is clean. Upstream issue-worthy.
