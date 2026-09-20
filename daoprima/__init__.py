"""
DaoPrima — DAO-oriented slice for Arcetri Prima (Drop 2+).

Design goals (binding):
- Reuse daoEkarus GUIs / scripts / ICD / SHM naming as much as possible
  (wrap or carefully adapt with attribution — prefer wrap over rewrite).
- Device I/O stays on the Arcetri plico stack (pysilico + plico_dm BMC).
- RTC should eventually be daoBase; until then a thin Python integrator at
  ~Manta rates (~60 fps) is acceptable for laptop / lab bring-up.
- Structure so daoBase can plug in later without rewriting the GUIs
  (GUIs talk SHM paths / ICD names, not plico clients directly).

Vendor reference (read-only): ``prima/vendor/daoEkarus``.
"""

__version__ = '0.1.0'
