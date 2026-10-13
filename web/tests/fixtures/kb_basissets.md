# Basis Sets（mini 夹具）

## Description

The following basis sets are stored internally in Gaussian:

- STO-3G [[Hehre69]]
- 6-31G [[Ditchfield71]]
- 6-311G [[McLean80]]
- LanL2DZ [[Hay85]]
- cc-pVDZ, cc-pVTZ, cc-pVQZ
- The newer redefinitions are requested with the keywords Def2SVP, Def2TZVP.
- EPR-II and EPR-III
- DGDZVP and CBSB7
- MidiX of Truhlar and coworkers. The MidiX keyword is used.
- QZVP
- 5D and 6D: Use 5 or 6 d functions.
- SVPFit corresponding to the SVP basis set.

## Adding Polarization and Diffuse Functions

The keyword syntax is best illustrated by example: 6-31+G(3df,2p) designates
the 6-31G basis set supplemented by diffuse functions; 6-31G** is equivalent
to 6-31G(d,p); AUG- prefix adds diffuse functions (AUG-cc-pVTZ).
