"""SenseMinds 360 - Industrial Intelligence Platform.

Modular monolith (ADR-010). Layer boundaries, inner to outer:

    domain  <-  application  <-  interfaces
    domain  <-  engines / infrastructure  (implement inner-declared ports)

`domain` depends on nothing. See docs/architecture/ for the full spec.
"""

__version__ = "0.1.0"
