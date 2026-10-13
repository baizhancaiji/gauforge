# Gaussian Calculation Setup Keywords & Options（mini 夹具）

| Job Type Tab | |
| --- | --- |
| Job Type => Optimization | opt |
| Use RFO step | opt=rfo |
| Job Type => Frequency | freq |
| Compute ROA => Yes | freq=roa |
| Job Type => Opt+Freq | opt freq |
| Read Incident Light Freqs => Yes | freq cphf=rdfreq |
| Compute more points, N= | irc=maxpoints= *n* |

| Method Tab | |
| --- | --- |
| Method => DFT => B3LYP | b3lyp |
| Method => Hartree-Fock | hf |

| Link0 Tab | |
| --- | --- |
| **Memory Limit** | %mem |
| **Shared Processors** | %nprocshared |

| General Tab | |
| --- | --- |
| Additional Print | #p |
| Method => Restricted | R prefix |
| Method => Unrestricted | U prefix |
| Write Gaussian Fragment Data | fragment in molecule specification |
