# Density Functional (DFT) Methods（mini 夹具）

## Keywords: Hybrid Functionals

- M06 hybrid functional of Truhlar. The M06HF and M062X variations are also available.
- The wB97XD functional uses a version of dispersion.
- The keyword is PBE1PBE. This functional uses 25% exact exchange.
- Becke's 1998 revisions to B97. The keyword is B98.
- The B1B95 keyword is used to specify Becke's one-parameter hybrid functional.

### Exchange Functionals

- S: The Slater exchange. Keyword if used alone: HFS.
- XA: The XAlpha exchange. Keyword if used alone: XAlpha.
- B: Becke's 1988 functional. Keyword if used alone: HFB.

## Examples

The functionals highlighted in bold include this dispersion model by default
when the indicated keyword is specified (e.g., B2PLYPD). Dispersion is
requested with EmpiricalDispersion=GD2.
