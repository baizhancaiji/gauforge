# SCF

## Description

This keyword controls the functioning of the SCF procedure.

## Options

### Algorithm Selection Options

#### QC

Calls for the use of a quadratically convergent SCF procedure.

#### XQC

Add an extra SCF=QC step in case the first-order SCF has not converged.

#### YQC

Extra QC with default guess.

#### NDamp=*N*

Allow dynamic damping for up to N SCF iterations.

#### Fermi

Fermi requests and NoFermiTest suppresses testing the curvature in SCF.

#### Pass

NoPassEx forces integrals to be recomputed during each in-core phase.

#### VShift

VShift=*N* is equivalent to NoVShiftEx and UseFallbackEx.

#### Extra

Use NoExtraGuess to disable this feature.

#### GICInfo

The option NoGICEx builds the internal coordinates of Peng96.

#### Raff, RafEx1

Enumeration headings are normalized per segment.

#### Conv

Only one of CAngles, Angles, and NoAnglesEx may be specified.

#### Usage Notes

Prose heading with spaces must be skipped by the option face.

## Availability

Explicit only.
